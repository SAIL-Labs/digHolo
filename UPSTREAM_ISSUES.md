# Upstream Issues

A running log of bugs in the upstream [joelacarpenter/digHolo](https://github.com/joelacarpenter/digHolo)
codebase that we've found and fixed in this SAIL-Labs fork while wiring up
cross-platform CI and a Python wheel.

Each entry should be PR-ready: reproduce, root cause, fix already applied
locally with a commit ref, and a "Reported upstream?" status. When an issue
is filed/PR'd at upstream, link it.

---

## Status legend

- 🐛 **Confirmed bug** — we have a reproducer and a fix.
- ⚠️ **Footgun** — works as documented but produces silent / surprising
  failures for any non-trivial consumer.
- ✏️ **Cleanup** — non-bug, just maintenance / hygiene.
- 📤 **Reported** — upstream issue / PR link in the entry.

---

## 1. 🐛 Public C API symbols are C++-mangled on Linux/macOS

**Affects:** every Linux and macOS build of `libdigholo.so` / `libdigholo.dylib`. Anything that loads the library via `dlopen` + `dlsym` — Python `ctypes`, `cffi`, hand-rolled FFI bindings — fails with `undefined symbol: digHoloCreate`. C/C++ callers that `#include "digHolo.h"` happen to link fine because both producer and consumer agree on the mangled name, so the bug is invisible to anyone who only consumes the library that way.

**Reproducer (Linux):**

```bash
g++ -std=c++11 -O3 -mavx2 -mfma -fPIC -shared src/digHolo.cpp -o libdigholo.so \
    -lfftw3f -lmkl_intel_lp64 -lmkl_sequential -lmkl_core -lpthread -lm -ldl
nm -D --defined-only libdigholo.so | grep digHoloCreate
# => _Z14digHoloCreatev    (mangled — should be `digHoloCreate`)

python3 -c "import ctypes; ctypes.CDLL('./libdigholo.so').digHoloCreate"
# AttributeError: ./libdigholo.so: undefined symbol: digHoloCreate
```

**Root cause:** the `EXT_C` macro in `digHolo.h` only adds `extern "C"` on Windows (because `__declspec(dllexport)` implies it). On non-Windows it expands to nothing, and every "public" function declaration is parsed as ordinary C++ — so the compiler emits the mangled name in the .so. The Windows API consumer pattern works because dllexport implies extern "C"; the Linux pattern silently breaks anyone using `dlsym`.

**Original macro:**

```c
#ifdef __cplusplus
#  ifdef _WIN32
#    define EXT_C extern "C" __declspec(dllexport)
#  else
#    define EXT_C            // <-- bug: missing `extern "C"`
#  endif
#else
#  define EXT_C
#endif
```

**Fix in this fork (commit `a8861c5`):** add `extern "C"` unconditionally on every platform when compiling as C++. Symbols emerge as the documented bare ASCII names.

**Reported upstream:** not yet.

---

## 2. 🐛 Windows consumers silently drop their `digholo.dll` dependency

**Affects:** any Windows binary that links against `digholo.dll` via the auto-generated import library. The consumer compiles and links without errors, but the resulting `.exe` has *no runtime dependency* on `digholo.dll` at all and dies at startup with `STATUS_DLL_NOT_FOUND` (`0xc0000135`).

**Reproducer (Windows, MSVC):**

1. Build digHolo as a shared library following the upstream README (Visual Studio project / `cl.exe`).
2. Compile a trivial consumer:

   ```cpp
   // smoke.cpp
   #include "digHolo.h"
   int main() { (void)digHoloCreate(); return 0; }
   ```

   ```cmd
   cl /EHsc /MD smoke.cpp /link digholo.lib
   ```

3. Inspect the produced exe:

   ```cmd
   dumpbin /dependents smoke.exe
   ```

   `digholo.dll` is **not** listed in the dependency table. The exe is implausibly small (~12 KB).

4. Run it: `0xc0000135 STATUS_DLL_NOT_FOUND`.

**Root cause:** `EXT_C` unconditionally expands to `extern "C" __declspec(dllexport)` on Windows — *even when the header is included by a consumer*. MSVC sees `dllexport` on a declaration and treats the consumer translation unit as if it were re-exporting the symbol itself. The linker then satisfies the references via the digholo.lib import-library entries but doesn't generate import-table entries in the consumer exe (because, from MSVC's perspective, the consumer exports them too). The resulting binary has empty / dangling thunks where calls into `digholo.dll` should be.

**Original macro:**

```c
#ifdef _WIN32
#  define EXT_C extern "C" __declspec(dllexport)   // <-- always export, even for consumers
#else
   ...
#endif
```

**Fix in this fork (commits `d98b879` + follow-up):** three-state `EXT_C` macro to handle DLL build, standalone build, and consumer builds independently:

```c
#ifdef _WIN32
#  if defined(DIGHOLO_STATIC_BUILD)        // CLI / static lib — no DLL surface
#    define EXT_C extern "C"
#  elif defined(DIGHOLO_BUILDING)          // building the shared library itself
#    define EXT_C extern "C" __declspec(dllexport)
#  else                                    // consumer of digholo.dll
#    define EXT_C extern "C" __declspec(dllimport)
#  endif
#endif
```

A naïve two-state version (just `DIGHOLO_BUILDING` vs not) breaks on Windows when the CLI executable compiles `digHolo.cpp` directly — MSVC produces a `digHolo.lib` + `digHolo.exp` next to `digHolo.exe` because of the `dllexport` decorations. On Windows's case-insensitive filesystem these clash with the shared library's `digholo.lib` / `digholo.exp`, and any test exe that subsequently links against `digHolo::digholo` ends up importing from `digHolo.exe` instead of `digholo.dll`. Hence the third state for "compile the source standalone with no DLL semantics".

CMake wires it up:
```cmake
target_compile_definitions(digholo     PRIVATE DIGHOLO_BUILDING)        # SHARED lib
target_compile_definitions(digholo-cli PRIVATE DIGHOLO_STATIC_BUILD)    # standalone CLI
```

Consumers (test exes, user code, Python ctypes host) define neither and get `dllimport`.

**Reported upstream:** not yet.

---

## 3. 🐛 `digHoloDestroy()` segfaults on a minimally-initialized handle

**Affects:** any consumer that creates a handle and tears it down without first running the full configure-then-batch dance — error paths, smoke tests, "is this lib usable from $LANG" sanity checks, etc.

**Reproducer (Linux + Windows):**

```c
#include "digHolo.h"
int main() {
    int h = digHoloCreate();
    digHoloDestroy(h);   // <-- segfault here
    return 0;
}
```

A bare Create + Destroy crashes. Adding even one config call (`digHoloConfigSetVerbosity`) before destroy is not enough; the crash still occurs. The minimum non-crashing setup we've found is:

```c
int h = digHoloCreate();
digHoloConfigSetFrameDimensions(h, FRAME_WIDTH, FRAME_HEIGHT);
digHoloConfigSetFramePixelSize(h, PIXEL_SIZE);
digHoloConfigSetWavelengthCentre(h, LAMBDA0);
digHoloConfigSetPolCount(h, POL_COUNT);
digHoloDestroy(h);   // OK
```

**Root cause (suspected, not yet pinpointed in source):** `digHoloDestroy` walks internal data structures that are only allocated by certain config setters. When those structures are still null pointers (because the setters were never called), the destroy path dereferences them and crashes. Needs a null check / lazy-allocation guard in `digHoloDestroy`.

**Workaround in this fork (commit `595c506`):** pytest fixture `_new_configured_handle()` in `python/tests/test_smoke.py` always applies the minimum non-crashing config before any test calls `close()`. The bare-lifecycle case is no longer exercised in CI. The Python wrapper's `close()` is otherwise a thin wrapper around `digHoloDestroy` and inherits the crash for users who follow the same minimal-handle pattern.

**Reported upstream:** not yet. Needs source-level investigation to point at the offending field; the workaround is good enough to unblock CI but doesn't fix the underlying issue.

---

## 4. 🐛 Off-by-one in `digHoloUpdateReferenceWave` reference-state allocation

**Affects:** every platform, but only manifests visibly on macOS arm64 (and presumably any platform where the libc heap doesn't add padding past tiny allocations). On x86 + glibc / MSVC heaps, the stray write lands inside allocator slack and the bug is silent. On macOS arm64's tiny-zone allocator, the next call to `free()` near that block trips heap-metadata corruption and aborts in `tiny_free_no_lock` — looks for all the world like a problem inside `fitToQuadratic` (where the next free happens), with no obvious connection to the actual buggy write.

**Reproducer (macOS arm64):** any pipeline that calls `digHoloAutoAlign` with the full set of auto-align passes enabled (beam centre, tilt, defocus, basis waist, Fourier window). The regression suite's `small_window` case crashes with SIGABRT in `tiny_free_no_lock` after producing the simulator frames.

**Root cause:** `digHoloUpdateReferenceWave` packs seven per-polarisation float arrays (`TiltX, TiltY, TiltXoffset, TiltYoffset, Defocus, CentreX, CentreY`) into a single backing allocation, but sized that allocation for **six**:

```cpp
const size_t parameterCount = 6;                              // <-- bug, should be 7
allocate1D(parameterCount*polCount, digHoloRefTiltX_Valid);   // 12 floats, 48 bytes
...
digHoloRefCentreY_Valid = &digHoloRefTiltX_Valid[6 * polCount];  // points 1 past the end
```

The first write to `digHoloRefCentreY_Valid[polIdx]` (line 10406) lands at offset 48 of a 48-byte allocation — exactly one element past the tail. AddressSanitizer flags it as a heap-buffer-overflow at digHolo.cpp:10406; the original allocation is at digHolo.cpp:10261.

**Fix in this fork:** change `parameterCount` to `7` in `src/digHolo.cpp:10259`. The matching `memset` of the buffer at line 10273 is already sized off the same `parameterCount`, so it scales correctly.

**Reported upstream:** not yet. Latent on Linux/Windows but a real bug — worth filing.

---

## ✏️ Non-bug cleanups we've also done in this fork

These aren't upstream bugs per se but are worth surfacing if we ever PR back:

- **Three duplicate copies of the source** — `digHolo.{cpp,h}` at the repo root, under `src/`, and under `Examples/C++/digHolo/`. All byte-identical (line-ending-normalized). Collapsed to `src/` only (commit `49c29bc`).
- **Committed binaries** — `bin/Win64/digHolo.dll`, `bin/linux/digHolo.exe`, `lib/Win64/digHolo.lib`, `lib/linux/libdigholo.so`. Replaced with CI-published release artefacts (commits `49c29bc`, `2bbc1f9`).
- **Vendored FFTW3** — `Examples/C++/FFTW/{fftw3.h,libfftw3f-3.lib}` checked into the tree (~5.5 MB). Replaced with vcpkg manifest on Windows + `apt`/source-build on Linux (commit `49c29bc`).
- **Hand-written build recipes** — `README.md` instructed users to invoke `g++` / open Visual Studio directly. Replaced with CMake + presets (commit `49c29bc`), preserving the upstream build flags.
- **MATLAB header divergence** — `Examples/Matlab/digHolo.h` was a near-copy of `digHolo.h` with `#define NATIVE_TYPE_ONLY` enabled. Replaced with a 13-line shim that defines the macro then `#include`s `../../src/digHolo.h` (commit `49c29bc`).

---

## How to file these upstream

1. Open one issue per bug (`#1`, `#2`, `#3` above).
2. For each, attach the reproducer here verbatim and link the SAIL-Labs commit
   for reference.
3. Open three small PRs against `joelacarpenter/digHolo:main` — keep them
   independent so they can land separately. The `EXT_C` patches (#1 + #2)
   touch the same lines and could be a single combined PR if upstream prefers.
4. The cleanup items above are a separate, larger conversation — best raised
   as a single discussion / RFC issue rather than a PR.
