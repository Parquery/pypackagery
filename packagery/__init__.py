"""Package a subset of a monorepo and determine the dependent packages."""
import csv
import io
import json
import modulefinder
import os
import pathlib
import sys
from typing import List, Mapping, TextIO, Set, MutableMapping, cast, Any

import collections
import icontract
import pkg_resources
import requirements as requirements_parser
import stdlib_list

READTHEDOCS = os.environ.get("READTHEDOCS", None) is not None


@icontract.require(lambda initial_paths: all(pth.is_absolute() for pth in initial_paths))
@icontract.ensure(lambda result: all(pth.is_file() for pth in result))
@icontract.ensure(lambda result: all(pth.is_absolute() for pth in result))
@icontract.ensure(lambda initial_paths, result: len(result) >= len(initial_paths) if initial_paths else result == [])
@icontract.ensure(
    lambda initial_paths, result: all(pth in result for pth in initial_paths if pth.is_file()),
    "Initial files also in result",
    enabled=icontract.SLOW or READTHEDOCS)
def resolve_initial_paths(initial_paths: List[pathlib.Path]) -> List[pathlib.Path]:
    """
    Resolve the initial paths of the dependency graph by recursively adding ``*.py`` files beneath given directories.

    :param initial_paths: initial paths as absolute paths
    :return: list of initial files (*i.e.* no directories)
    """
    if not initial_paths:
        return []

    seen_pths = set()  # type: Set[pathlib.Path]

    result = []  # type: List[pathlib.Path]

    for pth in initial_paths:
        if pth.is_file():
            result.append(pth)
            seen_pths.add(pth)

        elif pth.is_dir():
            for subpth in sorted(pth.glob("**/*.py")):
                if subpth not in seen_pths:
                    result.append(subpth)
                    seen_pths.add(subpth)
        else:
            raise NotImplementedError("Unhandled path, not a directory nor a file: {}".format(pth))

    return result


@icontract.invariant(lambda self: self.name.strip() == self.name)
@icontract.invariant(lambda self: self.line.endswith("\n"))
class Requirement:
    """Represent a requirement in requirements.txt."""

    def __init__(self, name: str, line: str) -> None:
        """
        Initialize.

        :param name: package name
        :param line: line in the requirements.txt file
        """
        self.name = name

        if not line.endswith("\n"):
            self.line = line + "\n"
        else:
            self.line = line

    def to_mapping(self) -> Mapping[str, Any]:
        """Represent the requirement as a mapping that can be directly converted to JSON and similar formats."""
        return collections.OrderedDict([("name", self.name), ("line", self.line)])


@icontract.ensure(lambda result: all(val.name == key for key, val in result.items()))
def parse_requirements(text: str, filename: str = '<unknown>') -> Mapping[str, Requirement]:
    """
    Parse requirements file and return package name -> package requirement as in requirements.txt.

    :param text: content of the ``requirements.txt``
    :param filename: where we got the ``requirements.txt`` from (URL or path)
    :return: name of the requirement (*i.e.* pip package) -> parsed requirement
    """
    result = collections.OrderedDict()  # type: MutableMapping[str, Requirement]

    try:
        for req in requirements_parser.parse(text):
            assert isinstance(req.line, str)
            assert req.uri is None or isinstance(req.uri, str)

            if req.name is None:
                raise ValueError(("The name is missing in the requirement from the file {}: {} "
                                  "(did you specify the egg fragment?)").format(filename, req.line))

            requirement = Requirement(name=req.name, line=req.line)

            result[requirement.name] = requirement
    except pkg_resources.RequirementParseError as err:  # type: ignore
        raise ValueError("Invalid requirements in file {}".format(filename)) from err

    return result


@icontract.ensure(lambda result: all(not key.endswith("\n") for key in result.keys()))
@icontract.ensure(lambda result: all(not val.endswith("\n") for val in result.values()))
def parse_module_to_requirement(text: str, filename: str = '<unknown>') -> Mapping[str, str]:
    """
    Parse the correspondence between the modules and the pip packages given as tab-separated values.

    :param text: content of ``module_to_requirement.tsv``
    :param filename: where we got the ``module_to_requirement.tsv`` from (URL or path)
    :return: name of the module -> name of the requirement
    """
    result = collections.OrderedDict()  # type: MutableMapping[str, str]

    stream = cast(TextIO, io.StringIO(text))

    for i, row in enumerate(csv.reader(stream, dialect='excel-tab')):
        if len(row) != 2:
            raise ValueError("Expected two columns, but got {} on line {} in {}: {}".format(
                i + 1, len(row), filename, row))

        module_name, requirement_name = row
        result[module_name] = requirement_name

    return result


@icontract.ensure(lambda result: len(result) == len(set(result)), enabled=icontract.SLOW or READTHEDOCS)
def missing_requirements(module_to_requirement: Mapping[str, str],
                         requirements: Mapping[str, Requirement]) -> List[str]:
    """
    List requirements from module_to_requirement missing in the ``requirements``.

    :param module_to_requirement: parsed ``module_to_requiremnt.tsv``
    :param requirements: parsed ``requirements.txt``
    :return: list of requirement names
    """
    result = []  # type: List[str]
    seen = set()  # type: Set[str]

    for requirement_name in module_to_requirement.values():
        if requirement_name not in requirements and requirement_name not in seen:
            result.append(requirement_name)

    return result


class UnresolvedModule:
    """
    Represent a module which was neither in the code base nor in requirements nor in built-ins.

    :ivar name: name of the module
    :ivar importer_rel_path: path to the file that imported the module
    """

    def __init__(self, name: str, importer_rel_path: pathlib.Path) -> None:
        """
        Initialize.

        :param name: name of the module
        :param importer_rel_path: path (relative to the codebase root dir) to the file that imported the module
        """
        self.name = name
        self.imported_from = importer_rel_path

    def to_mapping(self) -> Mapping[str, Any]:
        """Represent the unresolved module as a mapping that can be directly converted to JSON and similar formats."""
        return collections.OrderedDict([("name", self.name), ("imported_from", self.imported_from.as_posix())])


class Package:
    """
    Represent the package as a dependency graph of the initial set of python files from the code base.

    The package includes the initial set, the pypi depedendencies and the files from the code base recursively imported
    from the initial set.

    :ivar requirements: pip requirements, mapped by package name
    :ivar rel_paths: paths to the python files in the package relative to the root directory of the python code base
    :ivar unresolved_modules:
        modules which we couldn't find neither in the codebase nor in requirements nor in built-ins.
    """

    def __init__(self) -> None:
        """Initialize."""
        self.requirements = dict()  # type: MutableMapping[str, Requirement]
        self.rel_paths = set()  # type: Set[pathlib.Path]
        self.unresolved_modules = []  # type: List[UnresolvedModule]

    def to_mapping(self) -> Mapping[str, Any]:
        """Convert the package recursively to a mapping s.t. it can be converted to JSON and similar formats."""
        # yapf: disable
        result = collections.OrderedDict([
            ("requirements",
             collections.OrderedDict((key, req.to_mapping()) for key, req in sorted(self.requirements.items()))),
            ("rel_paths", sorted(rel_pth.as_posix() for rel_pth in self.rel_paths)),
            ("unresolved_modules", [mod.to_mapping() for mod in self.unresolved_modules])
        ])
        # yapf: enable

        return result


_STDLIB_SET = set(stdlib_list.stdlib_list())


@icontract.require(lambda rel_paths: all(not rel_pth.is_absolute() for rel_pth in rel_paths))
@icontract.ensure(
    lambda rel_paths, result: all(pth in result.rel_paths for pth in rel_paths),
    enabled=icontract.SLOW or READTHEDOCS,
    description="Initial relative paths included")
@icontract.ensure(
    lambda requirements, result: all(req.name in requirements for req in result.requirements.values()),
    enabled=icontract.SLOW or READTHEDOCS)
@icontract.require(
    lambda requirements, module_to_requirement: missing_requirements(module_to_requirement, requirements) == [],
    enabled=icontract.SLOW or READTHEDOCS)
def collect_dependency_graph(root_dir: pathlib.Path, rel_paths: List[pathlib.Path],
                             requirements: Mapping[str, Requirement],
                             module_to_requirement: Mapping[str, str]) -> Package:
    """
    Collect the dependency graph of the initial set of python files from the code base.

    :param root_dir: root directory of the codebase such as ``/home/marko/workspace/pqry/production/src/py``
    :param rel_paths: initial set of python files that we want to package. These paths are relative to root_dir.
    :param requirements: requirements of the whole code base, mapped by package name
    :param module_to_requirement: module to requirement correspondence of the whole code base
    :return: resolved depedendency graph including the given initial relative paths,
    """
    package = Package()

    stack = []  # type: List[pathlib.Path]

    stack.extend(rel_paths)

    unresolved_module_set = set()  # type: Set[str]

    while stack:
        rel_pth = stack.pop()
        assert not rel_pth.is_absolute(), "All visited paths must be relative."

        len_rel_paths_before = len(package.rel_paths)

        # Do not revisit already visited paths to avoid re-parsing.
        if rel_pth in package.rel_paths:
            continue

        pth = root_dir / rel_pth

        mfder = modulefinder.ModuleFinder(path=[root_dir.as_posix()])
        mfder.load_file(pathname=pth.as_posix())

        for module_name in mfder.badmodules:
            if module_name in module_to_requirement:
                req_name = module_to_requirement[module_name]

                if req_name not in package.requirements:
                    package.requirements[req_name] = requirements[req_name]

            elif module_name in _STDLIB_SET:
                # Ignore the module from a standard library
                pass

            else:
                if module_name not in unresolved_module_set:
                    unresolved_module_set.add(module_name)
                    package.unresolved_modules.append(UnresolvedModule(name=module_name, importer_rel_path=rel_pth))

        for module_name, module in mfder.modules.items():
            if module.__file__ is None:
                # Some of the standard library modules may have __file__ unset. Just ignore them, but panic for all the
                # other modules.
                if module_name not in _STDLIB_SET:
                    raise AssertionError(
                        "Expected the module found through modulefiner to have a __file__, but it is None: {}".format(
                            module))
            else:
                module_rel_pth = pathlib.Path(module.__file__).relative_to(root_dir)
                stack.append(module_rel_pth)

                package.rel_paths.add(rel_pth)

        assert len_rel_paths_before + 1 == len(package.rel_paths), "Expected to add only one dependency at a step."

    return package


@icontract.require(lambda table: not table or all(len(row) == len(table[0]) for row in table))
@icontract.ensure(lambda table, result: result == "" if not table else True)
@icontract.ensure(lambda result: not result.endswith("\n"))
def _format_table(table: List[List[str]]) -> str:
    """
    Format the table as equal-spaced columns.

    :param table: rows of cells
    :return: table as string
    """
    cols = len(table[0])

    col_widths = [max(len(row[i]) for row in table) for i in range(cols)]

    lines = []  # type: List[str]
    for i, row in enumerate(table):
        parts = []  # type: List[str]

        for cell, width in zip(row, col_widths):
            parts.append(cell.ljust(width))

        line = " | ".join(parts)
        lines.append(line)

        if i == 0:
            border = []  # type: List[str]

            for width in col_widths:
                border.append("-" * width)

            lines.append("-+-".join(border))

    result = "\n".join(lines)

    return result


def _output_verbose(package: Package, out: TextIO = sys.stdout) -> None:
    """
    Output the dependency graph in a human-readable format.

    :param package: dependency graph to be output
    :param out: output stream
    """
    blocks = []  # type: List[str]

    if package.requirements:
        table = [["Package name", "Requirement spec"]]  # type: List[List[str]]
        for _, req in sorted(package.requirements.items()):
            table.append([req.name, repr(req.line.strip())])

        blocks.append("External dependencies:\n{}".format(_format_table(table=table)))

    if package.rel_paths:
        local_block = ["Local dependencies:"]
        for rel_pth in sorted(package.rel_paths):
            local_block.append("{}".format(rel_pth))

        blocks.append("\n".join(local_block))

    if package.unresolved_modules:
        table = [["Module", "Imported from"]]
        for mod in sorted(package.unresolved_modules, key=lambda mod: mod.name):
            table.append([mod.name, mod.imported_from.as_posix()])

        blocks.append("Unresolved dependencies:\n{}".format(_format_table(table=table)))

    out.write("\n\n".join(blocks))
    out.write("\n")


FORMATS = ['verbose', 'json']


@icontract.require(lambda a_format: a_format in FORMATS if a_format is not None else True)
def output(package: Package, out: TextIO = sys.stdout, a_format: str = 'verbose') -> None:
    """
    Output the dependency graph in the given format.

    If no format is set, the verbose format (i.e. with best readability) is chosen by default.

    :param package: dependency graph to be output
    :param out: stream where to output the dependency graphas string
    :param a_format: format of the output (e.g., "json")
    """
    if a_format == 'verbose':
        _output_verbose(package=package, out=out)
    elif a_format == 'json':
        json.dump(obj=package.to_mapping(), fp=out, indent=2)
    else:
        raise ValueError("Unexpected format: {!r}".format(a_format))
