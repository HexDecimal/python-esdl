#!/usr/bin/env python3
import os
import sys

import re
import platform
import io
import shutil
import subprocess
from typing import Dict, List, Tuple, Any, Optional
import warnings
import zipfile

import cffi  # type: ignore
import pcpp  # type: ignore

try:
    from urllib import urlretrieve  # type: ignore
except ImportError:
    from urllib.request import urlretrieve

BITSIZE, LINKAGE = platform.architecture()

# The SDL2 version to parse and export symbols from.
SDL2_PARSE_VERSION = os.environ.get("SDL_VERSION", "2.0.5")
# The SDL2 version to include in binary distributions.
SDL2_BUNDLE_VERSION = os.environ.get("SDL_VERSION", "2.0.12")


# Used to remove excessive newlines in debug outputs.
RE_NEWLINES = re.compile(r"\n\n+")
# Functions using va_list need to be culled.
RE_VAFUNC = re.compile(r"^.*?\([^()]*va_list[^()]*\);$", re.MULTILINE)
# Static inline functions need to be culled.
RE_INLINE = re.compile(r"^static inline.*?^}$", re.MULTILINE | re.DOTALL)
# Most SDL_PIXELFORMAT names need their values scrubbed.
RE_PIXELFORMAT = re.compile(r"(?P<name>SDL_PIXELFORMAT_\w+) =[^,}]*")
# Most SDLK names need their values scrubbed.
RE_SDLK = re.compile(r"(?P<name>SDLK_\w+) =.*?(?=,\n|}\n)")
# Remove compile time assertions from the cdef.
RE_ASSERT = re.compile(r"^.*SDL_compile_time_assert.*$", re.MULTILINE)


def check_sdl_version() -> None:
    """Check the local SDL version on Linux distributions."""
    if not sys.platform.startswith("linux"):
        return
    needed_version = SDL2_PARSE_VERSION
    SDL_VERSION_NEEDED = tuple(int(n) for n in needed_version.split("."))
    try:
        sdl_version_str = subprocess.check_output(
            ["sdl2-config", "--version"], universal_newlines=True
        ).strip()
    except FileNotFoundError:
        raise RuntimeError(
            "libsdl2-dev or equivalent must be installed on your system"
            " and must be at least version %s."
            "\nsdl2-config must be on PATH." % (needed_version,)
        )
    print("Found SDL %s." % (sdl_version_str,))
    sdl_version = tuple(int(s) for s in sdl_version_str.split("."))
    if sdl_version < SDL_VERSION_NEEDED:
        raise RuntimeError(
            "SDL version must be at least %s, (found %s)"
            % (needed_version, sdl_version_str)
        )


def get_sdl2_file(version: str) -> str:
    """Return the path to an SDL2 binary archive, downloadin it if needed."""
    if sys.platform == "win32":
        sdl2_file = "SDL2-devel-%s-VC.zip" % (version,)
    else:
        assert sys.platform == "darwin"
        sdl2_file = "SDL2-%s.dmg" % (version,)
    sdl2_local_file = os.path.join("dependencies", sdl2_file)
    sdl2_remote_file = "https://www.libsdl.org/release/%s" % sdl2_file
    if not os.path.exists(sdl2_local_file):
        print("Downloading %s" % sdl2_remote_file)
        os.makedirs("dependencies/", exist_ok=True)
        print(sdl2_remote_file)
        urlretrieve(sdl2_remote_file, sdl2_local_file)
    return sdl2_local_file


def unpack_sdl2(version: str) -> str:
    """Return the path to an SDL binary folder."""
    sdl2_path = "dependencies/SDL2-%s" % (version,)
    sdl2_dir = ""
    if sys.platform == "darwin":
        sdl2_dir = sdl2_path
        sdl2_path += "/SDL2.framework"
    if os.path.exists(sdl2_path):
        return sdl2_path
    sdl2_arc = get_sdl2_file(version)
    print("Extracting %s" % sdl2_arc)
    if sdl2_arc.endswith(".zip"):
        with zipfile.ZipFile(sdl2_arc) as zf:
            zf.extractall("dependencies/")
    else:
        assert sdl2_arc.endswith(".dmg")
        subprocess.check_call(["hdiutil", "mount", sdl2_arc])
        subprocess.check_call(["mkdir", "-p", sdl2_dir])
        subprocess.check_call(
            ["cp", "-r", "/Volumes/SDL2/SDL2.framework", sdl2_dir]
        )
        subprocess.check_call(["hdiutil", "unmount", "/Volumes/SDL2"])
    return sdl2_path


class SDLParser(pcpp.Preprocessor):  # type: ignore
    """A modified preprocessor to output code in a format for CFFI."""

    def __init__(self) -> None:
        super().__init__()
        # Extra tracked strings.
        self.tracked_strings = {}  # type: Dict[str, str]
        self.line_directive = None  # Don't output line directives.

    def get_output(self) -> Tuple[str, str]:
        """Return this objects current tokens as strings.

        This returns two strings since the 2nd will have warnings to suppress.
        """
        with io.StringIO() as buffer:
            self.write(buffer)
            main_out = buffer.getvalue()
        # Append tracked_strings to the extra output.
        extra_out = ""
        for name, value in self.tracked_strings.items():
            extra_out += "static const char %s[] = %s;\n" % (name, value)
        return main_out, extra_out

    @staticmethod
    def scrub_tokens(toks: List[Any]) -> None:
        """Scrub the tokens from a directive so that CFFI can parse it better."""
        assert toks[0].type == "CPP_ID"  # toks[0] is the symbol.
        assert toks[1].type == "CPP_WS"  # toks[1] is whitespace/
        # Replace toks[2] with a "..." constant.
        toks[2].type = "CPP_ID"
        toks[2].value = "..."
        # Replace anything after that with whitespace.
        for tok in toks[3:]:
            tok.type = "CPP_WS"
            tok.value = " "

    def on_directive_handle(
        self,
        directive: Any,
        toks: List[Any],
        ifpassthru: bool,
        precedingtoks: List[Any],
    ) -> Optional[bool]:
        """Trys to track some specific #define directives."""
        super().on_directive_handle(directive, toks, ifpassthru, precedingtoks)
        if directive.value == "define" and toks:
            if "SDL_HINT_" in toks[0].value:
                self.tracked_strings[toks[0].value] = toks[2].value
            elif "SDL_INIT_" in toks[0].value:
                # Keep the SDL_INIT_X flags.
                if len(toks) > 3:
                    self.scrub_tokens(toks)
                return None  # Execute and add to the output.
            elif "AUDIO_" in toks[0].value and toks[1].type != "CPP_LPAREN":
                # Keep the SDL_AUDIO_X constants, but skip macro functions.
                self.scrub_tokens(toks)
                return None
        return True  # Execute and remove from the output.

    def on_include_not_found(
        self, is_system_include: bool, curdir: str, includepath: str
    ) -> None:
        """Remove bad includes such as stddef.h and stdarg.h."""
        raise pcpp.OutputDirective(pcpp.Action.IgnoreAndRemove)


check_sdl_version()

if sys.platform in ["win32", "darwin"]:
    SDL2_PARSE_PATH = unpack_sdl2(SDL2_PARSE_VERSION)
    SDL2_BUNDLE_PATH = unpack_sdl2(SDL2_BUNDLE_VERSION)

if sys.platform == "win32":
    SDL2_INCLUDE = os.path.join(SDL2_PARSE_PATH, "include")
elif sys.platform == "darwin":
    SDL2_INCLUDE = os.path.join(SDL2_PARSE_PATH, "Versions/A/Headers")
else:
    matches = re.findall(
        r"-I(\S+)",
        subprocess.check_output(
            ["sdl2-config", "--cflags"], universal_newlines=True
        ),
    )
    assert matches

    SDL2_INCLUDE = None
    for match in matches:
        if os.path.isfile(os.path.join(match, "SDL_stdinc.h")):
            SDL2_INCLUDE = match
    assert SDL2_INCLUDE

parser = SDLParser()
parser.add_path(SDL2_INCLUDE)
parser.parse(
    """
// Remove extern keyword.
#define extern
// Ignore some SDL assert statements.
#define DOXYGEN_SHOULD_IGNORE_THIS

#define _SIZE_T_DEFINED_
typedef int... size_t;

// Skip these headers.
#define SDL_atomic_h_
#define SDL_thread_h_

#include <SDL.h>
"""
)
sdl2_cdef, sdl2_cdef_extra = parser.get_output()
sdl2_cdef = RE_VAFUNC.sub("", sdl2_cdef)
sdl2_cdef = RE_INLINE.sub("", sdl2_cdef)
sdl2_cdef = RE_PIXELFORMAT.sub(r"\g<name> = ...", sdl2_cdef)
sdl2_cdef = RE_SDLK.sub(r"\g<name> = ...", sdl2_cdef)
sdl2_cdef = RE_NEWLINES.sub("\n", sdl2_cdef)
sdl2_cdef = RE_ASSERT.sub("", sdl2_cdef)
sdl2_cdef = (
    sdl2_cdef.replace("int SDL_main(int argc, char *argv[]);", "")
    .replace("} SDL_AudioCVT;", "...;} SDL_AudioCVT;")
    .replace("typedef unsigned int uintptr_t;", "typedef int... uintptr_t;")
    .replace("typedef unsigned int size_t;", "typedef int... size_t;")
)
if os.environ.get("DEBUG_CDEF"):
    with open("sdl2_cdef.c", "w") as f:
        print(sdl2_cdef + sdl2_cdef_extra, file=f)

sdl2_cdef += "#define SDL_INIT_AUDIO ...\n"

ffi = cffi.FFI()
ffi.cdef(sdl2_cdef)
with warnings.catch_warnings():
    # Ignore warnings about string literals, they work in this call.
    warnings.filterwarnings(
        "ignore", "String literal found in cdef", UserWarning
    )
    ffi.cdef(sdl2_cdef_extra)

include_dirs = []
extra_compile_args = []
extra_link_args = []

libraries = []
library_dirs = []
define_macros = [("Py_LIMITED_API", 0x03050000)]  # type: List[Tuple[str, Any]]


if sys.platform == "darwin":
    extra_link_args += ["-framework", "SDL2"]
else:
    libraries += ["SDL2"]

# Bundle the Windows SDL2 DLL.
if sys.platform == "win32":
    include_dirs.append(SDL2_INCLUDE)
    ARCH_MAPPING = {"32bit": "x86", "64bit": "x64"}
    SDL2_LIB_DIR = os.path.join(
        SDL2_BUNDLE_PATH, "lib/", ARCH_MAPPING[BITSIZE]
    )
    library_dirs.append(SDL2_LIB_DIR)
    SDL2_LIB_DEST = os.path.join("esdl", ARCH_MAPPING[BITSIZE])
    SDL2_LIB_DEST = "esdl"
    if not os.path.exists(SDL2_LIB_DEST):
        os.mkdir(SDL2_LIB_DEST)
    shutil.copy(os.path.join(SDL2_LIB_DIR, "SDL2.dll"), SDL2_LIB_DEST)

# Link to the SDL2 framework on MacOS.
# Delocate will bundle the binaries in a later step.
if sys.platform == "darwin":
    HEADER_DIR = os.path.join(SDL2_PARSE_PATH, "Headers")
    include_dirs.append(HEADER_DIR)
    extra_link_args += ["-F%s/.." % SDL2_BUNDLE_PATH]
    extra_link_args += ["-rpath", "%s/.." % SDL2_BUNDLE_PATH]
    extra_link_args += ["-rpath", "/usr/local/opt/llvm/lib/"]

# Use sdl2-config to link to SDL2 on Linux.
if sys.platform not in ["win32", "darwin"]:
    extra_compile_args += (
        subprocess.check_output(
            ["sdl2-config", "--cflags"], universal_newlines=True
        )
        .strip()
        .split()
    )
    extra_link_args += (
        subprocess.check_output(
            ["sdl2-config", "--libs"], universal_newlines=True
        )
        .strip()
        .split()
    )


ffi.set_source(
    module_name="esdl._sdl2",
    source="#include <SDL.h>",
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    libraries=libraries,
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
    define_macros=define_macros,
    py_limited_api=True,
)
