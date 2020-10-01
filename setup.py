#!/usr/bin/env python3
import sys

from setuptools import setup

from subprocess import check_output
import platform
import warnings


def get_version():
    """Get the current version from a git tag, or by reading version.py"""
    try:
        tag = check_output(
            ["git", "describe", "--abbrev=0"], universal_newlines=True
        ).strip()
        assert not tag.startswith("v")
        version = tag

        # add .devNN if needed
        log = check_output(
            ["git", "log", "%s..HEAD" % tag, "--oneline"],
            universal_newlines=True,
        )
        commits_since_tag = log.count("\n")
        if commits_since_tag:
            version += ".dev%i" % commits_since_tag

        # update esdl/version.py
        open("esdl/version.py", "w").write('__version__ = "%s"\n' % version)
        return version
    except:
        try:
            exec(open("esdl/version.py").read(), globals())
            return __version__
        except FileNotFoundError:
            warnings.warn(
                "Unknown version: "
                "Not in a Git repository and not from a sdist bundle or wheel."
            )
            return "0.0.0"


is_pypy = platform.python_implementation() == "PyPy"


def get_package_data():
    """get data files which will be included in the package directory"""
    files = ["py.typed"]
    if sys.platform == "win32":
        files += ["SDL2.dll"]
    if sys.platform == "darwin":
        files += ["SDL2.framework/Versions/A/SDL2"]
    return files


def get_long_description():
    """Return this projects description."""
    with open("README.md", "r") as f:
        readme = f.read()
    with open("CHANGELOG.md", "r") as f:
        changelog = f.read()
        changelog = changelog.replace("## [Unreleased]\n", "")
    return "\n".join([readme, changelog])


setup(
    name="esdl",
    version=get_version(),
    author="Kyle Benesch",
    author_email="4b796c65+esdl@gmail.com",
    description="An extendable SDL2 wrapper.",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/libtcod/python-esdl",
    packages=["esdl"],
    package_data={"esdl": get_package_data()},
    python_requires=">=3.5",
    install_requires=[
        "numpy>=1.10; platform.python_implementation != 'PyPy'",
    ],
    cffi_modules=["build_sdl2.py:ffi"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        # "Development Status :: 5 - Production/Stable",
        "Environment :: Win32 (MS Windows)",
        "Environment :: MacOS X",
        "Environment :: X11 Applications",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: zlib/libpng License",
        "Natural Language :: English",
        "Operating System :: POSIX",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Topic :: Games/Entertainment",
        "Topic :: Multimedia :: Graphics",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords="SDL SDL2 cffi ffi",
    platforms=["Windows", "MacOS", "Linux"],
    license="zlib/libpng License",
)
