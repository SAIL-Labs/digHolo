# Smoke tests — kept deliberately minimal. The point is to prove the binary
# produced by CI loads, exposes the C ABI we expect, and can take a hologram
# all the way through to a modal-coefficient batch without crashing.

add_executable(test_smoke test_smoke.cpp)
target_link_libraries(test_smoke PRIVATE digHolo::digholo)
set_target_properties(test_smoke PROPERTIES CXX_STANDARD 11)

add_test(NAME smoke COMMAND test_smoke)
set_tests_properties(smoke PROPERTIES
    LABELS "smoke"
    TIMEOUT 60
)
