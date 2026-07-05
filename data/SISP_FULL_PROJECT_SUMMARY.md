# SISP — Complete Project Summary

## Executive Summary

SISP is a full-stack CubeSat cooperative protocol and anomaly/correction system built to enable autonomous sensor correction, data relay, and sensor borrowing in small-satellite constellations. The project includes:
- a production-style C++ protocol stack with a deterministic 21-state finite state machine,
- a Python-based SVD anomaly detection pipeline for OPSSAT-AD telemetry,
- a physical-layer UHF 437 MHz dual-PHY study with energy and sustainability dashboards,
- a comprehensive test suite with 273 C++ tests and multiple Python integration scenarios.

Key achievements from the repo:
- 273/273 C++ tests pass,
- 94.3% RMSE improvement in the 30-day correction scenario,
- 85.6% improvement under 10% packet loss,
- 12.5 kHz + 25 kHz dual-PHY UHF design,
- Per-correction overhead under 0.022% of a 5 W daily energy budget,
- Reported orbital sustainability savings of roughly 3,100 t CO₂/yr for a 100-sat constellation.

The documentation is extensive and research-oriented, with a formal paper, KPI snapshot, detailed state machine description, SVD methodology, correction algorithm analysis, signal physics study, energy study, and test-results summary.

---

## Repository Layout & Tech Stack

### Layout

```
SISP/
├── c++ implemnetation/              # C++ protocol library + tests + build outputs
├── docs/                            # research paper + detailed design READMEs
├── simulation for signal and physics/ # orbital geometry, PHY, energy, dashboards
├── all_tests/                       # Python integration tests
├── pipelines/                       # ingestion/preprocess/SVD pipeline wrappers
├── sisp/                            # Python SVD/anomaly pipeline package
├── data/raw/                        # source OPSSAT-AD telemetry dataset
├── logs/                            # generated test logs
├── python_satellite_sim_v2.py       # multi-satellite Python harness
└── README.md                        # quick start and project overview
```

### Tech Stack

- C++ protocol implementation and simulation hooks
- Python 3 pipelines and harnesses
- Streamlit dashboards for PHY and sustainability visualization
- `numpy`, `scipy`, `matplotlib`, `streamlit`, `skyfield`
- `pandas`, `pyarrow`, `scikit-learn`, `joblib` for SVD anomaly detection
- `ctypes`-based Python harness to drive the C++ DLL
- MSVC / CMake build artifacts present under `c++ implemnetation/build`

The repo also includes full path management, pipeline orchestration, and reproducible artifact generation patterns.

---

## Research, Documentation & Innovation

The project is documented in a research-paper style with an academic-sounding `SISP_RESEARCH_PAPER.md` and a KPI snapshot for slide-ready numbers. It also includes:
- a full architecture document,
- a deep state machine breakdown,
- an SVD + chi-square anomaly detection design note,
- an in-depth correction algorithm comparison,
- a UHF signal physics and energy study,
- sustainability dashboards and long-term impact modeling.

The innovation claims are supported by:
- `README_06_TEST_RESULTS.md` summarizing exact log-derived outcomes,
- `SISP_KPI_SNAPSHOT.md` with launch-cost and CO₂ savings calculations,
- `simulation for signal and physics/sisp_value_dashboard.py` showing live-energy and climate-impact metrics.

The repo is loyal to its own data and does not depend on external claims beyond referenced literature and the OPSSAT-AD dataset.

---

## System Architecture

### Core services

SISP is built around three autonomous inter-satellite services:
1. **Correction** — a satellite with degraded sensors broadcasts a correction request, collects neighbour readings, and computes a corrected estimate.
2. **Relay** — a satellite with low energy or lost ground contact requests a neighbour to relay mission data during an ISL window.
3. **Borrow** — a satellite requests a healthy neighbour’s sensor data stream for continuous monitoring.

These services are coordinated by a single deterministic state machine in C++ and a fixed 64-byte frame protocol.

### Protocol layers

- **Frame codec**: fixed 64-byte frames, CRC-8/MAXIM checksum, 5-byte compact header, 59-byte payload/extension region.
- **Service codes**: typed payloads for correction, relay, borrow, heartbeat, status, failure.
- **Dual-PHY**: 12.5 kHz narrow control PHY and 25 kHz bulk PHY on the same 437 MHz band.
- **DEGR scoring**: neighbour degradation score from Kalman k-factor, SVD residual, age, and orbit error.

The implementation separates protocol transport from correction algorithms, making the filter layer pluggable and the state machine deterministic.

---

## State Machine

### States (21 total)

1. `IDLE`
2. `CORR_WAIT_RSP`
3. `CORR_COLLECTING`
4. `CORR_COMPUTING`
5. `CORR_DONE`
6. `CORR_RESPONDING`
7. `RELAY_WAIT_ACCEPT`
8. `RELAY_SENDING`
9. `RELAY_WAIT_ACK`
10. `RELAY_DONE`
11. `RELAY_RECEIVING`
12. `RELAY_STORING`
13. `RELAY_DOWNLINKING`
14. `BORROW_WAIT_ACCEPT`
15. `BORROW_RECEIVING`
16. `BORROW_DONE`
17. `BORROW_SAMPLING`
18. `BORROW_SENDING`
19. `TIMEOUT`
20. `ERROR`
21. `CRITICAL_FAIL`

### Events (24 total)

- `RX_CORRECTION_REQ`
- `RX_CORRECTION_RSP`
- `RX_RELAY_REQ`
- `RX_RELAY_ACCEPT`
- `RX_RELAY_REJECT`
- `RX_DOWNLINK_DATA`
- `RX_DOWNLINK_ACK`
- `RX_STATUS_BROADCAST`
- `RX_HEARTBEAT`
- `RX_HEARTBEAT_ACK`
- `RX_BORROW_REQ`
- `RX_FAILURE`
- `FAULT_DETECTED` (12)
- `TIMER_EXPIRED` (13)
- `ENERGY_LOW` (14)
- `GS_VISIBLE` (15)
- `GS_LOST` (16)
- `ALL_FRAGS_SENT` (17)
- `ALL_FRAGS_RCVD` (18)
- `SENSOR_READ_DONE` (19)
- `CORRECTION_DONE` (20)
- `CRITICAL_FAILURE` (21)
- `RESET` (22)
- `RX_BORROW_DECISION` (23)

### Correction flow

- `IDLE + FAULT_DETECTED` → `CORR_WAIT_RSP`: broadcast correction request, set timer.
- `CORR_WAIT_RSP + RX_CORRECTION_RSP` → `CORR_COLLECTING`: buffer neighbour readings and DEGR weights.
- `CORR_COLLECTING + TIMER_EXPIRED` → `CORR_COMPUTING`: run the configured correction filter.
- `CORR_COMPUTING + CORRECTION_DONE` → `IDLE`.

### Relay flow

- `IDLE + ENERGY_LOW` → `RELAY_WAIT_ACCEPT`: broadcast relay request.
- `RELAY_WAIT_ACCEPT + RX_RELAY_ACCEPT` → `RELAY_SENDING`: fragment and send bulk data.
- `RELAY_SENDING + ALL_FRAGS_SENT` → `RELAY_WAIT_ACK`.
- `RELAY_WAIT_ACK + RX_DOWNLINK_ACK` → `RELAY_DONE`.

### Borrow flow

- `IDLE + GS_VISIBLE` → `BORROW_WAIT_ACCEPT`: broadcast borrow request.
- `BORROW_WAIT_ACCEPT + RX_BORROW_DECISION` → `BORROW_RECEIVING`.
- `BORROW_RECEIVING + ALL_FRAGS_RCVD` → `BORROW_DONE`.

### Failure isolation

- `ANY + RX_FAILURE` stays in the same state while recording a remote failure; it does not cascade.
- `ANY + CRITICAL_FAILURE` transitions the local satellite to `CRITICAL_FAIL` and broadcasts a failure frame.
- `RESET` returns any state to `IDLE`.

### Implementation notes

- The state machine is a static 21×24 transition table for O(1) dispatch.
- The context is ~2 KB and uses no heap allocations in its core path.
- The `select_tx_phy()` function chooses between control narrowband and bulk wideband PHY based on service and peer capability.

---

## SVD Anomaly Detection

### Dataset and pipeline

- Dataset: OPSSAT-AD telemetry segments from `data/raw/segments.csv`.
- Features: 19 hand-engineered telemetry features per segment.
- Metadata: `segment`, `anomaly`, `train`, `channel`.
- Pipeline files: `sisp/`, `pipelines/run_ingest.py`, `pipelines/run_preprocess.py`, `pipelines/run_svd.py`.

### Preprocessing steps

1. Drop rows with >30% missing values.
2. Median-impute remaining NaNs using fit rows only.
3. Detect zero-variance features on fit rows and optionally convert them to binary deviation indicators.
4. Winsorize feature values at the 1st and 99th percentiles.
5. Standard scale features to zero mean and unit variance.

### Rank selection and scoring

- Fit a TruncatedSVD on normal training rows only (`train=True` and `anomaly=False`).
- Select rank `k` so cumulative explained variance ≥ 90%, clamped to [2, 15].
- Reconstruct rows and compute squared L2 reconstruction error.
- Use the 95th percentile of fit-row errors as the anomaly threshold.

### Chi-square gating

- The residual is evaluated against a chi-square distribution with `k` degrees of freedom.
- The NIS gate rejects readings whose normalized error exceeds the 95% chi-square critical value.
- This is used in the NIS-gated Kalman variant.

### Operational integration

- Correction responses are screened by SVD and, if configured, chi-square gating before entering the correction buffer.
- This prevents corrupted or anomalous neighbour readings from biasing the filter.

---

## Correction Algorithms

### Pluggable interface

The C++ correction module exposes:
- `CorrectionInput`: up to 8 neighbour readings + weights.
- `CorrectionOutput`: corrected vector, confidence, used count.
- `CorrectionFilter` abstract base class.

Available implementations:
- `WeightedMedianFilter`
- `KalmanFilter`
- `HybridFilter` (weighted median + Kalman)

The active filter can be switched at runtime and the protocol layer remains unchanged.

### DEGR weighting

DEGR is a 0–15 degradation score computed from:
- Kalman k-factor deviation,
- SVD residual magnitude,
- satellite age,
- orbit error.

Weight formula:

```text
w_i = max(0.05, 1 - DEGR_i / 15)
```

This gives healthy neighbours weight ≈ 1.0 and degraded neighbours a minimum weight of 0.05.

### Algorithms and their strengths

- **Weighted Median**: robust to outliers, independent per axis, O(n log n), breakdown point 50%.
- **Kalman**: 6-state constant-velocity model, temporal smoothing, optimal under Gaussian noise.
- **Hybrid**: robust prefilter + Kalman smoothing; recommended for mixed conditions.
- **NIS-gated Kalman**: adds chi-square innovation rejection; useful for impulsive spikes but can over-reject during persistent bias.

### Benchmark highlights

From the repo data:
- Kalman corrected error 0.504 vs raw 8.909 in the 30-day drift scenario (94.3% improvement).
- Under 10% packet loss, corrected RMSE 1.197 vs raw 8.290 (85.6% improvement).
- Weighted median is less effective in Gaussian noise but still robust to bias.
- Hybrid is the strongest default for mixed/adversarial conditions.

---

## Physical Layer & Dual-PHY

### Frequency & modulation

- Target band: 435–438 MHz amateur satellite allocation.
- Control PHY: 12.5 kHz, GMSK BT=0.3, 12.5 kbps.
- Bulk PHY: 25 kHz, GMSK BT=0.3, 25 kbps.
- Message: 64-byte fixed frame.

### FEC and air bits

- Convolutional code: K=7, R=1/2.
- Reed-Solomon: RS(255,223), t=16.
- Combined expansion: ≈ 2.287×.
- A 512-bit frame becomes ~1,171 air bits.

### Link budget and performance

- Reference 1,000 km link margin ≈ +3.3 dB at 437 MHz with 1 W TX and 2 dBi omni antennas.
- Maximum usable range for PER ≤ 1%:
  - Control 12.5 kHz ≈ 2,800 km,
  - Bulk 25 kHz ≈ 2,100 km.
- Doppler at 437 MHz in LEO can reach ~10.9 kHz, making robust constant-envelope modulation desirable.

### BER/PER validation

- Monte Carlo BPSK AWGN validation with 500,000 bits matches theory within Monte Carlo noise.
- PER for 64-byte frames is computed as `1 - (1-p)^{512}`.
- With the reference budget, PER at 8.8 dB Eb/N0 is approximately 0.01%.

### Dual-PHY selection logic

- Bulk PHY is used only for `DOWNLINK_DATA` and `DOWNLINK_ACK` when both sender and receiver advertise support.
- All control-service frames remain on the narrow control PHY.
- Tests confirm 8/8 dual-PHY assertions pass.

---

## Energy, Sustainability & KPIs

### Protocol-level energy

- Frame time with Conv+RS on 12.5 kHz: 93.6 ms.
- One correction event with 6 neighbours: ~7 frames, ~3.90 J network energy.
- Daily correction energy with 24 events: ~26.0 mWh.
- This is ~0.022% of a 5 W spacecraft daily budget.

### Bulk relay energy

- 1 MiB relay over 25 kHz GMSK Conv+RS: ~6.1 min, 1.26 Wh total.
- 10 MiB relay: ~61 min, 12.6 Wh.
- 1 MiB fits within a 15-min LoS window; 10 MiB does not.

### Sustainability KPIs

The repo models launch and CO₂ savings using assumptions such as:
- 100-satellite constellation,
- 3 year baseline design life,
- 45% life extension with SISP,
- 300 t CO₂ per launch,
- 60% failure recovery via borrowing.

Reported results include:
- 10.3 fewer replacement launches per year for 100 satellites,
- 3,100 t CO₂ avoided per year,
- 23,000 launches avoided in 50 years,
- 7 Mt CO₂ avoided in 50 years.

The `sisp_value_dashboard.py` streamlit app exposes these assumptions and calculations transparently.

---

## Test Coverage & Validation

### C++ tests

- 273 total tests in `c++ implemnetation/tests/`.
- Coverage includes encoder/decoder, payload codec, frame pipeline, state machine, DEGR computation, protocol simulation.
- All pass in the repo.

### Python tests

- Integration scenarios in `all_tests/` including:
  - `test_dual_phy_437.py`
  - `test_kalman_gaussian_3sat.py`
  - `test_noise_weighting_and_algorithms.py`
  - `test_integration_matrix_it02_it03_it05_it06.py`
  - `test_relay_text_resilience.py`
  - `test_borrow_addressing_flow.py`
  - `test_no_cascade.py`
- The Python harness uses `ctypes` to load the C++ DLL and drive state-machine behavior.

### Notable results

- `test_dual_phy_437.py`: 8/8 assertions pass.
- `test_relay_text_resilience.py`: robust fragment recovery across corrupted, out-of-order, and duplicate packets.
- `test_no_cascade.py`: confirmed no cascading CRITICAL_FAIL across peers.
- `test_integration_matrix_it02_it03_it05_it06.py`: integration test matrix covering DEGR, relay, 30-day correction, packet loss.

---

## Running the Project

### Python pipeline

```bash
pip install -r requirements.txt
python pipelines/run_ingest.py
python pipelines/run_preprocess.py
python pipelines/run_svd.py
```

### C++ test suite

```powershell
"c++ implemnetation/build/Release/test_runner.exe"
```

### Physical simulations

```bash
streamlit run "simulation for signal and physics/sisp_unified_sim.py"
streamlit run "simulation for signal and physics/sisp_value_dashboard.py"
```

### SVD anomaly tool

```bash
python sisp_svd_anomaly.py --list-channels
python sisp_svd_anomaly.py --channel CADC0894 --plot
```

---

## Accuracy and Fidelity Notes

This summary is based only on repository contents and documentation. It does not invent capabilities or external claims beyond what is present in these files.

### Strongly supported facts

- The exact 21 state machine states and 24 event codes are present in `c++ implemnetation/include/sisp_state_machine.hpp`.
- The SVD pipeline and rank/threshold rules are documented in the repo docs and code.
- The dual-PHY 12.5/25 kHz architecture is implemented in `src/sisp_state_machine.cpp` and tested in `test_dual_phy_437.py`.
- Energy and CO₂ KPIs are computed in `docs/SISP_KPI_SNAPSHOT.md` and `simulation for signal and physics/sisp_value_dashboard.py`.

### What is not explicitly present

- No explicit United Nations SDG targets are coded anywhere in the repo.
- The project authorship is limited to "SISP Team — AESH 2026 Hackathon" in the research paper.

---

## Further improvement path

A follow-on review should verify every numeric claim by tracing it to the source file or log excerpt, especially:
- 94.3% and 85.6% improvement values,
- 0.022% energy budget figure,
- 1.26 Wh per 1 MiB relay,
- 300 t CO₂ per launch and cumulative CO₂ savings.

This document is ready for use as the single comprehensive project overview in the repo.
