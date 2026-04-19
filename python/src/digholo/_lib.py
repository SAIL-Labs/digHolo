"""Low-level ctypes bindings to libdigholo.

This module loads the bundled shared library and declares the C signatures
for every API we wrap from Python. Application code should not import this
module directly — use the public :class:`digholo.DigHolo` class instead.
"""

from __future__ import annotations

import ctypes
import os
import platform
import sys
from ctypes import (
    CDLL,
    POINTER,
    byref,
    c_char_p,
    c_float,
    c_int,
    c_short,
    c_ushort,
    c_void_p,
)
from pathlib import Path

__all__ = ["lib", "complex64_p"]


def _candidate_lib_paths() -> list[Path]:
    """Return shared-library candidates in load-priority order."""
    pkg_dir = Path(__file__).resolve().parent

    if sys.platform == "win32":
        names = ["digholo.dll", "libdigholo.dll"]
    elif sys.platform == "darwin":
        # Not supported, but be explicit about it.
        names = ["libdigholo.dylib"]
    else:
        # SOVERSION-suffixed name first; CMake produces libdigholo.so.1
        # alongside the libdigholo.so symlink. Try both.
        names = ["libdigholo.so.1", "libdigholo.so"]

    return [pkg_dir / n for n in names]


def _load_library() -> CDLL:
    pkg_dir = Path(__file__).resolve().parent

    # On Python ≥ 3.8 / Windows, ctypes.CDLL no longer adds the DLL's own
    # directory to the search path for transitive deps. Tell the loader to
    # also look next to digholo.dll so any DLL that delvewheel bundled into
    # the package (MKL runtime, FFTW3, anything else) resolves cleanly.
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(pkg_dir))
        except (OSError, FileNotFoundError):
            pass

    last_err: Exception | None = None
    for candidate in _candidate_lib_paths():
        if candidate.exists():
            try:
                return CDLL(str(candidate))
            except OSError as exc:
                last_err = exc

    arch = platform.machine()
    raise OSError(
        f"Could not load the bundled digholo shared library on "
        f"{sys.platform}/{arch}. Searched: "
        + ", ".join(str(p) for p in _candidate_lib_paths())
        + (f". Last error: {last_err}" if last_err else "")
    )


lib: CDLL = _load_library()

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
# digHolo's complex64 type is `float[2]` (interleaved re/im). We always pass
# pointers to flat float arrays at the FFI boundary and reshape on either
# side — far simpler than declaring nested ctypes Structs.
complex64_p = POINTER(c_float)

# ---------------------------------------------------------------------------
# Function signatures
#
# Pattern: declare argtypes / restype for every function we call. ctypes
# defaults to int-everywhere otherwise, which silently truncates pointers
# on 64-bit systems.
# ---------------------------------------------------------------------------

# --- Lifecycle ------------------------------------------------------------
lib.digHoloCreate.argtypes  = []
lib.digHoloCreate.restype   = c_int

lib.digHoloDestroy.argtypes = [c_int]
lib.digHoloDestroy.restype  = c_int

lib.digHoloConfigSetVerbosity.argtypes = [c_int, c_int]
lib.digHoloConfigSetVerbosity.restype  = c_int

# --- Frame / pipeline configuration --------------------------------------
lib.digHoloConfigSetFrameDimensions.argtypes = [c_int, c_int, c_int]
lib.digHoloConfigSetFrameDimensions.restype  = c_int

lib.digHoloConfigGetFrameDimensions.argtypes = [c_int, POINTER(c_int), POINTER(c_int)]
lib.digHoloConfigGetFrameDimensions.restype  = c_int

lib.digHoloConfigSetFramePixelSize.argtypes  = [c_int, c_float]
lib.digHoloConfigSetFramePixelSize.restype   = c_int

lib.digHoloConfigGetFramePixelSize.argtypes  = [c_int]
lib.digHoloConfigGetFramePixelSize.restype   = c_float

lib.digHoloConfigSetWavelengthCentre.argtypes = [c_int, c_float]
lib.digHoloConfigSetWavelengthCentre.restype  = c_int

lib.digHoloConfigSetPolCount.argtypes = [c_int, c_int]
lib.digHoloConfigSetPolCount.restype  = c_int

lib.digHoloConfigGetPolCount.argtypes = [c_int]
lib.digHoloConfigGetPolCount.restype  = c_int

lib.digHoloConfigSetfftWindowSizeX.argtypes = [c_int, c_int]
lib.digHoloConfigSetfftWindowSizeX.restype  = c_int
lib.digHoloConfigSetfftWindowSizeY.argtypes = [c_int, c_int]
lib.digHoloConfigSetfftWindowSizeY.restype  = c_int

lib.digHoloConfigSetIFFTResolutionMode.argtypes = [c_int, c_int]
lib.digHoloConfigSetIFFTResolutionMode.restype  = c_int

lib.digHoloConfigSetBasisGroupCount.argtypes = [c_int, c_int]
lib.digHoloConfigSetBasisGroupCount.restype  = c_int

# --- Batch ingest --------------------------------------------------------
lib.digHoloSetBatch.argtypes = [c_int, c_int, c_void_p]
lib.digHoloSetBatch.restype  = c_int

lib.digHoloSetBatchUint16.argtypes = [c_int, c_int, POINTER(c_ushort), c_int]
lib.digHoloSetBatchUint16.restype  = c_int

# --- Pipeline execution --------------------------------------------------
lib.digHoloProcessBatch.argtypes = [
    c_int,
    POINTER(c_int),  # batchCount   (out)
    POINTER(c_int),  # modeCount    (out)
    POINTER(c_int),  # polCount     (out)
]
lib.digHoloProcessBatch.restype  = complex64_p

lib.digHoloAutoAlign.argtypes = [c_int]
lib.digHoloAutoAlign.restype  = c_float

# --- Field / coefficient retrieval ---------------------------------------
lib.digHoloGetFields.argtypes = [
    c_int,
    POINTER(c_int),                                # batchCount  (out)
    POINTER(c_int),                                # polCount    (out)
    POINTER(POINTER(c_float)),                     # x axis      (out)
    POINTER(POINTER(c_float)),                     # y axis      (out)
    POINTER(c_int),                                # width       (out)
    POINTER(c_int),                                # height      (out)
]
lib.digHoloGetFields.restype = complex64_p

lib.digHoloBasisGetCoefs.argtypes = [
    c_int,
    POINTER(c_int),  # batchCount
    POINTER(c_int),  # modeCount
    POINTER(c_int),  # polCount
]
lib.digHoloBasisGetCoefs.restype = complex64_p

# --- Frame simulator (used in tests / examples) --------------------------
lib.digHoloFrameSimulatorCreateSimple.argtypes = [
    c_int,    # frameCount
    c_int,    # frameWidth
    c_int,    # frameHeight
    c_float,  # pixelSize
    c_int,    # polCount
    c_float,  # wavelength
    c_int,    # printToConsole
]
lib.digHoloFrameSimulatorCreateSimple.restype = POINTER(c_float)

lib.digHoloFrameSimulatorDestroy.argtypes = [POINTER(c_float)]
lib.digHoloFrameSimulatorDestroy.restype  = c_int


# Re-exports for convenience
__all__ += [
    "byref",
    "c_float",
    "c_int",
    "c_ushort",
    "c_void_p",
    "POINTER",
]
