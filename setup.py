"""A setuptools based setup module.

See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""
import os

from setuptools import setup, find_packages

import pypackagery_meta

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'README.rst'), encoding='utf-8') as fid:
    long_description = fid.read().strip()  # pylint: disable=invalid-name

setup(
    name=pypackagery_meta.__title__,
    version=pypackagery_meta.__version__,
    description=pypackagery_meta.__description__,
    long_description=long_description,
    url=pypackagery_meta.__url__,
    author=pypackagery_meta.__author__,
    author_email=pypackagery_meta.__author_email__,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    license='License :: OSI Approved :: MIT License',
    keywords='package monorepo requirements',
    packages=find_packages(exclude=['tests']),
    scripts=['bin/pypackagery'],
    install_requires=['icontract>=2.0.1,<3', 'stdlib_list>=0.4.0,<1', 'requirements-parser>=0.2.0,<1'],
    extras_require={
        'dev': [
            'mypy==0.790', 'pylint==2.6.0', 'yapf==0.20.2', 'tox>=3.0.0', 'temppathlib>=1.0.3,<2', 'coverage>=4.5.1,<5',
            'pydocstyle>=2.1.1,<3'
        ]
    },
    py_modules=['packagery', 'pypackagery_meta'],
    entry_points={"console_scripts": ["pypackagery = packagery.main:main"]},
    package_data={
        "packagery": ["py.typed"],
        '': ['LICENSE.txt', 'README.rst'],
    })
