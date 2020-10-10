#!/usr/bin/env python
"""Test packagery."""

import io
import modulefinder
import pathlib
import unittest
from typing import Optional, cast, TextIO  # pylint: disable=unused-import

# pylint: disable=missing-docstring,too-many-public-methods
import collections
import icontract
import temppathlib

import packagery


class TestResolveInitialPaths(unittest.TestCase):
    def test_empty(self):
        self.assertListEqual([], packagery.resolve_initial_paths(initial_paths=[]))

    def test_single_file(self):
        with temppathlib.TemporaryDirectory() as tmp:
            pth = tmp.path / "some_file.py"
            pth.write_text("hello")

            self.assertListEqual([pth], packagery.resolve_initial_paths(initial_paths=[pth]))

    def test_multiple_files(self):
        with temppathlib.TemporaryDirectory() as tmp:
            pth = tmp.path / "some_file.py"
            pth.write_text("hello")

            another_pth = tmp.path / "another_file.py"
            another_pth.write_text("hello")

            self.assertListEqual([another_pth, pth], packagery.resolve_initial_paths(initial_paths=[another_pth, pth]))

    def test_directory(self):
        with temppathlib.TemporaryDirectory() as tmp:
            pth = tmp.path / "some_dir" / "some_file.py"
            pth.parent.mkdir()
            pth.write_text("hello")

            self.assertListEqual([pth], packagery.resolve_initial_paths(initial_paths=[pth.parent]))

    def test_directory_and_file(self):
        with temppathlib.TemporaryDirectory() as tmp:
            pth = tmp.path / "some_dir" / "some_file.py"
            pth.parent.mkdir()
            pth.write_text("hello")

            another_pth = tmp.path / "another_file.py"
            another_pth.write_text("hello")

            self.assertListEqual(
                [pth, another_pth], packagery.resolve_initial_paths(initial_paths=[pth.parent, another_pth]))


class TestParseRequirements(unittest.TestCase):
    def test_empty_requirements(self):
        text = ""
        reqs = packagery.parse_requirements(text=text)

        self.assertEqual(0, len(reqs))

    def test_with_comment(self):
        text = "# some comment\n  # some comment\n"
        reqs = packagery.parse_requirements(text=text)

        self.assertEqual(0, len(reqs))

    def test_without_version(self):
        text = "some_pack-age\n"

        reqs = packagery.parse_requirements(text=text)

        self.assertEqual(1, len(reqs))
        self.assertIn('some_pack-age', reqs)

        requirement = reqs["some_pack-age"]
        self.assertEqual("some_pack-age", requirement.name)
        self.assertEqual("some_pack-age\n", requirement.line)

    def test_with_pinned_version(self):
        text = "some_package12 == 1.2.3"

        reqs = packagery.parse_requirements(text=text)

        self.assertEqual(1, len(reqs))
        self.assertIn('some_package12', reqs)

        requirement = reqs['some_package12']

        self.assertEqual('some_package12', requirement.name)
        self.assertEqual("some_package12 == 1.2.3\n", requirement.line)

    def test_with_constrained_version(self):
        text = "some_package12 >=1.2.3,<2.*     "

        reqs = packagery.parse_requirements(text=text)

        self.assertEqual(1, len(reqs))
        self.assertIn('some_package12', reqs)

        requirement = reqs['some_package12']

        self.assertEqual('some_package12', requirement.name)
        self.assertEqual("some_package12 >=1.2.3,<2.*\n", requirement.line)

    def test_with_comment_on_the_same_line(self):  # pylint: disable=invalid-name
        text = "some_package # some comment"
        reqs = packagery.parse_requirements(text=text)

        self.assertEqual(1, len(reqs))
        self.assertIn('some_package', reqs)

        requirement = reqs['some_package']

        self.assertEqual('some_package', requirement.name)
        self.assertEqual("some_package # some comment\n", requirement.line)

    def test_with_whitespace(self):
        text = "    some_package    "
        reqs = packagery.parse_requirements(text=text)

        self.assertEqual(1, len(reqs))
        self.assertIn('some_package', reqs)

        requirement = reqs['some_package']

        self.assertEqual('some_package', requirement.name)
        self.assertEqual("some_package\n", requirement.line)

    def test_multiple(self):
        text = "some_package\nanother_package==1.2"
        reqs = packagery.parse_requirements(text=text)

        self.assertEqual(2, len(reqs))
        self.assertIn('some_package', reqs)
        self.assertIn('another_package', reqs)

        requirement1 = reqs['some_package']

        self.assertEqual('some_package', requirement1.name)
        self.assertEqual("some_package\n", requirement1.line)

        requirement2 = reqs['another_package']

        self.assertEqual('another_package', requirement2.name)
        self.assertEqual("another_package==1.2\n", requirement2.line)

    def test_url(self):
        url = "http://download.pytorch.org/whl/cpu/torch-0.3.1-cp35-cp35m-linux_x86_64.whl#egg=torch"
        text = "{}\n".format(url)

        reqs = packagery.parse_requirements(text=text)

        self.assertEqual(1, len(reqs))
        self.assertIn("torch", reqs)

        requirement = reqs["torch"]

        self.assertEqual("torch", requirement.name)
        self.assertEqual("http://download.pytorch.org/whl/cpu/torch-0.3.1-cp35-cp35m-linux_x86_64.whl#egg=torch\n",
                         requirement.line)

    def test_without_name(self):
        url = "http://download.pytorch.org/whl/cpu/torch-0.3.1-cp35-cp35m-linux_x86_64.whl"  # no egg fragment
        text = "{}\n".format(url)

        value_error = None  # type: Optional[ValueError]

        try:
            packagery.parse_requirements(text=text, filename="/some/requirements.txt")
        except ValueError as err:
            value_error = err

        self.assertIsNotNone(value_error)
        self.assertEqual("The name is missing in the requirement from the file /some/requirements.txt: "
                         "http://download.pytorch.org/whl/cpu/torch-0.3.1-cp35-cp35m-linux_x86_64.whl "
                         "(did you specify the egg fragment?)", str(value_error))

    def test_invalid(self):
        text = "//wrong"

        value_error = None  # type: Optional[ValueError]
        try:
            packagery.parse_requirements(text=text, filename="/some/path/requirements.txt")
        except ValueError as err:
            value_error = err

        self.assertIsNotNone(value_error)
        self.assertEqual("Invalid requirements in file /some/path/requirements.txt", str(value_error))


class TestParseModuleToRequirement(unittest.TestCase):
    def test_empty(self):
        mod_to_req = packagery.parse_module_to_requirement(text="")

        self.assertEqual(0, len(mod_to_req))

    def test_single(self):
        mod_to_req = packagery.parse_module_to_requirement(text="PIL.Image\tpillow")

        self.assertDictEqual({"PIL.Image": "pillow"}, mod_to_req)

    def test_multiple(self):
        mod_to_req = packagery.parse_module_to_requirement(text=("PIL.Image\tpillow\n" "PIL\tpillow\n"))

        self.assertDictEqual({"PIL.Image": "pillow", "PIL": "pillow"}, mod_to_req)

    def test_invalid(self):
        # Put a space instead of a tab

        value_error = None  # Optional[ValueError]
        try:
            packagery.parse_module_to_requirement(text="PIL.Image pillow\n")
        except ValueError as err:
            value_error = err

        self.assertIsNotNone(value_error)
        self.assertEqual("Expected two columns, but got 1 on line 1 in <unknown>: ['PIL.Image pillow']",
                         str(value_error))


class TestMissingRequirements(unittest.TestCase):
    def test_empty(self):
        self.assertListEqual([], packagery.missing_requirements(module_to_requirement={}, requirements={}))

    def test_that_it_works(self):
        # yapf: disable
        module_to_requirement = collections.OrderedDict([("some_module", "some_missing_package"),
                                                         ("another_module", "some_package")])
        # yapf: enable

        requirements = packagery.parse_requirements("some_package\nsome_unused_package")

        missing = packagery.missing_requirements(module_to_requirement=module_to_requirement, requirements=requirements)

        self.assertListEqual(['some_missing_package'], missing)


class TestModuleFinder(unittest.TestCase):
    def test_duplicate_imports(self):
        with temppathlib.TemporaryDirectory() as tmp:
            script_pth = tmp.path / "some_script.py"
            script_pth.write_text("#!/usr/bin/env python\n" "import os.path\n" "import os.path\n")

            mfder = modulefinder.ModuleFinder(path=[str(tmp.path)])
            mfder.load_file(pathname=str(script_pth))

            bad_modules = sorted(mfder.badmodules.keys())
            modules = sorted(mfder.modules.keys())

            self.assertListEqual(['os.path'], bad_modules)
            self.assertListEqual(['some_script'], modules)


class TestCollectDependencyGraph(unittest.TestCase):
    def test_pip_dependency(self):
        with temppathlib.TemporaryDirectory() as tmp:
            script_pth = tmp.path / "some_script.py"
            script_pth.write_text("#!/usr/bin/env python\n" "import PIL.Image\n")

            requirements = packagery.parse_requirements(text="pillow==5.2.0\n")

            module_to_requirement = packagery.parse_module_to_requirement(text="PIL.Image\tpillow")

            pkg = packagery.collect_dependency_graph(
                root_dir=tmp.path,
                rel_paths=[pathlib.Path("some_script.py")],
                requirements=requirements,
                module_to_requirement=module_to_requirement)

            self.assertListEqual([], pkg.unresolved_modules)

            self.assertListEqual(["pillow"], list(pkg.requirements.keys()))
            self.assertSetEqual({pathlib.Path("some_script.py")}, pkg.rel_paths)

    def test_local_dependency_without_init(self):  # pylint: disable=invalid-name
        with temppathlib.TemporaryDirectory() as tmp:
            script_pth = tmp.path / "some_script.py"
            script_pth.write_text("#!/usr/bin/env python\nimport some_module.something\n")

            module_pth = tmp.path / "some_module/something.py"
            module_pth.parent.mkdir()
            (tmp.path / "some_module/__init__.py").write_text("'''hello'''\n")
            module_pth.write_text("#!/usr/bin/env python\n'''hello'''\n")

            pkg = packagery.collect_dependency_graph(
                root_dir=tmp.path,
                rel_paths=[pathlib.Path("some_script.py")],
                requirements={},
                module_to_requirement={})

            self.assertListEqual([], pkg.unresolved_modules)

            self.assertSetEqual({
                pathlib.Path("some_script.py"),
                pathlib.Path("some_module/something.py"),
                pathlib.Path("some_module/__init__.py")
            }, pkg.rel_paths)

    def test_local_dependency_with_init(self):
        with temppathlib.TemporaryDirectory(dont_delete=True) as tmp:
            script_pth = tmp.path / "some_script.py"
            script_pth.write_text("#!/usr/bin/env python\nimport mapried.config\n")

            module_pth = tmp.path / "mapried/config/__init__.py"
            module_pth.parent.mkdir(parents=True)
            module_pth.write_text("#!/usr/bin/env python\n")

            (tmp.path / "mapried/__init__.py").write_text("#!/usr/bin/env python\n")

            pkg = packagery.collect_dependency_graph(
                root_dir=tmp.path,
                rel_paths=[pathlib.Path("some_script.py")],
                requirements={},
                module_to_requirement={})

            self.assertListEqual([], pkg.unresolved_modules)

            self.assertSetEqual({
                pathlib.Path("some_script.py"),
                pathlib.Path("mapried/__init__.py"),
                pathlib.Path("mapried/config/__init__.py")
            }, pkg.rel_paths)

    def test_builtin_without_file(self):
        with temppathlib.TemporaryDirectory() as tmp:
            script_pth = tmp.path / "some_script.py"
            script_pth.write_text("#!/usr/bin/env python\n\n" "import sys\n")

            pkg = packagery.collect_dependency_graph(
                root_dir=tmp.path,
                rel_paths=[pathlib.Path("some_script.py")],
                requirements=dict(),
                module_to_requirement=dict())

            self.assertListEqual([], pkg.unresolved_modules)

            self.assertListEqual([], list(pkg.requirements.keys()))
            self.assertSetEqual({pathlib.Path("some_script.py")}, pkg.rel_paths)

    def test_builtin_local_pip_dependencies(self):  # pylint: disable=invalid-name
        with temppathlib.TemporaryDirectory() as tmp:
            script_pth = tmp.path / "some_script.py"
            script_pth.write_text("#!/usr/bin/env python\n\n"
                                  "import sys\n\n"
                                  "import PIL.Image\n\n"
                                  "import something_local\n")

            module_pth = tmp.path / "something_local.py"
            module_pth.write_text("#!/usr/bin/env python\n")

            requirements = packagery.parse_requirements(text="pillow==5.2.0\n")

            module_to_requirement = packagery.parse_module_to_requirement(text="PIL.Image\tpillow")

            pkg = packagery.collect_dependency_graph(
                root_dir=tmp.path,
                rel_paths=[pathlib.Path("some_script.py")],
                requirements=requirements,
                module_to_requirement=module_to_requirement)

            self.assertListEqual([], pkg.unresolved_modules)

            self.assertListEqual(["pillow"], list(pkg.requirements.keys()))
            self.assertSetEqual({pathlib.Path("some_script.py"), pathlib.Path("something_local.py")}, pkg.rel_paths)

    def test_transitivity(self):
        with temppathlib.TemporaryDirectory() as tmp:
            script_pth = tmp.path / "some_script.py"
            script_pth.write_text("#!/usr/bin/env python\n\n" "import something_local\n")

            module_pth = tmp.path / "something_local.py"
            module_pth.write_text("#!/usr/bin/env python\n"
                                  "import unittest\n"
                                  "import PIL.Image\n"
                                  "import something_else_local")

            another_module_pth = tmp.path / "something_else_local.py"
            another_module_pth.write_text("#!/usr/bin/env python\n")

            requirements = packagery.parse_requirements(text="pillow==5.2.0\n")

            module_to_requirement = packagery.parse_module_to_requirement(text="PIL.Image\tpillow")

            pkg = packagery.collect_dependency_graph(
                root_dir=tmp.path,
                rel_paths=[pathlib.Path("some_script.py")],
                requirements=requirements,
                module_to_requirement=module_to_requirement)

            self.assertListEqual([], pkg.unresolved_modules)

            self.assertListEqual(["pillow"], list(pkg.requirements.keys()))
            self.assertSetEqual({
                pathlib.Path("some_script.py"),
                pathlib.Path("something_local.py"),
                pathlib.Path("something_else_local.py")
            }, pkg.rel_paths)

    def test_missing_module(self):
        with temppathlib.TemporaryDirectory() as tmp:
            script_pth = tmp.path / "some_script.py"
            script_pth.write_text("#!/usr/bin/env python\n\n" "import missing\n")

            pkg = packagery.collect_dependency_graph(
                root_dir=tmp.path,
                rel_paths=[pathlib.Path("some_script.py")],
                requirements={},
                module_to_requirement={})

            self.assertListEqual(
                [packagery.UnresolvedModule(name="missing", importer_rel_path=pathlib.Path("some_script.py")).__dict__],
                [unresolved_module.__dict__ for unresolved_module in pkg.unresolved_modules])


@icontract.ensure(
    lambda result: len(result.requirements) > 0 and len(result.rel_paths) > 0 and len(result.unresolved_modules) > 0)
def generate_package_with_local_pip_and_missing_deps() -> packagery.Package:  # pylint: disable=invalid-name
    with temppathlib.TemporaryDirectory() as tmp:
        script_pth = tmp.path / "some_script.py"
        script_pth.write_text("#!/usr/bin/env python\n\n"
                              "import PIL.Image\n\n"
                              "import something_local\n"
                              "import something_missing\n")

        module_pth = tmp.path / "something_local.py"
        module_pth.write_text("#!/usr/bin/env python\n")

        requirements = packagery.parse_requirements(text="pillow==5.2.0\n")

        module_to_requirement = packagery.parse_module_to_requirement(text="PIL.Image\tpillow")

        pkg = packagery.collect_dependency_graph(
            root_dir=tmp.path,
            rel_paths=[pathlib.Path("some_script.py")],
            requirements=requirements,
            module_to_requirement=module_to_requirement)

        return pkg


class TestOutput(unittest.TestCase):
    # pylint: disable=protected-access
    def test_format_table(self):
        table = [['column 0', 'another column 1'], ['00', '01'], ['10', '11']]

        result = packagery._format_table(table=table)

        self.assertEqual('column 0 | another column 1\n'
                         '---------+-----------------\n'
                         '00       | 01              \n'
                         '10       | 11              ', result)

    def test_verbose(self):
        pkg = generate_package_with_local_pip_and_missing_deps()

        buf = io.StringIO()
        packagery.output(package=pkg, out=cast(TextIO, buf), a_format='verbose')

        self.assertEqual("External dependencies:\n"
                         "Package name | Requirement spec\n"
                         "-------------+-----------------\n"
                         "pillow       | 'pillow==5.2.0' \n"
                         "\n"
                         "Local dependencies:\n"
                         "some_script.py\n"
                         "something_local.py\n"
                         "\n"
                         "Unresolved dependencies:\n"
                         "Module            | Imported from \n"
                         "------------------+---------------\n"
                         "something_missing | some_script.py\n", buf.getvalue())

    def test_json(self):
        pkg = generate_package_with_local_pip_and_missing_deps()

        buf = io.StringIO()
        packagery.output(package=pkg, out=cast(TextIO, buf), a_format='json')

        self.assertEqual('{\n'
                         '  "requirements": {\n'
                         '    "pillow": {\n'
                         '      "name": "pillow",\n'
                         '      "line": "pillow==5.2.0\\n"\n'
                         '    }\n'
                         '  },\n'
                         '  "rel_paths": [\n'
                         '    "some_script.py",\n'
                         '    "something_local.py"\n'
                         '  ],\n'
                         '  "unresolved_modules": [\n'
                         '    {\n'
                         '      "name": "something_missing",\n'
                         '      "imported_from": "some_script.py"\n'
                         '    }\n'
                         '  ]\n'
                         '}', buf.getvalue())


if __name__ == '__main__':
    unittest.main()
