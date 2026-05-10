$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

Set-Location "$PSScriptRoot\.."
python .\all_tests\test_no_cascade.py
python .\all_tests\test_correction_propagation.py
python .\all_tests\test_kalman_gaussian_3sat.py
python .\all_tests\test_noise_weighting_and_algorithms.py
python .\all_tests\test_integration_matrix_it02_it03_it05_it06.py
python .\all_tests\test_full_message_propagation_sensor_correction.py
python .\all_tests\test_borrow_addressing_flow.py
python .\all_tests\test_relay_text_resilience.py
