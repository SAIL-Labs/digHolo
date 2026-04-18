# digHolo <img src="https://github.com/joelacarpenter/digHolo/blob/doc/DigHoloLogo_64x64.png" height="32" width="32">

High-speed library for off-axis digital holography and Hermite-Gaussian decomposition.

SAIL-Labs fork of [joelacarpenter/digHolo](https://github.com/joelacarpenter/digHolo).

## User Guide

If this library is useful to you, please cite the [User Guide](https://arxiv.org/abs/2204.02348) ([arXiv:2204.02348](https://arxiv.org/abs/2204.02348)).
Full function documentation, benchmarks, and background are in `doc/UserGuide.pdf`.

## Video Tutorials

- [digHolo library introduction (YouTube)](https://youtu.be/rQMfWO2MQJQ)
- [Off-axis digital holography tutorial (YouTube)](https://youtu.be/9hgQyx1He_U)

## Supported Platforms

- **Linux** — x86-64 with AVX2 + FMA3
- **Windows** — x86-64 with AVX2 + FMA3

macOS is not supported: digHolo's SIMD paths hard-require AVX2/FMA3 (no Apple Silicon), and Intel MKL isn't redistributed for recent macOS.

## Dependencies

- [FFTW 3](https://www.fftw.org/) — single-precision (`fftw3f`), used for all FFTs **and the real-to-real DCTs** in `AutoAlign`.
- [Intel MKL](https://www.intel.com/content/www/us/en/developer/tools/oneapi/onemkl.html) from Intel oneAPI — BLAS/LAPACK (`cgesvd`, `sgels`, `cgemv`, `cgemm`). OpenBLAS works too but requires editing `src/digHolo.cpp` (comment out `#define MKL_ENABLE`).
- **SVML** (optional) — picked up automatically on MSVC ≥ VS2019 / Intel Compiler for fast trig. Otherwise digHolo falls back to hand-vectorised implementations.

## Build

See [`build.md`](build.md) for prerequisites and the full configure/build/test recipe. TL;DR:

```bash
# Linux
source /opt/intel/oneapi/setvars.sh
cmake --preset linux-release
cmake --build --preset linux-release
ctest --preset linux-release
```

```powershell
# Windows (from Intel oneAPI Command Prompt for VS 2022, with VCPKG_ROOT set)
cmake --preset windows-release
cmake --build --preset windows-release --config Release
ctest --preset windows-release
```

Produces `libdigholo.so` / `digholo.dll` (shared library) and `digHolo` (CLI executable).

## Command-line Execution

```
digHolo digHoloSettings.txt
```

The settings file is tab-delimited: each `<PropertyName>\t<value(s)>` line maps to the corresponding `digHoloConfigSet<PropertyName>(...)` call. See `Examples/C++/digHoloDemo/digHoloSettings.txt` for the full set of options and `main` / `digHoloRunBatchFromConfigFile` in `src/digHolo.cpp` for the dispatch table. Camera frame data is supplied as a binary file referenced from the settings file; outputs (coefficients, fields, axes, viewport bitmap) are written to user-specified paths.

## Using the Library

See `Examples/`:

- `Examples/C++/digHoloDemo/digHoloDemo.cpp` — minimal C++ driver
- `Examples/Python/digHoloExamplePython.py` — ctypes-based wrapper
- `Examples/Matlab/digHoloExampleMatlab.m` — MATLAB `loadlibrary` usage

The example scripts currently expect the shared library at the old `bin/Win64/digHolo.dll` path; adjust the `LoadLibrary` / `loadlibrary` calls to point at whatever install prefix you configured (e.g. `build/linux-release/libdigholo.so.1`). A proper Python package is on the roadmap.
