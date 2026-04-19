cmake_minimum_required(VERSION 3.21)

project(digHolo
    VERSION 1.0.0
    DESCRIPTION "High-speed library for off-axis digital holography and Hermite-Gaussian decomposition"
    HOMEPAGE_URL "https://github.com/SAIL-Labs/digHolo"
    LANGUAGES CXX
)

# ---------------------------------------------------------------------------
# Project-wide settings
# ---------------------------------------------------------------------------
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Default to Release for single-config generators (Ninja, Makefiles).
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
    set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS
        Debug Release RelWithDebInfo MinSizeRel)
endif()

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
option(DIGHOLO_BUILD_SHARED        "Build digholo as a shared library"            ON)
option(DIGHOLO_BUILD_CLI           "Build the digHolo command-line executable"    ON)
option(DIGHOLO_BUILD_TESTING       "Build smoke tests against the library"        ON)
option(DIGHOLO_INSTALL             "Generate install / packaging targets"         ON)
option(DIGHOLO_FFTW_DLL            "Define FFTW_DLL (use only for shared FFTW3)"  OFF)

# When ON: produce a self-contained shared library that drops onto the user's
# system without requiring libfftw3, libstdc++, or libgcc to be installed at a
# specific version. Strongly recommended for any artefact that's published for
# external consumption (release tarballs, Python wheels). Linux-only — Windows
# already gets static FFTW3 via vcpkg's x64-windows-static-md triplet, and the
# MSVC runtime is universally available via VC++ Redistributable.
option(DIGHOLO_PREFER_STATIC_DEPS  "Prefer static FFTW3 + libstdc++/libgcc"       OFF)

# ---------------------------------------------------------------------------
# Architecture requirements
#
# digHolo's SIMD core was originally written against x86-64 AVX2 + FMA3. On
# Apple Silicon we route the same intrinsics through simde → NEON, so arm64
# is also accepted on Apple hosts. Other architectures (arm64 Linux, other
# POSIX) are still unsupported.
# ---------------------------------------------------------------------------
set(DIGHOLO_IS_APPLE_SILICON OFF)
if(APPLE AND CMAKE_SYSTEM_PROCESSOR MATCHES "(arm64|aarch64)")
    set(DIGHOLO_IS_APPLE_SILICON ON)
endif()

if(NOT (CMAKE_SYSTEM_PROCESSOR MATCHES "(x86_64|AMD64|x64)" OR DIGHOLO_IS_APPLE_SILICON))
    message(FATAL_ERROR
        "digHolo supports x86-64 with AVX2 + FMA3 (Linux, Windows) or "
        "Apple Silicon (arm64 macOS, via simde + Accelerate). "
        "Detected system: ${CMAKE_SYSTEM_NAME} / ${CMAKE_SYSTEM_PROCESSOR}.")
endif()

if(APPLE AND NOT DIGHOLO_IS_APPLE_SILICON)
    message(FATAL_ERROR
        "x86_64 macOS is not supported — Intel MKL is not redistributed for "
        "macOS in modern oneAPI releases. Build on arm64 macOS (simde + "
        "Accelerate) or on Linux/Windows (MKL).")
endif()

# ---------------------------------------------------------------------------
# Dependency: FFTW3 (single precision)
# IMPORTANT: FFTW3 must appear in the link line BEFORE Intel MKL, otherwise
# MKL's FFTW-compatible interface will be picked instead — and MKL does not
# implement the real-to-real DCTs used by digHolo's AutoAlign routine.
# ---------------------------------------------------------------------------
set(_DIGHOLO_FFTW_TARGET "")

if(DIGHOLO_PREFER_STATIC_DEPS AND NOT WIN32)
    # Bypass FFTW3Config.cmake / pkg-config (both return whichever library
    # variant upstream packaged — usually the shared one on Linux) and locate
    # the static archive directly.
    find_path(FFTW3F_INCLUDE_DIR fftw3.h)
    find_library(FFTW3F_LIBRARY NAMES libfftw3f.a)
    if(NOT FFTW3F_INCLUDE_DIR OR NOT FFTW3F_LIBRARY)
        message(FATAL_ERROR
            "Static FFTW3f (libfftw3f.a) not found — required with "
            "DIGHOLO_PREFER_STATIC_DEPS=ON. On Debian/Ubuntu install "
            "libfftw3-dev (which ships libfftw3f.a alongside the shared lib); "
            "on AlmaLinux/RHEL install fftw-static; or build FFTW3 from "
            "source with --enable-static --enable-single -fPIC.")
    endif()
    add_library(digholo_fftw3f INTERFACE)
    target_include_directories(digholo_fftw3f INTERFACE "${FFTW3F_INCLUDE_DIR}")
    target_link_libraries(digholo_fftw3f INTERFACE "${FFTW3F_LIBRARY}")
    set(_DIGHOLO_FFTW_TARGET digholo_fftw3f)
else()
    # Preferred: vcpkg / installed CMake config. Try both package-name
    # conventions: vcpkg's fftw3 port (and recent upstream FFTW3 ≥ 3.3.10)
    # ships `FFTW3Config.cmake` and exports `FFTW3::fftw3f` for single
    # precision. Some older / Linux-distro packages install
    # `FFTW3fConfig.cmake` instead. Try both.
    find_package(FFTW3f CONFIG QUIET)
    if(NOT TARGET FFTW3::fftw3f)
        find_package(FFTW3 CONFIG QUIET)
    endif()
    if(TARGET FFTW3::fftw3f)
        set(_DIGHOLO_FFTW_TARGET FFTW3::fftw3f)
    endif()

    # Fallback: pkg-config (Linux distros)
    if(NOT _DIGHOLO_FFTW_TARGET)
        find_package(PkgConfig QUIET)
        if(PkgConfig_FOUND)
            pkg_check_modules(FFTW3F IMPORTED_TARGET fftw3f)
            if(TARGET PkgConfig::FFTW3F)
                set(_DIGHOLO_FFTW_TARGET PkgConfig::FFTW3F)
            endif()
        endif()
    endif()

    # Last resort: manual find_path / find_library
    if(NOT _DIGHOLO_FFTW_TARGET)
        find_path(FFTW3F_INCLUDE_DIR fftw3.h)
        find_library(FFTW3F_LIBRARY NAMES fftw3f libfftw3f-3 libfftw3f)
        if(NOT FFTW3F_INCLUDE_DIR OR NOT FFTW3F_LIBRARY)
            message(FATAL_ERROR
                "FFTW3 (single precision) not found. Install libfftw3-dev "
                "(Linux) or run vcpkg with the supplied vcpkg.json manifest "
                "(Windows).")
        endif()
        add_library(digholo_fftw3f INTERFACE)
        target_include_directories(digholo_fftw3f INTERFACE "${FFTW3F_INCLUDE_DIR}")
        target_link_libraries(digholo_fftw3f INTERFACE "${FFTW3F_LIBRARY}")
        set(_DIGHOLO_FFTW_TARGET digholo_fftw3f)
    endif()
endif()

message(STATUS "digHolo: using FFTW3f target = ${_DIGHOLO_FFTW_TARGET}")
if(FFTW3F_LIBRARY)
    message(STATUS "digHolo: FFTW3f library file = ${FFTW3F_LIBRARY}")
endif()
get_target_property(_DIGHOLO_FFTW_LOC ${_DIGHOLO_FFTW_TARGET} LOCATION)
if(_DIGHOLO_FFTW_LOC AND NOT _DIGHOLO_FFTW_LOC STREQUAL "_DIGHOLO_FFTW_LOC-NOTFOUND")
    message(STATUS "digHolo: FFTW3f resolved location = ${_DIGHOLO_FFTW_LOC}")
endif()
get_target_property(_DIGHOLO_FFTW_INCS ${_DIGHOLO_FFTW_TARGET} INTERFACE_INCLUDE_DIRECTORIES)
if(_DIGHOLO_FFTW_INCS)
    message(STATUS "digHolo: FFTW3f include dirs   = ${_DIGHOLO_FFTW_INCS}")
endif()

# Sanity check: refuse to link against Intel MKL's FFTW-compatible interface
# stub (fftw3f.lib under the oneAPI tree) — it's missing the real-to-real DCTs
# that AutoAlign needs. If the manual find_library accidentally walked the
# MKL lib dir on Windows and picked it up, fail loudly with a clear message.
if(FFTW3F_LIBRARY MATCHES "[Ii]ntel.*one[Aa][Pp][Ii]")
    message(FATAL_ERROR
        "Refusing to use Intel MKL's FFTW-compatible interface as the "
        "FFTW3 backend (found at ${FFTW3F_LIBRARY}). This stub is missing "
        "the real-to-real DCTs digHoloAutoAlign requires. "
        "Install a real FFTW3 (vcpkg fftw3 / libfftw3-dev) and ensure its "
        "CMake config is on CMAKE_PREFIX_PATH ahead of MKL.")
endif()

if(DIGHOLO_PREFER_STATIC_DEPS)
    message(STATUS "digHolo: DIGHOLO_PREFER_STATIC_DEPS=ON (portable shared lib)")
endif()

# ---------------------------------------------------------------------------
# Dependency: BLAS + LAPACK
#
# x86-64 (Linux, Windows): Intel MKL via oneAPI. Requires setvars.{sh,bat}
# sourced so the CMake config is on CMAKE_PREFIX_PATH.
#
# Apple Silicon: the Accelerate framework, using the modern LAPACK interface
# introduced in macOS 13.3 (ACCELERATE_NEW_LAPACK, LP64 int-sized).
# ---------------------------------------------------------------------------
if(DIGHOLO_IS_APPLE_SILICON)
    find_library(ACCELERATE_FRAMEWORK Accelerate REQUIRED)
    message(STATUS "digHolo: using Apple Accelerate framework = ${ACCELERATE_FRAMEWORK}")

    # Homebrew's FFTW3 splits the threads API into a separate dylib
    # (libfftw3f_threads.dylib), whereas the Linux CI build compiles FFTW3
    # without --enable-threads and bundles no-op thread stubs into the main
    # libfftw3f. digHolo.cpp calls fftwf_init_threads / fftwf_plan_with_nthreads
    # unconditionally, so we need the separate threads lib on macOS.
    find_library(FFTW3F_THREADS_LIBRARY NAMES fftw3f_threads libfftw3f_threads
                 HINTS ${FFTW3F_INCLUDE_DIR}/../lib /opt/homebrew/lib /usr/local/lib)
    if(NOT FFTW3F_THREADS_LIBRARY)
        message(FATAL_ERROR
            "libfftw3f_threads not found. On macOS install via Homebrew: "
            "`brew install fftw` (ships libfftw3f_threads.dylib).")
    endif()
    message(STATUS "digHolo: FFTW3f threads lib = ${FFTW3F_THREADS_LIBRARY}")
else()
    set(MKL_INTERFACE   "lp64"       CACHE STRING "MKL integer interface")
    set(MKL_THREADING   "sequential" CACHE STRING "MKL threading layer")
    set(MKL_LINK        "static"     CACHE STRING "MKL link mode (static/dynamic)")

    find_package(MKL CONFIG REQUIRED)
endif()

# ---------------------------------------------------------------------------
# Dependency: simde (Apple Silicon only — translates x86 AVX2/FMA3 intrinsics
# to NEON at compile time). Pulled via FetchContent and pinned; the tag
# is baked in so builds are reproducible across machines.
# ---------------------------------------------------------------------------
if(DIGHOLO_IS_APPLE_SILICON)
    include(FetchContent)
    FetchContent_Declare(
        simde
        GIT_REPOSITORY https://github.com/simd-everywhere/simde.git
        GIT_TAG        v0.8.2
        GIT_SHALLOW    TRUE
    )
    FetchContent_MakeAvailable(simde)

    # simde is header-only; expose its include dir as an INTERFACE target.
    add_library(digholo_simde INTERFACE)
    target_include_directories(digholo_simde INTERFACE
        "${simde_SOURCE_DIR}"
    )
    message(STATUS "digHolo: simde headers = ${simde_SOURCE_DIR}")
endif()

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
set(DIGHOLO_PUBLIC_HEADERS src/digHolo.h)
set(DIGHOLO_SOURCES        src/digHolo.cpp)

# ---------------------------------------------------------------------------
# Helper: apply common compile settings to a target compiled from digHolo.cpp
# ---------------------------------------------------------------------------
function(_digholo_apply_compile_settings target)
    target_include_directories(${target}
        PUBLIC
            $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>
            $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
    )

    if(MSVC)
        target_compile_options(${target} PRIVATE
            /arch:AVX2
            $<$<CONFIG:Release>:/O2>
            $<$<CONFIG:Release>:/Oi>      # intrinsics
            /D_CRT_SECURE_NO_WARNINGS
        )
    else()
        if(DIGHOLO_IS_APPLE_SILICON)
            # simde handles intrinsic translation — no -mavx2/-mfma needed.
            target_compile_options(${target} PRIVATE
                $<$<CONFIG:Release>:-O3>
            )
        else()
            target_compile_options(${target} PRIVATE
                -mavx2 -mfma
                $<$<CONFIG:Release>:-O3>
            )
        endif()
    endif()

    if(DIGHOLO_FFTW_DLL)
        target_compile_definitions(${target} PRIVATE FFTW_DLL)
    endif()

    # Link FFTW3 *first*, then the BLAS/LAPACK backend — order matters for
    # the MKL path (MKL also ships an FFTW-compatible interface that lacks
    # the real-to-real DCTs digHolo needs; FFTW must win the symbol race).
    if(DIGHOLO_IS_APPLE_SILICON)
        target_link_libraries(${target} PRIVATE
            ${_DIGHOLO_FFTW_TARGET}
            ${FFTW3F_THREADS_LIBRARY}
            ${ACCELERATE_FRAMEWORK}
            digholo_simde
        )
        target_compile_definitions(${target} PRIVATE
            DIGHOLO_USE_ACCELERATE
            ACCELERATE_NEW_LAPACK
            DIGHOLO_USE_SIMDE
        )
    else()
        target_link_libraries(${target} PRIVATE
            ${_DIGHOLO_FFTW_TARGET}
            MKL::MKL
        )
    endif()

    if(UNIX AND NOT APPLE)
        target_link_libraries(${target} PRIVATE pthread m dl)
    endif()

    # Portable Linux artefacts: static-link libstdc++ + libgcc so the output
    # runs on any distro with a recent-enough glibc (set by the build host —
    # manylinux_2_28 gives glibc 2.28 → RHEL 8 / Ubuntu 18.04+). digholo's
    # public API is extern "C" only, so swallowing the C++ runtime into the
    # binary is safe — no C++ ABI crosses the library boundary.
    if(DIGHOLO_PREFER_STATIC_DEPS AND UNIX AND NOT APPLE)
        target_link_options(${target} PRIVATE
            -static-libstdc++
            -static-libgcc
        )
    endif()
endfunction()

# ---------------------------------------------------------------------------
# Library target
# ---------------------------------------------------------------------------
if(DIGHOLO_BUILD_SHARED)
    add_library(digholo SHARED ${DIGHOLO_SOURCES} ${DIGHOLO_PUBLIC_HEADERS})
else()
    add_library(digholo STATIC ${DIGHOLO_SOURCES} ${DIGHOLO_PUBLIC_HEADERS})
endif()
add_library(digHolo::digholo ALIAS digholo)

_digholo_apply_compile_settings(digholo)

# DIGHOLO_BUILDING tells digHolo.h to use __declspec(dllexport) on Windows.
# Consumers (test exes, user code, Python ctypes host) never have this
# defined, so they see __declspec(dllimport) — proper cross-DLL linkage.
target_compile_definitions(digholo PRIVATE DIGHOLO_BUILDING)

set_target_properties(digholo PROPERTIES
    OUTPUT_NAME    digholo
    VERSION        ${PROJECT_VERSION}
    SOVERSION      ${PROJECT_VERSION_MAJOR}
    PUBLIC_HEADER  "${DIGHOLO_PUBLIC_HEADERS}"
)

# ---------------------------------------------------------------------------
# CLI executable target
#
# The library translation unit also defines `main()` — so the executable is
# produced by simply rebuilding src/digHolo.cpp as an executable, matching the
# build recipe documented in the upstream README. This avoids modifying the
# upstream source.
# ---------------------------------------------------------------------------
if(DIGHOLO_BUILD_CLI)
    add_executable(digholo-cli ${DIGHOLO_SOURCES})
    set_target_properties(digholo-cli PROPERTIES OUTPUT_NAME digHolo)
    _digholo_apply_compile_settings(digholo-cli)
    # CLI compiles the library source standalone into an exe — no DLL
    # surface exposed. DIGHOLO_STATIC_BUILD makes EXT_C a plain extern "C"
    # with no dllexport/dllimport, which:
    #   * prevents MSVC from creating a digHolo.lib + digHolo.exp next
    #     to digHolo.exe (those would clash with digholo.lib /
    #     digholo.exp from the shared library on case-insensitive
    #     Windows filesystems and corrupt the test-exe's link).
    #   * avoids the dllimport-on-definitions linker error.
    target_compile_definitions(digholo-cli PRIVATE DIGHOLO_STATIC_BUILD)
endif()

# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------
if(DIGHOLO_BUILD_TESTING)
    enable_testing()
    add_subdirectory(tests)
endif()

# ---------------------------------------------------------------------------
# Python wheel install (only when invoked by scikit-build-core)
#
# scikit-build-core sets ${SKBUILD} when building a wheel, and reads the
# component-tagged install rules below. The shared library lands next to
# the package's __init__.py inside the wheel, where the Python loader can
# find it via a relative path.
# ---------------------------------------------------------------------------
if(SKBUILD)
    install(TARGETS digholo
        LIBRARY DESTINATION digholo COMPONENT python
        RUNTIME DESTINATION digholo COMPONENT python
        ARCHIVE EXCLUDE_FROM_ALL
    )
    install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/digHolo.h"
        DESTINATION digholo/include
        COMPONENT   python
    )
endif()

# ---------------------------------------------------------------------------
# Install / packaging
# ---------------------------------------------------------------------------
if(DIGHOLO_INSTALL)
    install(TARGETS digholo
        EXPORT  digHoloTargets
        LIBRARY        DESTINATION ${CMAKE_INSTALL_LIBDIR}
        ARCHIVE        DESTINATION ${CMAKE_INSTALL_LIBDIR}
        RUNTIME        DESTINATION ${CMAKE_INSTALL_BINDIR}
        PUBLIC_HEADER  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
    )

    if(DIGHOLO_BUILD_CLI)
        install(TARGETS digholo-cli
            RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
        )
    endif()

    install(EXPORT digHoloTargets
        FILE        digHoloTargets.cmake
        NAMESPACE   digHolo::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/digHolo
    )

    write_basic_package_version_file(
        "${CMAKE_CURRENT_BINARY_DIR}/digHoloConfigVersion.cmake"
        VERSION       ${PROJECT_VERSION}
        COMPATIBILITY SameMajorVersion
    )
    install(FILES "${CMAKE_CURRENT_BINARY_DIR}/digHoloConfigVersion.cmake"
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/digHolo
    )
endif()

# ---------------------------------------------------------------------------
# Build summary
# ---------------------------------------------------------------------------
message(STATUS "")
message(STATUS "digHolo ${PROJECT_VERSION} build configuration")
message(STATUS "  Build type             : ${CMAKE_BUILD_TYPE}")
message(STATUS "  Shared library         : ${DIGHOLO_BUILD_SHARED}")
message(STATUS "  CLI executable         : ${DIGHOLO_BUILD_CLI}")
message(STATUS "  Smoke tests            : ${DIGHOLO_BUILD_TESTING}")
message(STATUS "  Install targets        : ${DIGHOLO_INSTALL}")
message(STATUS "  FFTW3f target          : ${_DIGHOLO_FFTW_TARGET}")
if(DIGHOLO_IS_APPLE_SILICON)
    message(STATUS "  BLAS/LAPACK backend    : Apple Accelerate")
else()
    message(STATUS "  MKL link / threading   : ${MKL_LINK} / ${MKL_THREADING}")
endif()
message(STATUS "")
