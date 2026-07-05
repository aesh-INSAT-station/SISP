# SISP Summary Review Agent

## Purpose

This document defines a review checklist and validation process for the generated `SISP_FULL_PROJECT_SUMMARY.md` file.
It is intended as a lightweight "sub-agent" guide that reads the summary, checks every fact against repository sources, and returns feedback for improvement.

## Review Process

1. **Check source fidelity**
   - For every numeric claim in `SISP_FULL_PROJECT_SUMMARY.md`, identify the exact source file or documentation.
   - Confirm whether the claim is present in:
     - `README.md`
     - `docs/*.md`
     - `c++ implemnetation/include/*.hpp`
     - `c++ implemnetation/src/*.cpp`
     - `all_tests/*.py`
     - simulation scripts under `simulation for signal and physics/`
   - Mark each claim as: verified, likely, or unsupported.

2. **Validate enumerated state machine details**
   - Verify the 21 states and 24 events against `c++ implemnetation/include/sisp_state_machine.hpp`.
   - Confirm the event integer codes for `FAULT_DETECTED`, `TIMER_EXPIRED`, `ENERGY_LOW`, and `CRITICAL_FAILURE` match the implementation.

3. **Validate dual-PHY and PHY selection**
   - Confirm `select_tx_phy()` logic in `c++ implemnetation/src/sisp_state_machine.cpp` matches the summary.
   - Confirm the bulk profile is only selected for `DOWNLINK_DATA` / `DOWNLINK_ACK` and when peer capability permits.

4. **Verify SVD anomaly metadata**
   - Confirm the `config/settings.py` constants for `SVD_VARIANCE_TARGET`, `SVD_K_MIN`, `SVD_K_MAX`, and `ANOMALY_THRESHOLD_PCTILE`.
   - Confirm preprocessing rules in `sisp/preprocessing/` and the `fit_mask` behavior.

5. **Verify correction algorithm claims**
   - Confirm the existence of `WeightedMedianFilter`, `KalmanFilter`, and `HybridFilter` in `c++ implemnetation/include/sisp_correction.hpp`.
   - Confirm the hybrid recommendation is supported by benchmark tables in docs and tests.

6. **Verify energy and sustainability numbers**
   - Confirm the 93.6 ms frame time, 0.022% daily budget, 1.26 Wh for 1 MiB, and CO₂ savings figures from `docs/SISP_KPI_SNAPSHOT.md` and `simulation for signal and physics/sisp_value_dashboard.py`.
   - If any number originates only from dashboard assumptions, mark it clearly as assumption-based.

7. **Check test coverage claims**
   - Confirm 273 C++ tests and the presence of `test_dual_phy_437.py`, `test_kalman_gaussian_3sat.py`, `test_noise_weighting_and_algorithms.py`, and `test_integration_matrix_it02_it03_it05_it06.py`.
   - Confirm python tests exercise dual-PHY, no-cascade failures, relay fragmentation, and correction quality.

8. **Identify missing or misleading statements**
   - Highlight any summary statement that overreaches beyond repo evidence.
   - If SDG or sustainability language is used, verify that it is phrased as derived from energy/launch/CO₂ models rather than claimed as UN-defined SDG metrics.

## Feedback format

Provide results in this structure:

1. Verified facts
   - List source file or doc reference for each fact.
2. Corrections needed
   - List incorrect or unsupported statements.
3. Suggestions for improvement
   - Propose more precise wording or additional source citations.
4. Confidence notes
   - Note any claims that are "likely" but not explicitly present in repo text.

## Example feedback item

- `94.3% RMSE improvement` — verified from `docs/SISP_KPI_SNAPSHOT.md` and `docs/README_06_TEST_RESULTS.md`.
- `SDG target mention` — unsupported; repo contains sustainability and CO₂ impact, but no explicit SDG labels.
- `1 MiB relay energy 1.26 Wh` — verified from `docs/README_05_ENERGY_STUDY.md` and `docs/SISP_KPI_SNAPSHOT.md`.

## Usage

This review-agent guide should be used after generating a draft summary to catch overstatements, ensure accurate citations, and strengthen the final document’s faithfulness to repository content.
