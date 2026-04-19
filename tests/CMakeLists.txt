# Smoke tests — kept deliberately minimal. The point is to prove the binary
# produced by CI loads, exposes the C ABI we expect, and can take a hologram
# all the way through to a modal-coefficient batch without crashing.

add_executable(test_smoke test_smoke.cpp)
target_link_libraries(test_smoke PRIVATE digHolo::digholo)
set_target_properties(test_smoke PROPERTIES CXX_STANDARD 11)

# On Windows the Visual Studio generator puts targets under per-config subdirs,
# so the test exe and digholo.dll end up in different directories. Copy any
# runtime DLLs next to the test exe so the loader finds them. No-op on Linux
# (build-tree rpath handles it).
#
# CMake's $<TARGET_RUNTIME_DLLS:test_smoke> only lists DLLs that come from
# IMPORTED targets — first-party in-tree shared libraries are excluded. So
# we copy $<TARGET_FILE:digholo> explicitly in addition to the imported set.
if(WIN32)
    add_custom_command(TARGET test_smoke POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:digholo> $<TARGET_FILE_DIR:test_smoke>
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_RUNTIME_DLLS:test_smoke> $<TARGET_FILE_DIR:test_smoke>
        COMMAND_EXPAND_LISTS
    )
endif()

add_test(NAME smoke COMMAND test_smoke)
set_tests_properties(smoke PROPERTIES
    LABELS "smoke"
    TIMEOUT 60
)

# ---------------------------------------------------------------------------
# Numerical regression test — diffs against reference output generated on
# Linux/x86. Gated on the reference data being committed: if the settings
# file isn't present, the test is silently skipped so this scaffolding can
# land without blocking CI.
# ---------------------------------------------------------------------------
set(DIGHOLO_REFERENCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/reference")
if(EXISTS "${DIGHOLO_REFERENCE_DIR}/reference_settings.txt")
    add_executable(test_reference test_reference.cpp)
    target_link_libraries(test_reference PRIVATE digHolo::digholo)
    set_target_properties(test_reference PROPERTIES CXX_STANDARD 11)

    if(WIN32)
        add_custom_command(TARGET test_reference POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                    $<TARGET_FILE:digholo> $<TARGET_FILE_DIR:test_reference>
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                    $<TARGET_RUNTIME_DLLS:test_reference> $<TARGET_FILE_DIR:test_reference>
            COMMAND_EXPAND_LISTS
        )
    endif()

    add_test(NAME reference
             COMMAND test_reference "${DIGHOLO_REFERENCE_DIR}")
    set_tests_properties(reference PROPERTIES
        LABELS "reference"
        TIMEOUT 120
    )
else()
    message(STATUS
        "digHolo tests: reference data not present at ${DIGHOLO_REFERENCE_DIR} — "
        "skipping test_reference (scaffolding only; commit reference binaries "
        "to enable).")
endif()
