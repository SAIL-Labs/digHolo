// Smoke test — exercises the minimal digHolo pipeline end-to-end using the
// built-in synthetic frame simulator (no external data files required). Run
// via CTest: `ctest --output-on-failure -L smoke`.
//
// The assertions below are intentionally loose — the goal is to prove that:
//   * the shared library loads and symbols resolve,
//   * the handle lifecycle works,
//   * ProcessBatch produces a non-null coefficient pointer of the expected shape.
// It is NOT a numerical-accuracy test.

#include "digHolo.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {

int check(bool cond, const char* msg) {
    if (!cond) {
        std::fprintf(stderr, "[smoke] FAIL: %s\n", msg);
        return 1;
    }
    std::fprintf(stdout, "[smoke] ok:   %s\n", msg);
    return 0;
}

} // namespace

int main() {
    // --- Tiny synthetic batch ----------------------------------------------
    const int   frameCount  = 4;
    const int   frameWidth  = 320;
    const int   frameHeight = 256;
    const float pixelSize   = 20e-6f;
    const int   polCount    = 2;
    const float lambda0     = 1565e-9f;

    float* frameBuffer = digHoloFrameSimulatorCreateSimple(
        frameCount, frameWidth, frameHeight, pixelSize, polCount, lambda0, /*printToConsole*/ 0);

    int failures = 0;
    failures += check(frameBuffer != nullptr,
        "digHoloFrameSimulatorCreateSimple returned a buffer");
    if (!frameBuffer) return failures;

    // --- Create handle + configure the pipeline -----------------------------
    int handleIdx = digHoloCreate();
    failures += check(handleIdx >= 0, "digHoloCreate returned a valid handle");

    digHoloConfigSetVerbosity(handleIdx, 0); // silent
    digHoloConfigSetFramePixelSize(handleIdx, pixelSize);
    digHoloConfigSetFrameDimensions(handleIdx, frameWidth, frameHeight);
    digHoloConfigSetWavelengthCentre(handleIdx, lambda0);
    digHoloConfigSetPolCount(handleIdx, polCount);
    digHoloConfigSetfftWindowSizeX(handleIdx, 128);
    digHoloConfigSetfftWindowSizeY(handleIdx, 128);
    digHoloConfigSetIFFTResolutionMode(handleIdx, 1);
    digHoloConfigSetBasisGroupCount(handleIdx, 3); // keep the basis tiny

    // --- Run the pipeline ---------------------------------------------------
    digHoloSetBatch(handleIdx, frameCount, frameBuffer);
    digHoloAutoAlign(handleIdx);

    int         gotBatch = 0;
    int         gotModes = 0;
    int         gotPols  = 0;
    complex64*  coefs    = digHoloProcessBatch(handleIdx, &gotBatch, &gotModes, &gotPols);

    failures += check(coefs != nullptr,        "digHoloProcessBatch returned coefficients");
    failures += check(gotBatch == frameCount,  "coefficient batch count matches input");
    failures += check(gotPols  == polCount,    "coefficient pol count matches config");
    failures += check(gotModes >  0,           "coefficient mode count is positive");

    // --- Teardown -----------------------------------------------------------
    digHoloDestroy(handleIdx);
    digHoloFrameSimulatorDestroy(frameBuffer);

    std::fprintf(stdout, "[smoke] %d failure(s)\n", failures);
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
