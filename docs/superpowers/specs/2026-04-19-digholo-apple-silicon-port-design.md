# digHolo Apple Silicon Port — Design

**Date:** 2026-04-19
**Scope:** Local dev build only (scope A). No CI changes, no release artefacts, no Python wheels.
**Status:** Draft, pending user review.

## Goal

Produce a working `libdigholo.dylib` + `digHolo` CLI on Apple Silicon (arm64 macOS) that passes the existing `ctest` smoke tests, without regressing the Linux or Windows x86-64 builds.

## Non-goals

- macOS CI runner
- Release artefacts (`digholo-macos-arm64` zip)
- Python wheels for macOS
- Support for `x86_64` macOS (Intel Macs)
- Hand-tuned NEON kernels
- OpenBLAS as an alternative BLAS/LAPACK backend on macOS

These are natural follow-ups but explicitly deferred so this first pass stays small and lands quickly.

## Approach

Two translation shims keep the source tree changes minimal:

1. **simde** translates x86 AVX2/FMA3 intrinsics to NEON at compile time. The ~912 intrinsic call sites in `src/digHolo.cpp` are untouched.
2. **Apple Accelerate framework** replaces Intel MKL for BLAS/LAPACK. The LAPACK/CBLAS function signatures (`cgesvd`, `sgels`, `cgemv`, `cgemm`) are standard, so call sites are untouched.

All new code paths are gated behind `APPLE AND CMAKE_SYSTEM_PROCESSOR MATCHES "arm64|aarch64"` so the Linux/Windows x86-64 builds produce byte-identical artefacts before and after this change.

## Design decisions and trade-offs

### simde vs sse2neon

simde was chosen over sse2neon because digHolo is entirely 256-bit AVX2 / FMA3 code. sse2neon started as SSE→NEON (128-bit) and bolted on AVX2 later; simde was designed from day one for broad x86 intrinsic coverage including AVX2/AVX-512. sse2neon has more recent commit activity, but commit activity is not the same as coverage parity on this particular intrinsic surface.

### Accelerate vs OpenBLAS

Accelerate was chosen because it ships with macOS (zero extra dependency), is tuned for Apple Silicon's AMX matrix coprocessor, and exposes standard LAPACK/CBLAS symbols. OpenBLAS would work but adds a Homebrew dependency and is meaningfully slower than Accelerate for large GEMM/SVD on M-series.

### simde acquisition: FetchContent vs Homebrew

`FetchContent` was chosen over `brew install simde` for two reasons: (1) the simde version is pinned to a specific commit at the CMake layer, so builds are byte-reproducible across machines and across time, (2) no user-facing install step — `cmake --preset macos-release` just works. Homebrew's formula version is implicit and can change under the build with `brew upgrade`; that is a real risk for a scientific library where numerical correctness matters.

### Validation: reference-output diff

Element-wise diff against a reference output generated on Linux/x86 is the cheapest mechanism that actually catches wrong-answer bugs (e.g., a misrouted intrinsic or a signedness mismatch in the BLAS layer). The existing `test_smoke.cpp` only proves the binary loads and runs. Reference binaries are not generated in this change; the diff-test scaffolding lands now and is opt-in via ctest label until the reference data exists.

## File-level changes

### New files

#### `src/digholo_simd_compat.h`

Header-only shim that routes SIMD intrinsic includes:

```cpp
#pragma once
#if defined(DIGHOLO_USE_SIMDE)
  #define SIMDE_ENABLE_NATIVE_ALIASES
  #include <simde/x86/avx2.h>
  #include <simde/x86/fma.h>
#else
  #include <immintrin.h>
#endif
```

`SIMDE_ENABLE_NATIVE_ALIASES` makes `__m256`, `_mm256_*`, `_mm_fmadd_ps`, etc. available without a `simde_` prefix, so no source-level edits are needed at the 912 intrinsic call sites.

#### `CMakePresets.json` — new `macos-release` preset

Ninja generator, `CMAKE_BUILD_TYPE=Release`, binary dir `build/macos-release`. No `DIGHOLO_PREFER_STATIC_DEPS` (scope A is local dev, no portable-artefact requirement).

#### `tests/reference/README.md`

Placeholder explaining:
- How reference binaries were generated (Linux/x86, pinned commit).
- What each file contains.
- The tolerance used for comparison (relative 1e-4, absolute 1e-6).

Reference binaries themselves are not committed in this change.

#### `tests/test_reference.cpp`

ctest binary that:
1. Reads a committed `tests/reference/reference_settings.txt`.
2. Runs the library with those settings.
3. Reads a committed reference output binary from `tests/reference/`.
4. Compares element-wise using relative 1e-4 and absolute 1e-6 tolerance.
5. Returns non-zero on any element outside tolerance.

Registered in CTest with label `reference`, and only added to the test suite if the reference binary file exists — so this change commits cleanly without reference data.

### Modified files

#### `CMakeLists.txt`

- Remove the `if(APPLE)` fatal-error block at lines 54-59.
- Widen the processor check at line 48 to accept `arm64|aarch64` in addition to `x86_64|AMD64|x64`.
- Add a branch: `if(APPLE AND CMAKE_SYSTEM_PROCESSOR MATCHES "arm64|aarch64")`:
  - Pull simde via `FetchContent` pinned to a specific tag (exact commit chosen during implementation).
  - `find_library(ACCELERATE_FRAMEWORK Accelerate REQUIRED)`.
  - Set compile definitions `DIGHOLO_USE_SIMDE` and `DIGHOLO_USE_ACCELERATE` on the `digholo` and `digholo-cli` targets.
  - Do *not* add `-mavx2 -mfma` to compile options on this branch.
  - Link Accelerate framework instead of MKL.
- Leave the existing MKL path and `DIGHOLO_PREFER_STATIC_DEPS` logic untouched in the x86 branch.

#### `src/digHolo.cpp`

Three edits, all narrow:

1. Line 38: replace `#include <immintrin.h>` with `#include "digholo_simd_compat.h"`.
2. Lines 3-10 area: add a new macro `DIGHOLO_USE_ACCELERATE` handling. When defined, include `<Accelerate/Accelerate.h>` and skip the MKL / generic-CBLAS include branches.
3. Lines 486-488 (CPUID query): when compiling for arm64 (`#if defined(__aarch64__) || defined(__arm64__)`), stub the AVX2-support check to return true unconditionally, since simde provides the intrinsic coverage.

#### `tests/CMakeLists.txt`

Add `test_reference` as a new `add_executable` + `add_test`, with label `reference`. Gated on the reference binary existing so it's a no-op today.

## Data flow

Unchanged. SIMD operations route through simde → NEON on macOS, and natively to AVX2 on x86. BLAS/LAPACK calls route to Accelerate on macOS and to MKL (or OpenBLAS) on x86. The public `extern "C"` API surface in `src/digHolo.h` is unchanged.

## Error handling

- **simde FetchContent fails (network)**: CMake produces a clear error pointing to the pinned URL and suggesting a manual checkout.
- **Accelerate not found**: `find_library(... REQUIRED)` fails fast with a clear CMake message (should never happen on a healthy macOS install).
- **Build attempted on x86_64 macOS**: the `aarch64` processor check fails and the build errors out. This is intentional scope limitation for this pass.
- **Numerical drift in reference test**: test_reference.cpp prints the index, reference value, and actual value of the first out-of-tolerance element before exiting non-zero.

## Testing

1. `cmake --preset macos-release && cmake --build --preset macos-release && ctest --preset macos-release` on an M-series Mac produces a green build and passes existing smoke tests.
2. Linux and Windows presets produce byte-identical library output before and after this change (verified by hash comparison of the built `libdigholo.so.1`).
3. `tests/test_reference.cpp` is built on all platforms but skipped until reference data is committed. Once reference data lands, the test runs on all three platforms and enforces numerical agreement.

## Open questions deferred to implementation

- Specific simde commit/tag to pin to — will pick the latest stable release at implementation time.
- Exact Accelerate header path strategy — new LAPACK interface (macOS 13.3+) vs legacy. Preference is the legacy interface since it matches the symbol names already used in `src/digHolo.cpp`, but this will be verified at implementation.
- Whether `DIGHOLO_USE_ACCELERATE` should be an automatic consequence of `APPLE AND arm64` or a separately toggleable option. Default: automatic, for simplicity.

## Out of scope for this change (future work)

- macOS CI runner in `.github/workflows/ci.yml`
- `digholo-macos-arm64` release artefacts
- macOS wheels via `cibuildwheel`
- `x86_64` macOS support
- Native NEON kernels for perf-critical hot loops (if simde-on-NEON measurably lags hand-tuned)
- OpenBLAS fallback on macOS (if Accelerate's behaviour surprises us)
