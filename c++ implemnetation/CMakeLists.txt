cmake_minimum_required(VERSION 3.15)
project(SISP_Protocol 
        VERSION 1.0.0 
        DESCRIPTION "Satellite Inter-Service Protocol (SISP) C++ Implementation"
        LANGUAGES CXX)

# Require C++17
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Compiler flags for warnings and optimization
if(MSVC)
    add_compile_options(/Wall /W4)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -fPIC)
endif()

# Add optimization flags for embedded compatibility
add_compile_options(-O2)

# Include directories
include_directories(${CMAKE_SOURCE_DIR}/include)

# Source files
set(SISP_SOURCES
    src/sisp_protocol.cpp
    src/sisp_encoder.cpp
    src/sisp_decoder.cpp
    src/sisp_state_machine.cpp
    src/sisp_degr.cpp
    src/sim_hooks.cpp
)

# Main library
add_library(sisp SHARED ${SISP_SOURCES})

# Set library output directory
set_target_properties(sisp PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

# Testing
enable_testing()

# Test executable
add_executable(test_runner
    tests/test_encode_decode.cpp
    tests/test_payload_codec.cpp
    tests/test_frame_pipeline.cpp
    tests/test_state_machine.cpp
    tests/test_degr.cpp
    tests/test_main.cpp
    ${SISP_SOURCES}
)

add_test(NAME SISPTests COMMAND test_runner)

# Compiler flags for tests
if(NOT MSVC)
    target_compile_options(test_runner PRIVATE -fPIC)
endif()

# Print build info
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "SISP library will be built in ${CMAKE_BINARY_DIR}/lib")
