Set-Location "$PSScriptRoot\..\c++ implemnetation\build"
cmake --build . --config Release
.\Release\test_runner.exe
