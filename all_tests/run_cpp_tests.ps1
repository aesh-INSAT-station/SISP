$ErrorActionPreference = "Stop"

$Root = Resolve-Path "$PSScriptRoot\.."
$CppRoot = Join-Path $Root "c++ implemnetation"
$DllOutDir = Join-Path $CppRoot "build\bin\Release"
$DllOut = Join-Path $DllOutDir "sisp.dll"
$RunnerOut = Join-Path $CppRoot "test_runner_manual.exe"

if (-not (Get-Command g++.exe -ErrorAction SilentlyContinue)) {
    throw "g++.exe not found on PATH. Install MinGW-w64/GCC or add it to PATH."
}

New-Item -ItemType Directory -Force -Path $DllOutDir | Out-Null

Set-Location $CppRoot

Write-Host "Building sisp.dll with g++..."
g++.exe -std=c++17 -O2 -Wall -Wextra -Iinclude -shared -static `
    src/sisp_protocol.cpp `
    src/sisp_encoder.cpp `
    src/sisp_decoder.cpp `
    src/sisp_state_machine.cpp `
    src/sisp_degr.cpp `
    src/sisp_correction.cpp `
    src/sim_hooks.cpp `
    -o $DllOut
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Building C++ test runner with g++..."
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
    -o $RunnerOut
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $RunnerOut
exit $LASTEXITCODE
