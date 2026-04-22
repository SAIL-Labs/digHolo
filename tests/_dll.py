"""Shared ctypes setup for the regression-test scripts.

Both ``generate_references.py`` and ``validate_references.py`` need to load
the digHolo shared library and declare the same C-ABI signatures. Keeping
the boilerplate here avoids the two scripts drifting out of sync.

The library path is resolved in this order:
1. ``--lib PATH`` on the script's command line (handled by the caller)
2. ``DIGHOLO_LIB`` environment variable
3. Auto-discovery under ``build/<preset>/`` for the current platform
4. Legacy ``bin/Win64/digHolo.dll`` (for parity with the original generator)
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import CDLL, POINTER, c_float, c_int, c_void_p
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent


def _platform_lib_names() -> list[str]:
    if sys.platform == "win32":
        return ["digholo.dll", "digHolo.dll", "libdigholo.dll"]
    if sys.platform == "darwin":
        return ["libdigholo.dylib", "libdigholo.1.dylib"]
    return ["libdigholo.so", "libdigholo.so.1"]


def _candidate_build_dirs() -> list[Path]:
    """Build-output directories to search, in priority order."""
    build_root = REPO_ROOT / "build"
    if sys.platform == "win32":
        presets = ["windows-release", "windows-ninja"]
        # MSBuild generators put the binary under build/<preset>/Release/.
        return [build_root / p / "Release" for p in presets] + [build_root / p for p in presets]
    if sys.platform == "darwin":
        return [build_root / "macos-release", build_root / "macos-debug"]
    return [build_root / "linux-release", build_root / "linux-debug"]


def find_library() -> Optional[Path]:
    env = os.environ.get("DIGHOLO_LIB")
    if env:
        p = Path(env)
        return p if p.exists() else None

    for d in _candidate_build_dirs():
        for name in _platform_lib_names():
            cand = d / name
            if cand.exists():
                return cand

    legacy = REPO_ROOT / "bin" / "Win64" / "digHolo.dll"
    if legacy.exists():
        return legacy

    return None


def load_dll(lib_path: Optional[Path] = None) -> CDLL:
    """Load the digHolo shared library and apply argtypes/restypes.

    Raises SystemExit if the library can't be located. Pass an explicit
    ``lib_path`` to override the search; otherwise ``find_library()`` is
    used.
    """
    if lib_path is None:
        lib_path = find_library()
    if lib_path is None or not Path(lib_path).exists():
        searched = [str(d) for d in _candidate_build_dirs()]
        sys.exit(
            "ERROR: digHolo shared library not found.\n"
            f"  Set DIGHOLO_LIB or pass --lib PATH.\n"
            f"  Searched: {searched}"
        )

    # On Windows, transitive deps (MKL runtime, etc.) live next to the DLL.
    # Tell the loader to look there too — otherwise we get a misleading
    # 'module not found' from CDLL even when the file itself is fine.
    lib_dir = Path(lib_path).resolve().parent
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(lib_dir))
        except (OSError, FileNotFoundError):
            pass

    dll = ctypes.cdll.LoadLibrary(str(lib_path))
    _bind_signatures(dll)
    print(f"[validate] loaded: {lib_path}", file=sys.stderr)
    return dll


def _bind_signatures(dll: CDLL) -> None:
    dll.digHoloFrameSimulatorCreateSimple.argtypes = [
        c_int, c_int, c_int, c_float, c_int, c_float, c_int,
    ]
    dll.digHoloFrameSimulatorCreateSimple.restype = POINTER(c_float)

    dll.digHoloConfigSetFramePixelSize.argtypes = [c_int, c_float]
    dll.digHoloConfigSetFrameDimensions.argtypes = [c_int, c_int, c_int]
    dll.digHoloConfigSetWavelengthCentre.argtypes = [c_int, c_float]
    dll.digHoloConfigSetPolCount.argtypes = [c_int, c_int]
    dll.digHoloConfigSetfftWindowSizeX.argtypes = [c_int, c_int]
    dll.digHoloConfigSetfftWindowSizeY.argtypes = [c_int, c_int]
    dll.digHoloConfigSetIFFTResolutionMode.argtypes = [c_int, c_int]
    dll.digHoloConfigSetBasisGroupCount.argtypes = [c_int, c_int]
    dll.digHoloConfigSetAutoAlignBeamCentre.argtypes = [c_int, c_int]
    dll.digHoloConfigSetAutoAlignDefocus.argtypes = [c_int, c_int]
    dll.digHoloConfigSetAutoAlignTilt.argtypes = [c_int, c_int]
    dll.digHoloConfigSetAutoAlignBasisWaist.argtypes = [c_int, c_int]
    dll.digHoloConfigSetAutoAlignFourierWindowRadius.argtypes = [c_int, c_int]
    dll.digHoloConfigSetVerbosity.argtypes = [c_int, c_int]
    dll.digHoloSetBatch.argtypes = [c_int, c_int, c_void_p]

    # complex64* digHoloGetFields(handleIdx, int* batchCount, int* polCount,
    #                             float** x, float** y, int* width, int* height)
    dll.digHoloGetFields.argtypes = [
        c_int,
        POINTER(c_int), POINTER(c_int),
        POINTER(POINTER(c_float)), POINTER(POINTER(c_float)),
        POINTER(c_int), POINTER(c_int),
    ]
    dll.digHoloGetFields.restype = POINTER(c_float)

    # complex64* digHoloBasisGetCoefs(handleIdx, int* batchCount, int* modeCount, int* polCount)
    dll.digHoloBasisGetCoefs.argtypes = [
        c_int, POINTER(c_int), POINTER(c_int), POINTER(c_int),
    ]
    dll.digHoloBasisGetCoefs.restype = POINTER(c_float)
