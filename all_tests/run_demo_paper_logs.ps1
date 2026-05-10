$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$Root = Resolve-Path "$PSScriptRoot\.."
$LogDir = Join-Path $Root "logs\demo_paper"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = "python"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $Root

function Run-Logged {
    param(
        [string]$Name,
        [string[]]$Command
    )

    $LogPath = Join-Path $LogDir "$Name.log"
    Write-Host "=== $Name ==="
    Write-Host "Log: $LogPath"

    $started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "=== $Name | started $started ===" | Set-Content -Path $LogPath -Encoding utf8
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Command[0] @($Command[1..($Command.Length - 1)]) 2>&1 | Tee-Object -FilePath $LogPath -Append
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode. See $LogPath"
    }
    $ended = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "=== $Name | finished $ended ===" | Add-Content -Path $LogPath -Encoding utf8
}

Run-Logged "cpp_gpp_protocol_tests" @("powershell", "-ExecutionPolicy", "Bypass", "-File", "all_tests\run_cpp_tests.ps1")
Run-Logged "python_protocol_tests" @("powershell", "-ExecutionPolicy", "Bypass", "-File", "all_tests\run_python_tests.ps1")
Run-Logged "dataset_algorithm_comparison" @($Py, "all_tests\test_dataset_algorithm_comparison.py")
Run-Logged "noise_weighting_algorithms" @($Py, "all_tests\test_noise_weighting_and_algorithms.py")
Run-Logged "kalman_gaussian_3sat" @($Py, "all_tests\test_kalman_gaussian_3sat.py")
Run-Logged "full_message_pipeline" @($Py, "all_tests\test_full_message_propagation_sensor_correction.py")
Run-Logged "protocol_scale_heavy" @($Py, "all_tests\scale_testing\run_protocol_scale.py", "--tier", "heavy", "--repeats", "1")
Run-Logged "satellite_sim_v1" @($Py, "python_satellite_sim.py")
Run-Logged "satellite_sim_v2_auto" @($Py, "python_satellite_sim_v2.py", "--auto")
Run-Logged "bpsk_awgn_validation" @($Py, "simulation for signal and physics\validate_bpsk_awgn.py", "--bits", "200000")
Run-Logged "orbital_geometry" @($Py, "simulation for signal and physics\orbital geometry.py")

Write-Host ""
Write-Host "Demo/paper logs written to: $LogDir"
