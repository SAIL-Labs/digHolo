# Reference Test Data

This directory holds ground-truth outputs that `tests/test_reference.cpp`
diffs against. On a cross-platform port you want at least one test that
catches subtle numerical drift (a misrouted intrinsic, a BLAS call that
defaults to a different convention, etc.); this is that test.

## Generating the reference data

1. Check out the repo on a Linux x86-64 host, at a commit where the build
   is known-good against the upstream `main`. Record the commit hash.
2. Build with the `linux-release` preset. Run the CLI with a fixed settings
   file (see `reference_settings.txt` in this directory — to be committed
   alongside the generated output) and record its output binaries.
3. Commit the settings file and output binaries into this directory.
4. Record the source commit hash, compiler version, MKL version, and FFTW
   version in `reference_manifest.txt` for future forensics.

## Expected files (not yet committed)

- `reference_settings.txt` — input settings for the CLI (tab-delimited,
  same format as `Examples/C++/digHoloDemo/digHoloSettings.txt`). The
  settings file must write the output coefficients to `actual_coefs.bin`
  in this directory (the test reads that path).
- `reference_frames.bin`  — input hologram frame buffer referenced from
  `reference_settings.txt`.
- `reference_coefs.bin`   — expected output coefficient buffer.
- `reference_manifest.txt` — generation provenance (commit hash, compiler
  version, MKL version, FFTW version, date).

## Tolerance

- **Relative**: 1e-4 (for magnitudes ≥ 1e-3)
- **Absolute**: 1e-6 (for magnitudes < 1e-3)

The per-element check is `|actual - expected| <= max(atol, rtol * |expected|)`.

## Why this tolerance

simde's AVX2→NEON translation is semantically equivalent but not bitwise
identical — floating-point add/mul reordering and fused-vs-unfused
multiply-add produce last-bit differences. Accelerate's GEMM/SVD also
differs from MKL's at the last few bits. 1e-4 relative is generous enough
to tolerate those without admitting a real bug (e.g. a 1-bit sign flip in
an intrinsic translation would produce an O(1) relative error).

## Enabling the test

`tests/CMakeLists.txt` only registers `test_reference` with CTest if
`reference_settings.txt` exists in this directory. Until that file is
committed, the test is silently skipped on all platforms. After the
files are in place:

```
ctest --preset macos-release -L reference
```
