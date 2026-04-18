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
if(WIN32)
    add_custom_command(TARGET test_smoke POST_BUILD
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
