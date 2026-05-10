$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

Set-Location "$PSScriptRoot\.."

# ── Protocol correctness ─────────────────────────────────────────────────
python .\all_tests\test_no_cascade.py
python .\all_tests\test_correction_propagation.py
python .\all_tests\test_borrow_addressing_flow.py
python .\all_tests\test_relay_text_resilience.py

# ── Dual-PHY 437 MHz ────────────────────────────────────────────────────
python .\all_tests\test_dual_phy_437.py

# ── Correction algorithms ────────────────────────────────────────────────
python .\all_tests\test_kalman_gaussian_3sat.py
python .\all_tests\test_noise_weighting_and_algorithms.py
python .\all_tests\test_full_message_propagation_sensor_correction.py

# ── Integration matrix ───────────────────────────────────────────────────
python .\all_tests\test_integration_matrix_it02_it03_it05_it06.py
