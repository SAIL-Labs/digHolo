cmake_minimum_required(VERSION 3.21)

# Wheel-build wrapper for the digholo Python package.
#
# This file is the CMake entry point that scikit-build-core invokes when
# building a wheel. It pulls in the parent project (which actually compiles
# libdigholo) and then installs the resulting shared library into the
# Python package's directory inside the wheel.
#
# Build order, conceptually:
#   1. scikit-build-core configures this CMakeLists with sane CMake options
#      defined in [tool.scikit-build.cmake.define] (see pyproject.toml).
#   2. add_subdirectory(..) below kicks off the regular digholo build
#      (static FFTW3 + libstdc++ on Linux; vcpkg-static FFTW3 on Windows).
#   3. The install() rule below copies the produced shared library into
#      `digholo/` inside the wheel, where the Python loader can find it.

project(digholo_wheel
    VERSION 1.0.0
    LANGUAGES CXX
)

# Force-disable parts of the parent build that the wheel doesn't need. These
# match the [tool.scikit-build.cmake.define] block in pyproject.toml — set
# here too so the build still works if invoked directly without the backend.
set(DIGHOLO_BUILD_SHARED       ON  CACHE BOOL "" FORCE)
set(DIGHOLO_BUILD_CLI          OFF CACHE BOOL "" FORCE)
set(DIGHOLO_BUILD_TESTING      OFF CACHE BOOL "" FORCE)
set(DIGHOLO_INSTALL            OFF CACHE BOOL "" FORCE)
set(DIGHOLO_PREFER_STATIC_DEPS ON  CACHE BOOL "" FORCE)

# Bring in the parent project. Output goes into a subdirectory of our build
# tree so it doesn't collide with the parent's standalone build dir.
add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/.." digholo_native)

# ---------------------------------------------------------------------------
# Install the shared library into the wheel
# ---------------------------------------------------------------------------
# scikit-build-core installs everything tagged with the `python` component
# into the wheel's site-packages root. Putting `digholo.dll` / `libdigholo.so`
# next to the package's __init__.py means the loader can find it via a
# relative path with zero environment fiddling.
install(TARGETS digholo
    LIBRARY     DESTINATION digholo COMPONENT python
    RUNTIME     DESTINATION digholo COMPONENT python
    ARCHIVE EXCLUDE_FROM_ALL
)

# Also vendor the public header so power users can poke at the C ABI from
# their own ctypes / cffi code.
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/../src/digHolo.h"
    DESTINATION digholo/include
    COMPONENT python
)
