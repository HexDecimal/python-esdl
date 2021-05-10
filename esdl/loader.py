"""This module handles loading of the SDL2 FFI.
"""
import atexit
import os
import platform
import sys
from typing import Any  # noqa: F401

import cffi  # type: ignore

__sdl_version__ = ""


def get_architecture() -> str:
    """Return the Windows architecture, one of "x86" or "x64"."""
    return "x86" if platform.architecture()[0] == "32bit" else "x64"


def get_sdl_version() -> str:
    sdl_version = ffi.new("SDL_version*")
    lib.SDL_GetVersion(sdl_version)
    return "%s.%s.%s" % (
        sdl_version.major,
        sdl_version.minor,
        sdl_version.patch,
    )


class _Mock(object):
    """Mock object needed for ReadTheDocs."""

    CData = ()  # This gets passed to an isinstance call.

    @staticmethod
    def def_extern() -> Any:
        """Pass def_extern call silently."""
        return lambda func: func

    def __call__(self, *args: Any, **kargs: Any) -> Any:
        """Suppress any other calls"""
        return self

    def __str__(self) -> Any:
        """Just have ? in case anything leaks as a parameter default."""
        return "?"


lib = None  # type: Any
ffi = None  # type: Any

if os.environ.get("READTHEDOCS"):
    # Mock the lib and ffi objects needed to compile docs for readthedocs.io
    # Allows an import without building the cffi module first.
    lib = ffi = _Mock()
else:
    from esdl._sdl2 import ffi, lib  # type: ignore # noqa: F401

    atexit.register(lib.SDL_Quit)
    __sdl_version__ = get_sdl_version()

__all__ = ["ffi", "lib"]
