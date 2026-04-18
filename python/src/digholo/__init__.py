"""digholo — Python bindings for the digHolo off-axis digital holography library.

Public API:

* :class:`DigHolo` — handle-based wrapper around the C library, exposes the
  whole processing pipeline as a Pythonic object.
* :func:`simulate_frames` — generate a synthetic camera-frame batch using
  digHolo's bundled simulator (useful for tests and examples).

The C library handles its own memory; arrays returned by `process_batch()`
and friends are NumPy views over library-owned buffers and become invalid
when the :class:`DigHolo` instance is destroyed or when subsequent processing
calls re-allocate. Copy with `np.array(..., copy=True)` if you need to keep
the data past the next call.

The C ABI documentation lives in ``src/digHolo.h``. The :mod:`digholo._lib`
module exposes the raw ctypes functions for users that need an escape hatch
into uncommon parts of the API.
"""

from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_float, c_int
from typing import Tuple

import numpy as np

from . import _lib

__version__ = "1.0.0"

__all__ = ["DigHolo", "DigHoloError", "simulate_frames"]


class DigHoloError(RuntimeError):
    """Raised when the digHolo C library reports an error."""


# Sentinel — the C library uses this to indicate "metric not yet calculated".
_FLT_MAX = 3.4028234663852886e38


def _as_complex(buf: ctypes.POINTER(c_float), shape: Tuple[int, ...]) -> np.ndarray:
    """Wrap a `complex64*` pointer (interleaved float pairs) as a complex64 array.

    Returns a view over library-owned memory. The total flat element count
    must equal ``2 * prod(shape)`` (interleaved real, imaginary).
    """
    if not buf:
        raise DigHoloError("library returned a null pointer")
    nfloats = 2 * int(np.prod(shape))
    raw = np.ctypeslib.as_array(buf, shape=(nfloats,))
    # Interpret consecutive float pairs as complex64. View, no copy.
    return raw.view(np.complex64).reshape(shape)


class DigHolo:
    """Reconstruction context — one per concurrent processing pipeline.

    Use as a context manager so the underlying C handle is destroyed even on
    exception::

        with DigHolo() as dh:
            dh.frame_dimensions = (320, 256)
            dh.set_batch(frames)
            dh.auto_align()
            coefs = dh.process_batch()
    """

    def __init__(self, *, verbosity: int = 0) -> None:
        self._handle: int = _lib.lib.digHoloCreate()
        if self._handle < 0:
            raise DigHoloError(f"digHoloCreate returned {self._handle}")
        # Default to silent — the C library's stdout chatter is rarely useful.
        _lib.lib.digHoloConfigSetVerbosity(self._handle, int(verbosity))
        # Hold a reference to the most recent input batch so it isn't GC'd
        # while the C library still has its pointer.
        self._batch_keepalive: np.ndarray | None = None

    # -- Resource management ----------------------------------------------
    def close(self) -> None:
        """Release the C handle. Idempotent."""
        h, self._handle = self._handle, -1
        if h >= 0:
            _lib.lib.digHoloDestroy(h)
        self._batch_keepalive = None

    def __enter__(self) -> "DigHolo":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def __del__(self) -> None:
        # Best-effort cleanup; ignore errors during interpreter shutdown.
        try:
            self.close()
        except Exception:
            pass

    # -- Configuration properties -----------------------------------------
    @property
    def frame_dimensions(self) -> Tuple[int, int]:
        w, h = c_int(), c_int()
        _lib.lib.digHoloConfigGetFrameDimensions(self._handle, byref(w), byref(h))
        return w.value, h.value

    @frame_dimensions.setter
    def frame_dimensions(self, wh: Tuple[int, int]) -> None:
        w, h = wh
        _lib.lib.digHoloConfigSetFrameDimensions(self._handle, int(w), int(h))

    @property
    def frame_pixel_size(self) -> float:
        return float(_lib.lib.digHoloConfigGetFramePixelSize(self._handle))

    @frame_pixel_size.setter
    def frame_pixel_size(self, value: float) -> None:
        _lib.lib.digHoloConfigSetFramePixelSize(self._handle, c_float(float(value)))

    @property
    def pol_count(self) -> int:
        return int(_lib.lib.digHoloConfigGetPolCount(self._handle))

    @pol_count.setter
    def pol_count(self, value: int) -> None:
        _lib.lib.digHoloConfigSetPolCount(self._handle, int(value))

    # Wavelength has no Get* in the C API at the parity we need; setter only.
    @property
    def wavelength_centre(self) -> float:
        raise AttributeError("wavelength_centre is write-only (no C getter exposed)")

    @wavelength_centre.setter
    def wavelength_centre(self, value: float) -> None:
        _lib.lib.digHoloConfigSetWavelengthCentre(self._handle, c_float(float(value)))

    @property
    def fft_window_size(self) -> Tuple[int, int]:
        raise AttributeError("fft_window_size is write-only (no C getter exposed)")

    @fft_window_size.setter
    def fft_window_size(self, wh: Tuple[int, int]) -> None:
        w, h = wh
        _lib.lib.digHoloConfigSetfftWindowSizeX(self._handle, int(w))
        _lib.lib.digHoloConfigSetfftWindowSizeY(self._handle, int(h))

    @property
    def ifft_resolution_mode(self) -> int:
        raise AttributeError("ifft_resolution_mode is write-only (no C getter exposed)")

    @ifft_resolution_mode.setter
    def ifft_resolution_mode(self, value: int) -> None:
        _lib.lib.digHoloConfigSetIFFTResolutionMode(self._handle, int(value))

    @property
    def basis_group_count(self) -> int:
        raise AttributeError("basis_group_count is write-only (no C getter exposed)")

    @basis_group_count.setter
    def basis_group_count(self, value: int) -> None:
        _lib.lib.digHoloConfigSetBasisGroupCount(self._handle, int(value))

    # -- Pipeline ----------------------------------------------------------
    def set_batch(self, frames: np.ndarray) -> None:
        """Hand a batch of camera frames to the library.

        ``frames`` must be a contiguous ``float32`` array with shape
        ``(batch_count, height, width)`` — i.e. the same layout the C library
        expects, with the leading axis indexing frames within the batch. A
        reference is held until the next ``set_batch`` / ``close`` so the
        buffer stays alive across subsequent ``auto_align`` / ``process_batch``
        calls.
        """
        arr = np.ascontiguousarray(frames, dtype=np.float32)
        if arr.ndim != 3:
            raise ValueError(
                f"frames must be 3-D (batch, height, width); got shape {arr.shape}"
            )
        self._batch_keepalive = arr  # prevent GC
        batch_count = arr.shape[0]
        _lib.lib.digHoloSetBatch(
            self._handle,
            int(batch_count),
            arr.ctypes.data_as(ctypes.c_void_p),
        )

    def auto_align(self) -> float:
        """Run the iterative AutoAlign routine and return the goal-metric value."""
        return float(_lib.lib.digHoloAutoAlign(self._handle))

    def process_batch(self) -> np.ndarray:
        """Run the digital-holography pipeline over the current batch.

        Returns
        -------
        np.ndarray
            Complex64 array of shape ``(batch_count, pol_count * mode_count)``
            containing the modal coefficients for every frame.
        """
        bc, mc, pc = c_int(), c_int(), c_int()
        ptr = _lib.lib.digHoloProcessBatch(
            self._handle, byref(bc), byref(mc), byref(pc)
        )
        if not ptr:
            raise DigHoloError("digHoloProcessBatch returned NULL")
        return _as_complex(ptr, shape=(bc.value, pc.value * mc.value))

    def get_coefficients(self) -> np.ndarray:
        """Re-fetch the most recent batch's modal coefficients without re-processing."""
        bc, mc, pc = c_int(), c_int(), c_int()
        ptr = _lib.lib.digHoloBasisGetCoefs(
            self._handle, byref(bc), byref(mc), byref(pc)
        )
        if not ptr:
            raise DigHoloError("digHoloBasisGetCoefs returned NULL")
        return _as_complex(ptr, shape=(bc.value, pc.value * mc.value))

    def get_fields(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return the reconstructed complex fields and their (x, y) axes.

        Returns
        -------
        fields : np.ndarray
            Shape ``(batch_count, pol_count * width, height)``, complex64.
        x : np.ndarray
            Camera-plane x coordinates, shape ``(width,)`` per polarisation.
        y : np.ndarray
            Camera-plane y coordinates, shape ``(height,)`` per polarisation.
        """
        bc, pc = c_int(), c_int()
        w,  h  = c_int(), c_int()
        x_p = POINTER(c_float)()
        y_p = POINTER(c_float)()
        ptr = _lib.lib.digHoloGetFields(
            self._handle, byref(bc), byref(pc),
            byref(x_p), byref(y_p), byref(w), byref(h),
        )
        if not ptr:
            raise DigHoloError("digHoloGetFields returned NULL")
        fields = _as_complex(ptr, shape=(bc.value, pc.value * w.value, h.value))
        x = np.ctypeslib.as_array(x_p, shape=(pc.value * w.value,))
        y = np.ctypeslib.as_array(y_p, shape=(pc.value * h.value,))
        return fields, x, y


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------
def simulate_frames(
    *,
    frame_count: int,
    frame_width: int,
    frame_height: int,
    pixel_size: float,
    pol_count: int,
    wavelength: float,
    print_to_console: bool = False,
) -> np.ndarray:
    """Generate a synthetic batch of camera frames using digHolo's simulator.

    Returns a ``(frame_count, frame_height, frame_width)`` ``float32`` array.
    The data is **copied** out of library-owned memory before that memory is
    released, so the returned array is safe to keep indefinitely.
    """
    ptr = _lib.lib.digHoloFrameSimulatorCreateSimple(
        int(frame_count),
        int(frame_width),
        int(frame_height),
        c_float(float(pixel_size)),
        int(pol_count),
        c_float(float(wavelength)),
        int(bool(print_to_console)),
    )
    if not ptr:
        raise DigHoloError("digHoloFrameSimulatorCreateSimple returned NULL")
    try:
        view = np.ctypeslib.as_array(
            ptr, shape=(frame_count, frame_height, frame_width)
        )
        return view.copy()
    finally:
        _lib.lib.digHoloFrameSimulatorDestroy(ptr)


# Convenience: expose simulate_frames as a class-method too so the README's
# example reads naturally.
DigHolo.simulate_frames = staticmethod(simulate_frames)  # type: ignore[attr-defined]
