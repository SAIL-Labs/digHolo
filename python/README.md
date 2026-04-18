# digholo (Python)

Python bindings for [digHolo](https://github.com/SAIL-Labs/digHolo) — a
high-speed off-axis digital holography and Hermite-Gaussian decomposition
library.

The wheel ships a pre-built `libdigholo.so` / `digholo.dll` so installation
is just `pip install digholo` — no MKL or FFTW3 install required on the user's
system.

```python
import numpy as np
from digholo import DigHolo

# Generate a synthetic batch of camera frames using the bundled simulator.
frames = DigHolo.simulate_frames(
    frame_count=4, frame_width=320, frame_height=256,
    pixel_size=20e-6, pol_count=2, wavelength=1565e-9,
)

# Reconstruct fields and decompose onto Hermite-Gaussian modes.
with DigHolo() as dh:
    dh.frame_dimensions      = (320, 256)
    dh.frame_pixel_size      = 20e-6
    dh.wavelength_centre     = 1565e-9
    dh.pol_count             = 2
    dh.fft_window_size       = (128, 128)
    dh.ifft_resolution_mode  = 1   # minimal-window reconstruction
    dh.basis_group_count     = 9   # → sum(1..9) = 45 HG modes

    dh.set_batch(frames)
    dh.auto_align()
    coefs = dh.process_batch()      # shape (batch, pol*modes), complex64

print(coefs.shape, coefs.dtype)
```

See [the upstream User Guide](https://arxiv.org/abs/2204.02348) for the full
processing-pipeline theory and parameter reference.

## Platform support

- Linux x86-64, glibc ≥ 2.28 (RHEL 8, Ubuntu 18.04+, Debian 10+)
- Windows 10/11 x64, with the MSVC 2015–2022 runtime

macOS is not supported — digHolo's SIMD paths hard-require AVX2/FMA3 and
Intel MKL is not redistributed for macOS.

## Building from source

```bash
pip install scikit-build-core ninja
pip install ./python -v
```

You'll need Intel oneAPI MKL and FFTW3 development headers on the build host;
see the [main repo's build instructions](../build.md) for the full setup.
