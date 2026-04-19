// SIMD intrinsic include shim for digHolo.
//
// On x86-64 (Linux, Windows) we use the native AVX2/FMA3 intrinsics from
// <immintrin.h>. On Apple Silicon we route the same intrinsic names through
// simde, which translates them to NEON at compile time.
//
// The translation is transparent at the call site: SIMDE_ENABLE_NATIVE_ALIASES
// causes simde to expose unprefixed names (__m256, _mm256_add_ps, _mm_fmadd_ps,
// etc), so ~912 AVX2/FMA3 references in digHolo.cpp compile unchanged.

#pragma once

#if defined(DIGHOLO_USE_SIMDE)
    #define SIMDE_ENABLE_NATIVE_ALIASES
    #include <simde/x86/avx2.h>
    #include <simde/x86/fma.h>
#else
    #include <immintrin.h>
#endif
