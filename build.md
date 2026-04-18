# Building digHolo

digHolo builds on **Linux** and **Windows** via CMake (≥ 3.21). macOS is not
supported — digHolo's SIMD paths hard-require x86-64 AVX2 + FMA3.

The single canonical source lives in `src/digHolo.cpp` and `src/digHolo.h`.

## Prerequisites

### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install build-essential cmake ninja-build libfftw3-dev

# Intel oneAPI MKL (BLAS/LAPACK)
wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB \
    | gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" \
    | sudo tee /etc/apt/sources.list.d/oneapi.list
sudo apt update
sudo apt install intel-oneapi-mkl-devel

# Source MKL's env vars before configuring CMake
source /opt/intel/oneapi/setvars.sh
```

### Windows

Install:

- **Visual Studio 2022** with the "Desktop development with C++" workload
- **Intel oneAPI Base Toolkit** (for MKL)
- **CMake** (≥ 3.21) and **Ninja** (optional but fast)
- **vcpkg**, exported via `VCPKG_ROOT` env var (the `vcpkg.json` manifest in this
  repo will pull FFTW3 automatically on first configure)

Open the "Intel oneAPI Command Prompt for Visual Studio 2022" so both MKL and
MSVC are on PATH before running CMake.

## Configure + build

This repo ships `CMakePresets.json` with ready-made configurations for Linux
and Windows.

```bash
# Linux
cmake --preset linux-release
cmake --build --preset linux-release
ctest --preset linux-release
cmake --install build/linux-release --prefix /desired/install/path
```

```powershell
# Windows (x64)
cmake --preset windows-release
cmake --build --preset windows-release --config Release
ctest --preset windows-release
```

Or invoke CMake directly without presets:

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build --output-on-failure
```

## Build outputs

- `digholo` — shared library (`libdigholo.so.1` / `digholo.dll`)
- `digHolo` — CLI executable that consumes tab-delimited settings files
  (`./digHolo digHoloSettings.txt`)

## Key CMake options

| Option                  | Default | Effect                                               |
| ----------------------- | ------- | ---------------------------------------------------- |
| `DIGHOLO_BUILD_SHARED`  | `ON`    | Build shared (vs static) library                     |
| `DIGHOLO_BUILD_CLI`     | `ON`    | Build the CLI executable                             |
| `DIGHOLO_BUILD_TESTING` | `ON`    | Build smoke tests (run with `ctest`)                 |
| `DIGHOLO_INSTALL`       | `ON`    | Emit install + `digHoloConfig.cmake` export targets  |
| `DIGHOLO_FFTW_DLL`      | `OFF`   | Define `FFTW_DLL` (only for dynamic-linked FFTW)     |
| `MKL_LINK`              | `static` | `static` or `dynamic` MKL linkage                   |
| `MKL_THREADING`         | `sequential` | `sequential`, `tbb`, `intel_thread`             |

## Gotchas

- **Link order is load-bearing.** FFTW3 must come before MKL, otherwise MKL's
  FFTW-compatible interface wins — and MKL does not implement the
  real-to-real DCTs used by `digHoloAutoAlign`. The CMakeLists enforces this.
- **`#define MKL_ENABLE` / `CBLAS_ENABLE` / `LAPACKBLAS_ENABLE`** are currently
  unconditional at the top of `src/digHolo.cpp`. Switching to OpenBLAS
  requires editing those `#define`s directly — no CMake toggle exists yet.
- **AVX2/FMA3 are mandatory**; the CMake file errors out on non-x86-64 hosts
  including Apple Silicon.
- When distributing the shared library alongside MKL's own DLLs/SOs (dynamic
  MKL linkage), remember to ship `libiomp5md.dll` / `libiomp5.so` if you use
  `MKL_THREADING=intel_thread`.

## Python / MATLAB bindings

These consume the built shared library. See `Examples/Python/` and
`Examples/Matlab/` — they currently hardcode paths into `bin/` from the old
build layout and will need updating once CI publishes release artefacts. A
proper Python package (`python/`) with `scikit-build-core` + `cibuildwheel`
is planned.
