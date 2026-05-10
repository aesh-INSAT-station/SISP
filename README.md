# SISP Unified Guide

This file is the single source of truth for:
- protocol usage
- where and how to modify protocol behavior
- where and how to tune SVD, chi-square, and Kalman logic
- all test workflows

## 1) Project At A Glance

SISP is a satellite inter-service protocol implementation with:
- fixed-size frame transport and packet payload codecs
- state machine service flows (correction, relay, borrow, heartbeat, failure)
- pluggable correction filters (weighted median, Kalman, hybrid)
- C++ test runner and Python simulation and analysis harnesses

Primary folders:
- `c++ implemnetation/include` - protocol types, state-machine API, correction interfaces, sim hooks
- `c++ implemnetation/src` - protocol codec, state machine logic, correction algorithms, simulation bridge
- `c++ implemnetation/tests` - C++ test groups
- `all_tests` - Python integration and scenario tests

## 2) Quick Start

### Build C++

From repo root:

```powershell
Set-Location .\c++ implemnetation\build
cmake --build . --config Release
```

### Run C++ tests

```powershell
Set-Location .\c++ implemnetation\build\Release
.\test_runner.exe
```

### Run Python tests bundle

```powershell
Set-Location .\all_tests
.\run_python_tests.ps1
```

### Run key Python scenarios directly

```powershell
Set-Location ..
python .\all_tests\test_relay_text_resilience.py
python .\all_tests\test_borrow_addressing_flow.py
python .\python_satellite_sim.py --packet-loss-rate 0.10 --seed 42 --max-response-frames 50
```

## 3) Protocol Usage

### Core C++ integration points

Header and payload model:
- `c++ implemnetation/include/sisp_protocol.hpp`

Codec entry points:
- `c++ implemnetation/src/sisp_encoder.cpp`
- `c++ implemnetation/src/sisp_decoder.cpp`

State machine:
- `c++ implemnetation/include/sisp_state_machine.hpp`
- `c++ implemnetation/src/sisp_state_machine.cpp`

Simulation bridge for Python:
- `c++ implemnetation/include/sim_hooks.hpp`
- `c++ implemnetation/src/sim_hooks.cpp`

### Python usage pattern

1. Create per-satellite contexts with `sim_create_context`.
2. Register a TX callback with `sim_register_tx_callback`.
3. Route frames to targets with `sim_inject_packet`.
4. Inject internal events with `sim_inject_event`.
5. Read state and metrics with `sim_get_state`, `sim_get_degr`, and payload-copy helpers.

Reference scripts:
- `python_satellite_sim.py`
- `all_tests/test_relay_text_resilience.py`
- `all_tests/test_borrow_addressing_flow.py`

## 4) Addressing And Communication Semantics

Broadcast:
- Requests that seek responders are sent to receiver `0xFF`.
- Example: `BORROW_REQ`, `RELAY_REQ`, correction request broadcasts.

Unicast:
- Acceptance/decision and payload data are sent to specific receiver IDs.
- Example: `BORROW_DECISION` provider -> borrower, `DOWNLINK_DATA` accepted peer -> requester.

Current multi-answer borrow behavior:
- First delivered `BORROW_DECISION` moves borrower to `BORROW_RECEIVING` and sets `peer_id`.
- Later decisions are ignored in that state unless transitions are extended.

## 5) Where To Modify Protocol Behavior

### Service definitions and payload schema

Edit:
- `c++ implemnetation/include/sisp_protocol.hpp`
- `c++ implemnetation/src/sisp_protocol.cpp`

Use this when changing:
- service codes
- payload structures
- serialize/deserialize logic
- DEGR formula inputs and bucketing

### State transitions and service actions

Edit:
- `c++ implemnetation/src/sisp_state_machine.cpp`

Use this when changing:
- event-to-state transition table
- retry/timeout behavior
- per-service send/store/ack actions
- relay and borrow flow edge cases

### Python simulation API

Edit:
- `c++ implemnetation/include/sim_hooks.hpp`
- `c++ implemnetation/src/sim_hooks.cpp`

Use this when adding:
- new Python-visible helpers
- custom simulation injection utilities
- extra diagnostics for tests

## 6) SVD, Chi-Square, And Kalman: Exact Edit Points

### SVD pipeline (Python data path)

Run the dataset pipeline end-to-end (uses repo-root `dataset.csv` if present, otherwise downloads):

```powershell
python .\ingest.py
python .\preprocess.py
python .\svd_pipeline.py
```

Force a specific local file and prevent downloading:

```powershell
python .\ingest.py --input .\dataset.csv --no-download
```

Primary file:
- `svd_pipeline.py`

Key knobs:
- `TARGET_EXPLAINED_VARIANCE`
- `MIN_COMPONENTS`
- `MAX_COMPONENTS`
- `THRESHOLD_PERCENTILE`
- `CHI_SQUARE_CONFIDENCE`

Key functions:
- `select_rank_k(...)` for rank/component selection
- `score_channel_and_write_results(...)` for reconstruction error scoring

### Chi-square thresholding (Python)

Primary file:
- `svd_pipeline.py`

Key functions:
- `approximate_chi_square_critical(dof, confidence)`
- chi-square statistic and threshold usage in `score_channel_and_write_results(...)`

What to tune:
- confidence level
- residual scaling strategy
- decision rule and reporting outputs

### Kalman and correction algorithms (C++)

Interfaces and implementations:
- `c++ implemnetation/include/sisp_correction.hpp`
- `c++ implemnetation/src/sisp_correction.cpp`

Modify these classes:
- `KalmanFilter` for process/measurement/noise/state update policy
- `WeightedMedianFilter` for robust weighting behavior
- `HybridFilter` for median+Kalman chaining

Where correction is called from protocol flow:
- `action_run_kalman` in `c++ implemnetation/src/sisp_state_machine.cpp`

Where filter is selected from simulation:
- `sim_use_kalman_filter`, `sim_use_weighted_median_filter`, `sim_use_hybrid_filter` in `c++ implemnetation/src/sim_hooks.cpp`

## 7) Full Testing In One Place

### C++ tests (single executable)

Main runner:
- `c++ implemnetation/tests/test_main.cpp`

Groups:
- `test_encode_decode.cpp`
- `test_payload_codec.cpp`
- `test_frame_pipeline.cpp`
- `test_state_machine.cpp`
- `test_degr.cpp`
- `test_protocol_simulation.cpp`
- `test_comprehensive_matrix.cpp`

Run:

```powershell
Set-Location .\c++ implemnetation\build\Release
.\test_runner.exe
```

### Python tests and scenario matrix

Batch scripts:
- `all_tests/run_cpp_tests.ps1`
- `all_tests/run_python_tests.ps1`

High-value scenarios:
- `all_tests/test_relay_text_resilience.py` - multi-fragment relay with checksum corruption, out-of-order delivery, duplicate replay
- `all_tests/test_borrow_addressing_flow.py` - borrow request/decision/data addressing and drop modeling
- `all_tests/test_integration_matrix_it02_it03_it05_it06.py` - IT-02/03/05/06 integration matrix
- `all_tests/test_noise_weighting_and_algorithms.py` - weighting and algorithm sensitivity
- `all_tests/test_kalman_gaussian_3sat.py` - Kalman performance profile

## 8) Recommended Change Workflow

1. Modify one subsystem at a time.
2. Rebuild C++.
3. Run `test_runner.exe`.
4. Run relevant Python scenario tests.
5. If behavior changed intentionally, update this file in the same commit.

## 9) Branching And Push (Parallel To Main)

Example workflow:

```powershell
git checkout -b parallel-main/unified-protocol-guide
git add README.md
git commit -m "docs: unify protocol, algorithm tuning, and testing guide"
git push -u origin parallel-main/unified-protocol-guide
```

This keeps a clean branch in parallel to `main` for review and merge.
