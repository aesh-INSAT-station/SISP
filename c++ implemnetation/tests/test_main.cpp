#include <iostream>
#include <cstdlib>

// Forward declare test functions
int test_encode_decode();
int test_payload_codec();
int test_frame_pipeline();
int test_state_machine();
int test_protocol_simulation();
int test_comprehensive_state_machine();
int test_degr();

int main() {
    std::cout << "===== SISP Protocol Unit Tests =====\n" << std::endl;

    int total_tests = 0;
    int failed_groups = 0;

    std::cout << "\n--- Encoder/Decoder Tests ---" << std::endl;
    int result = test_encode_decode();
    if (result < 0) {
        failed_groups++;
    } else {
        total_tests += result;
    }

    std::cout << "\n--- Payload Codec Tests ---" << std::endl;
    result = test_payload_codec();
    if (result < 0) {
        failed_groups++;
    } else {
        total_tests += result;
    }

    std::cout << "\n--- 512-bit Frame Pipeline Tests ---" << std::endl;
    result = test_frame_pipeline();
    if (result < 0) {
        failed_groups++;
    } else {
        total_tests += result;
    }

    std::cout << "\n--- State Machine Tests ---" << std::endl;
    result = test_state_machine();
    if (result < 0) {
        failed_groups++;
    } else {
        total_tests += result;
    }

    std::cout << "\n--- DEGR Computation Tests ---" << std::endl;
    result = test_degr();
    if (result < 0) {
        failed_groups++;
    } else {
        total_tests += result;
    }

    std::cout << "\n--- Protocol Simulation Tests ---" << std::endl;
    result = test_protocol_simulation();
    if (result < 0) {
        failed_groups++;
    } else {
        total_tests += result;
    }
    std::cout << "\n--- Comprehensive State Machine Tests (Level 2 Matrix) ---" << std::endl;
    result = test_comprehensive_state_machine();
    if (result < 0) {
        failed_groups++;
    } else {
        total_tests += result;
    }
    std::cout << "\n===== Summary =====" << std::endl;
    std::cout << "Executed tests: " << total_tests << std::endl;
    std::cout << "Failed groups: " << failed_groups << std::endl;

    return (failed_groups == 0) ? 0 : 1;
}
