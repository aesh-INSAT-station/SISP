$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\.."
$CppRoot = Join-Path $Root "c++ implemnetation"
$BuildDir = Join-Path $CppRoot "build"
$NinjaDir = Join-Path $CppRoot "build_ninja"

if (Test-Path (Join-Path $BuildDir "CMakeCache.txt")) {
    Set-Location $BuildDir
    cmake --build . --config Release
    .\Release\test_runner.exe
    exit $LASTEXITCODE
}

if (Get-Command g++.exe -ErrorAction SilentlyContinue) {
    Set-Location $CppRoot
    g++.exe -std=c++17 -O2 -Wall -Wextra -Iinclude `
        tests/test_encode_decode.cpp `
        tests/test_payload_codec.cpp `
        tests/test_frame_pipeline.cpp `
        tests/test_state_machine.cpp `
        tests/test_protocol_simulation.cpp `
        tests/test_comprehensive_matrix.cpp `
        tests/test_degr.cpp `
        tests/test_main.cpp `
        src/sisp_protocol.cpp `
        src/sisp_encoder.cpp `
        src/sisp_decoder.cpp `
        src/sisp_state_machine.cpp `
        src/sisp_degr.cpp `
        src/sisp_correction.cpp `
        src/sim_hooks.cpp `
        -o test_runner_manual.exe
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    .\test_runner_manual.exe
    exit $LASTEXITCODE
}

if (Test-Path (Join-Path $NinjaDir "CMakeCache.txt")) {
    Set-Location $NinjaDir
    cmake --build .
    .\test_runner.exe
    exit $LASTEXITCODE
}

throw "No usable C++ build path found. Expected CMake cache or g++.exe."
