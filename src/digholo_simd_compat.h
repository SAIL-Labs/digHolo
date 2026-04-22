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

    // simde exposes the rounding-mode constants as SIMDE_MM_* but does NOT
    // alias them back to the unprefixed x86 names under
    // SIMDE_ENABLE_NATIVE_ALIASES. digHolo uses the bare names directly in
    // _mm256_round_ps / _mm256_round_pd calls, so alias them here.
    #ifndef _MM_FROUND_TO_NEAREST_INT
        #define _MM_FROUND_TO_NEAREST_INT SIMDE_MM_FROUND_TO_NEAREST_INT
    #endif
    #ifndef _MM_FROUND_NO_EXC
        #define _MM_FROUND_NO_EXC SIMDE_MM_FROUND_NO_EXC
    #endif
    #ifndef _MM_ROUND_NEAREST
        #define _MM_ROUND_NEAREST SIMDE_MM_ROUND_NEAREST
    #endif

    // _mm_malloc / _mm_free are x86-specific aligned allocators exposed by
    // Intel's <xmmintrin.h>, NOT by the AVX2 intrinsic surface simde covers.
    // digHolo.cpp aliases alignedAllocate / alignedFree onto them, so we
    // polyfill them here for arm64 using posix_memalign. Signature matches
    // Intel's: (size, alignment) → void*.
    #include <cstddef>
    #include <cstdlib>

    static inline void* _mm_malloc(std::size_t size, std::size_t alignment) {
        // posix_memalign requires alignment to be a power of two and at
        // least sizeof(void*); round up so callers passing small alignments
        // (e.g. 16) still succeed on 64-bit hosts where sizeof(void*) == 8.
        if (alignment < sizeof(void*)) alignment = sizeof(void*);
        void* p = nullptr;
        if (::posix_memalign(&p, alignment, size) != 0) return nullptr;
        return p;
    }
    static inline void _mm_free(void* p) { ::free(p); }
#else
    #include <immintrin.h>
#endif
