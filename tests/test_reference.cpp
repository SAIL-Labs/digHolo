// Numerical regression test — compares digHolo output against a reference
// buffer generated on Linux/x86 (see tests/reference/README.md).
//
// Gated in CTest on the reference files existing; if they're not present
// (which is the initial state after landing this scaffolding), the test
// is not added to the test list and is a no-op.
//
// Run via CTest: `ctest --output-on-failure -L reference`.

#include "digHolo.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr double kRelTol = 1e-4;
constexpr double kAbsTol = 1e-6;

bool readBinary(const std::string& path, std::vector<float>& out) {
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    std::fseek(f, 0, SEEK_END);
    long bytes = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    if (bytes < 0 || bytes % sizeof(float) != 0) { std::fclose(f); return false; }
    out.resize(static_cast<size_t>(bytes) / sizeof(float));
    size_t got = std::fread(out.data(), sizeof(float), out.size(), f);
    std::fclose(f);
    return got == out.size();
}

int compareWithTolerance(const std::vector<float>& actual,
                         const std::vector<float>& expected) {
    if (actual.size() != expected.size()) {
        std::fprintf(stderr,
            "[reference] FAIL: size mismatch — actual %zu, expected %zu\n",
            actual.size(), expected.size());
        return 1;
    }
    for (size_t i = 0; i < actual.size(); ++i) {
        const double a = actual[i];
        const double e = expected[i];
        const double tol = std::max(kAbsTol, kRelTol * std::fabs(e));
        if (std::fabs(a - e) > tol) {
            std::fprintf(stderr,
                "[reference] FAIL at element %zu: actual=%.9g expected=%.9g "
                "diff=%.3g tol=%.3g\n",
                i, a, e, a - e, tol);
            return 1;
        }
    }
    return 0;
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: %s <reference_dir>\n", argv[0]);
        return 2;
    }
    const std::string refDir = argv[1];
    std::string settingsPath = refDir + "/reference_settings.txt";
    const std::string expectedPath = refDir + "/reference_coefs.bin";
    const std::string actualPath   = refDir + "/actual_coefs.bin";

    // Run the CLI via the library's batch entry point — mirrors what
    // `digHolo digHoloSettings.txt` does internally. The settings file is
    // responsible for writing coefficients to actual_coefs.bin in the
    // reference directory, matching the path the diff below reads.
    std::vector<char> settingsPathMut(settingsPath.begin(), settingsPath.end());
    settingsPathMut.push_back('\0');
    int rc = digHoloRunBatchFromConfigFile(settingsPathMut.data());
    if (rc != 0) {
        std::fprintf(stderr,
            "[reference] FAIL: digHoloRunBatchFromConfigFile returned %d\n", rc);
        return 1;
    }

    std::vector<float> actual;
    std::vector<float> expected;
    if (!readBinary(actualPath, actual)) {
        std::fprintf(stderr,
            "[reference] FAIL: could not read actual output at %s\n",
            actualPath.c_str());
        return 1;
    }
    if (!readBinary(expectedPath, expected)) {
        std::fprintf(stderr,
            "[reference] FAIL: could not read expected output at %s\n",
            expectedPath.c_str());
        return 1;
    }

    int failures = compareWithTolerance(actual, expected);
    if (failures == 0) {
        std::fprintf(stdout,
            "[reference] ok: %zu floats within tolerance (rtol=%.0e, atol=%.0e)\n",
            actual.size(), kRelTol, kAbsTol);
    }
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
