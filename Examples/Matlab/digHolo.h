/*
 * MATLAB-compatible shim around the canonical digHolo header.
 *
 * MATLAB's loadlibrary() cannot cope with the complex64 typedef (a C struct
 * containing a float[2]), so we enable NATIVE_TYPE_ONLY before including the
 * real header. This collapses complex64 to a bare float, and any complex array
 * then has twice the length with interleaved real/imaginary components.
 *
 * Keep this file as a one-liner shim only — the authoritative API declarations
 * live in src/digHolo.h.
 */
#define NATIVE_TYPE_ONLY
#include "../../src/digHolo.h"
