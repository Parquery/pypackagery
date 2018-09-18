pypackagery
===========

.. image:: https://api.travis-ci.com/Parquery/pypackagery.svg?branch=master
    :target: https://api.travis-ci.com/Parquery/pypackagery.svg?branch=master
    :alt: Build Status

.. image:: https://coveralls.io/repos/github/Parquery/pypackagery/badge.svg?branch=master
    :target: https://coveralls.io/github/Parquery/pypackagery?branch=master
    :alt: Coverage

.. image:: https://badge.fury.io/py/pypackagery.svg
    :target: https://pypi.org/project/pypackagery/
    :alt: PyPi

.. image:: https://img.shields.io/pypi/pyversions/pypackagery.svg
    :alt: PyPI - Python Version

.. image:: https://readthedocs.org/projects/pypackagery/badge/?version=latest
    :target: https://pypackagery.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status

Pypackagery packages a subset of a monorepo and determine the dependent packages.

Given a root directory of a Python code base, a list of Python files (from that code base) and a target directory,
pypackagery determines the dependent modules of the specified files. The scripts and the *local* dependencies are copied
to the given target directory. The *external* dependencies (such as pypi packages) are not copied
(and need not be installed), but the list containing a subset of external dependencies is generated instead.

The external dependencies of the monorepo need to be specified in
``<root directory>/requirements.txt`` and ``<root directory>/module_to_requirement.tsv``.

The ``requirements.txt`` follows the Pip format
(see `pip documentation <https://pip.pypa.io/en/stable/user_guide/#id1>`_). The file defines which external packages are
needed by the *whole* of the code base. Pypackagery will read this list and extract the subset needed by the specified
Python files.

``module_to_requirement.tsv`` defines the correspondence between Python modules and requirements as defined in
``requirements.txt``. This correspondence needs to be manually defined since there is no way to automatically map
Python modules to pip packages. The correspondance in ``module_to_requirement.tsv`` is given as
lines of two tab-separated values. The first column is the full model name (such as ``PIL.Image``) and the second is
the name of the package in ``requirements.txt`` (such as ``pillow``). The version of the package should be omitted and
should be specified *only* in the ``requirements.txt``.

Please do not forget to add the ``#egg`` fragment to URLs and files in ``requirements.txt`` so that the name of the
package can be uniquely resolved when joining ``module_to_requirement.tsv`` and ``requirements.txt``.

Related Projects
================

* https://github.com/pantsbuild/pex -- a library tool for generating PEX (Python EXecutable) files. It packages all the
  files in the virtual environment including all the requirements. This works for small code bases and light
  requirements which are not frequently re-used among the components in the code base. However, when the requirements
  are heavy (such as OpenCV or numpy) and frequently re-used in the code base, it is a waste of bandwidth and disk space
  to package them repeatedly for each executable independently.

* https://www.pantsbuild.org/, https://buckbuild.com/ and https://github.com/linkedin/pygradle are build systems that
  can produce PEX files (with all the problems mentioned above). We considered using them and writing a plug-in to
  achieve the same goal as pypackagery. Finally, we decided for a separate tool since these build systems are not
  yet supported natively by IDEs (such as Pycharm) and actually break the expected Python development work flow.

* https://blog.shazam.com/python-microlibs-5be9461ad979 presents a microlib approach where a monorepo is packaged in
  separate pip packages. While we find the idea interesting, it adds an administration overhead since every library
  needs to live in a separate package thus making bigger refactorings tedious and error-prone (*e.g.* are the
  requirements updated correctly and are dependency conflicts reported early?). We found it easiest to have a global
  list of the requirements (with modules mapped to requirements), so that a sole ``pip3 install -r requirements.txt``
  would notify us of the conflicts.

  If you wanted to work only on part of the code base, and do no want to install all the requirements, you can use
  pypackagery to determine the required subset and install only those requirements that you need.

  Since we deploy often on third-party sites, we also found it difficult to secure our deployments. Namely, packaging
  the code base into microlibs practically implies that we need to give the remote machine access to our private pypi
  repository. In case that we only want to deploy the subset of the code base, granting access to all packages would
  unnecessarily open up a potential security hole. With pypackagery, we deploy only the files that are actually
  used while the third-party dependencies are separately installed on the remote instance from a subset of requirements
  ``subrequirements.txt`` with ``pip3 install -r subrequirements.txt``.


Usage
=====
Requirement Specification
-------------------------
As already mentioned, the requirements are expected to follow Pip format
(see `pip documentation <https://pip.pypa.io/en/stable/user_guide/#id1>`_) and live in ``requirements.txt`` at the root
of the code base. The mapping from modules to requirements is expected in ``module_to_requirement.tsv`` also at the root
of the code base.

Assume that the code base lives in ``~/workspace/pqry/production/src/py``.

Here is an excerpt from ``~/workspace/pqry/production/src/py/requirements.txt``:

.. code-block::

    pillow==5.2.0
    pytz==2018.5
    pyzmq==17.1.2

And here is an excerpt from ``~/workspace/pqry/production/src/py/module_to_requirement.tsv``
(mind that it's tab separated):

.. code-block::

    PIL	pillow
    PIL.Image	pillow
    PIL.ImageFile	pillow
    PIL.ImageOps	pillow
    PIL.ImageStat	pillow
    PIL.ImageTk	pillow
    cv2	opencv-python

Directory
---------
Assume that the code base lives in ``~/workspace/pqry/production/src/py`` and we are interested to bundle everything
in ``pipeline/out`` directory.

To determine the subset of the files and requirements, run the following command line:


.. code-block:: bash

    pypackagery \
        --root_dir ~/workspace/pqry/production/src/py \
        --initial_set ~/workspace/pqry/production/src/py/pipeline/out

This gives us a verbose, human-readable output like:

.. code-block::

    External dependencies:
    Package name | Requirement spec
    -------------+---------------------
    pyzmq        | 'pyzmq==17.1.2'
    temppathlib  | 'temppathlib==1.0.3'

    Local dependencies:
    pipeline/out/__init__.py
    pqry/__init__.py
    pqry/logging.py
    pqry/proc.py

If we want to get the same output in JSON, we need to call:

.. code-block:: bash

    pypackagery \
        --root_dir ~/workspace/pqry/production/src/py \
        --initial_set ~/workspace/pqry/production/src/py/pipeline/out \
        --format json

which gives us a JSON-encoded dependency graph:

.. code-block:: json

    {
      "requirements": {
        "pyzmq": {
          "name": "pyzmq",
          "line": "pyzmq==17.1.2\n"
        },
        "temppathlib": {
          "name": "temppathlib",
          "line": "temppathlib==1.0.3\n"
        }
      },
      "rel_paths": [
        "pipeline/out/__init__.py",
        "pqry/__init__.py",
        "pqry/logging.py",
        "pqry/proc.py"
      ],
      "unresolved_modules": []
    }

Files
-----
Assume again that the code base lives in ``~/workspace/pqry/production/src/py``. We would like to get a subset of the
code base required by a list of scripts. We need to specify the initial set as a list of files:

.. code-block:: bash

    pypackagery \
        --root_dir ~/workspace/pqry/production/src/py \
        --initial_set \
            ~/workspace/pqry/production/src/py/pipeline/input/receivery.py \
            ~/workspace/pqry/production/src/py/pipeline/input/snapshotry.py

which gives us:

.. code-block::

    External dependencies:
    Package name | Requirement spec
    -------------+-------------------
    icontract    | 'icontract==1.5.1'
    pillow       | 'pillow==5.2.0'
    protobuf     | 'protobuf==3.5.1'
    pytz         | 'pytz==2018.5'
    pyzmq        | 'pyzmq==17.1.2'
    requests     | 'requests==2.19.1'

    Local dependencies:
    pipeline/__init__.py
    pipeline/input/receivery.py
    pipeline/input/snapshotry.py
    pqry/__init__.py
    pqry/img.py
    pqry/logging.py
    protoed/__init__.py
    protoed/pipeline_pb2.py

Unresolved Modules
------------------
If there is a module which could not be resolved (neither in built-ins, nor specified in the requirements nor
living in the code base), the pypackagery will return a non-zero return code.

If you specify ``--dont_panic``, the return code will be 0 even if there are unresolved modules.

Module ``packagery``
--------------------
Pypackagery provides a module ``packagery`` which can be used to programmatically determine the dependencies of the
subset of the code base. For example, this is particularly useful for deployments to a remote machine where you
want to deploy only a part of the code base depending on some given configuration.

Here is an example:

.. code-block:: python

    import pathlib

    import packagery

    root_dir = pathlib.Path('/some/codebase')

    rel_pths = [
        pathlib.Path("some/dir/file1.py"),
        pathlib.Path("some/other/dir/file2.py")]

    requirements_txt = root_dir / "requirements.txt"
    module_to_requirement_tsv = root_dir / "module_to_requirement.tsv"

    requirements = packagery.parse_requirements(
        text=requirements_txt.read_text())

    module_to_requirement = packagery.parse_module_to_requirement(
        text=module_to_requirement_tsv.read_text(),
        filename=module_to_requirement_tsv.as_posix())

    pkg = packagery.collect_dependency_graph(
        root_dir=root_dir,
        rel_paths=rel_pths,
        requirements=requirements,
        module_to_requirement=module_to_requirement)

    # do something with pkg ...

Mind that relative paths (given as ``rel_paths`` argument) all need to be files, not directories.

Documentation
=============
The documentation is available on `readthedocs <https://pypackagery.readthedocs.io/en/latest/>`_.

Installation
============

* Create a virtual environment:

.. code-block:: bash

    python3 -m venv venv3

* Activate it:

.. code-block:: bash

    source venv3/bin/activate

* Install pypackagery with pip:

.. code-block:: bash

    pip3 install pypackagery

Development
===========

* Check out the repository.

* In the repository root, create the virtual environment:

.. code-block:: bash

    python3 -m venv venv3

* Activate the virtual environment:

.. code-block:: bash

    source venv3/bin/activate

* Install the development dependencies:

.. code-block:: bash

    pip3 install -e .[dev]

We use tox for testing and packaging the distribution:

.. code-block:: bash

    tox

Pre-commit Checks
-----------------
We provide a set of pre-commit checks that lint and check code for formatting.

Namely, we use:

* `yapf <https://github.com/google/yapf>`_ to check the formatting.
* The style of the docstrings is checked with `pydocstyle <https://github.com/PyCQA/pydocstyle>`_.
* Static type analysis is performed with `mypy <http://mypy-lang.org/>`_.
* Various linter checks are done with `pylint <https://www.pylint.org/>`_.
* Doctests are executed using the Python `doctest module <https://docs.python.org/3.5/library/doctest.html>`_.

Run the pre-commit checks locally from an activated virtual environment with development dependencies:

.. code-block:: bash

    ./precommit.py

* The pre-commit script can also automatically format the code:

.. code-block:: bash

    ./precommit.py  --overwrite


Versioning
==========
We follow `Semantic Versioning <http://semver.org/spec/v1.0.0.html>`_. The version X.Y.Z indicates:

* X is the major version (backward-incompatible),
* Y is the minor version (backward-compatible), and
* Z is the patch version (backward-compatible bug fix).
