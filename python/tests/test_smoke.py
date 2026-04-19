"""End-to-end smoke test for the digholo Python wheel.

Mirrors ``tests/test_smoke.cpp`` from the C++ side: drives the full pipeline
against synthetic frames and asserts shape / dtype invariants. Not a numerical
accuracy test — the goal is to prove the wheel was built and packaged
correctly and that the Python ↔ C boundary works.
"""

from __future__ import annotations

import numpy as np
import pytest

import digholo
from digholo import DigHolo, DigHoloError, simulate_frames


# Tiny canonical configuration shared by the tests below.
FRAME_COUNT  = 4
FRAME_WIDTH  = 320
FRAME_HEIGHT = 256
PIXEL_SIZE   = 20e-6
POL_COUNT    = 2
LAMBDA0      = 1565e-9


@pytest.fixture
def frames() -> np.ndarray:
    return simulate_frames(
        frame_count=FRAME_COUNT,
        frame_width=FRAME_WIDTH,
        frame_height=FRAME_HEIGHT,
        pixel_size=PIXEL_SIZE,
        pol_count=POL_COUNT,
        wavelength=LAMBDA0,
    )


def test_version_present():
    assert isinstance(digholo.__version__, str)
    assert digholo.__version__


def test_simulate_frames_shape_dtype(frames):
    assert frames.shape == (FRAME_COUNT, FRAME_HEIGHT, FRAME_WIDTH)
    assert frames.dtype == np.float32
    # Synthetic frames carry interference fringes — must have nonzero variance.
    assert frames.var() > 0


def _new_configured_handle() -> DigHolo:
    """Return a freshly-created DigHolo with the canonical batch config applied.

    The C library segfaults if you call digHoloDestroy() on a handle that was
    never given a frame batch + dimensions (probably reaching for never-
    allocated internal buffers during teardown). Always run at least the
    minimum config before close — wrap the construction here so individual
    tests stay short.
    """
    dh = DigHolo()
    dh.frame_dimensions  = (FRAME_WIDTH, FRAME_HEIGHT)
    dh.frame_pixel_size  = PIXEL_SIZE
    dh.wavelength_centre = LAMBDA0
    dh.pol_count         = POL_COUNT
    return dh


def test_handle_lifecycle():
    dh = _new_configured_handle()
    dh.close()
    # close() is idempotent — second call must not crash even though the
    # underlying C handle is already gone.
    dh.close()


def test_handle_context_manager():
    with _new_configured_handle() as dh:
        assert dh.frame_dimensions == (FRAME_WIDTH, FRAME_HEIGHT)


def test_pol_count_round_trip():
    with _new_configured_handle() as dh:
        assert dh.pol_count == POL_COUNT


def test_pixel_size_round_trip():
    with _new_configured_handle() as dh:
        assert dh.frame_pixel_size == pytest.approx(PIXEL_SIZE, rel=1e-6)


def test_full_pipeline_shape(frames):
    """End-to-end run: configure → set_batch → auto_align → process_batch."""
    with DigHolo() as dh:
        dh.frame_dimensions     = (FRAME_WIDTH, FRAME_HEIGHT)
        dh.frame_pixel_size     = PIXEL_SIZE
        dh.wavelength_centre    = LAMBDA0
        dh.pol_count            = POL_COUNT
        dh.fft_window_size      = (128, 128)
        dh.ifft_resolution_mode = 1
        dh.basis_group_count    = 3   # tiny basis to keep the test fast

        dh.set_batch(frames)
        dh.auto_align()
        coefs = dh.process_batch()

        # Exact mode count is 1+2+3 = 6 per polarisation.
        expected_modes = sum(range(1, 4))  # = 6
        assert coefs.shape == (FRAME_COUNT, POL_COUNT * expected_modes)
        assert coefs.dtype == np.complex64
        # Library populated something — coefficients should not be all zeros.
        assert np.any(np.abs(coefs) > 0)

        # get_coefficients() should return the same thing without re-running.
        coefs_again = dh.get_coefficients()
        assert coefs_again.shape == coefs.shape
        # Values may be a view over the same buffer — copy before comparing.
        np.testing.assert_array_equal(np.asarray(coefs), np.asarray(coefs_again))


def test_set_batch_validates_dtype_and_shape():
    with DigHolo() as dh:
        with pytest.raises(ValueError, match="3-D"):
            dh.set_batch(np.zeros((4, 4), dtype=np.float32))


def test_get_fields_after_processing(frames):
    with DigHolo() as dh:
        dh.frame_dimensions     = (FRAME_WIDTH, FRAME_HEIGHT)
        dh.frame_pixel_size     = PIXEL_SIZE
        dh.wavelength_centre    = LAMBDA0
        dh.pol_count            = POL_COUNT
        dh.fft_window_size      = (128, 128)
        dh.ifft_resolution_mode = 1
        dh.basis_group_count    = 3

        dh.set_batch(frames)
        dh.auto_align()
        dh.process_batch()
        fields, x, y = dh.get_fields()

        assert fields.dtype == np.complex64
        assert fields.ndim == 3
        # Width / height come from the IFFT window, but per-pol axis must
        # be a multiple of pol_count.
        assert fields.shape[0] == FRAME_COUNT
        assert fields.shape[1] % POL_COUNT == 0
        assert x.size > 0 and y.size > 0
