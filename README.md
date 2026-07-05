# SISP — Satellite Inter-Service Protocol

A cooperative, self-healing satellite protocol stack for CubeSat constellations.
Satellites correct degraded sensors, relay data across visibility gaps, and borrow
healthy sensors from neighbours - fully autonomously, with no ground intervention.

**273/273 C++ tests pass · 94.3% RMSE improvement (IT-05) · 12.5 kHz + 25 kHz dual-PHY**

---

## Repository Layout

```
SISP/
│
├── c++ implemnetation/          Protocol C++ library
│   ├── include/                 Headers: protocol, state machine, correction, sim hooks
│   ├── src/                     Implementations: codec, state machine, correction, bridge
│   ├── tests/                   273 unit + integration tests
│   └── build/Release/           Prebuilt: sisp.dll, test_runner.exe
│
├── simulation/                  JS/Cesium protocol visualizer (React + Three.js)
│   ├── src/                     Simulation engine, state machine, OPS-SAT detector
│   ├── server/                  BRIDGE DLL server (websocket → C++ bindings)
│   ├── package.json             → npm install && npm run dev → http://localhost:5173
│   └── README.md
│
├── simulation for signal and physics/   Physical layer + sustainability analysis
│   ├── sisp_unified_sim.py      Streamlit: geometry, BER/PER, energy, dual-PHY  → port 8501
│   ├── sisp_value_dashboard.py  Streamlit: sustainability & impact KPIs          → port 8501
│   ├── validate_bpsk_awgn.py    Monte Carlo BER validation
│   ├── requirements.txt
│   └── legacy documentation/    Archived study notes (preserved for reference)
│
├── sisp/                        SVD anomaly detection Python package
│   ├── anomaly/svd.py           Rank selection, model fitting, reconstruction error
│   ├── preprocessing/           Scaler, cleaner, metadata extraction
│   ├── io/                      CSV/parquet loader and writer
│   └── utils/                   Paths and helpers
│
├── sisp_svd_anomaly.py          SVD anomaly detection CLI (entry point)
├── python_satellite_sim_v2.py   Level-3 multi-satellite Python harness (C++ DLL bindings)
│
├── pipelines/                   Batch-processing run scripts
│   ├── run_ingest.py
│   ├── run_preprocess.py
│   └── run_svd.py
│
├── scripts/                     Utility scripts
│   ├── inspect_artifacts.py
│   ├── energy_audit.py
│   └── preprocess_segments_for_js.py
│
├── all_tests/                   Python integration test suite
│   ├── test_dual_phy_437.py     Dual-PHY PHY-profile correctness (8/8 PASS)
│   ├── test_integration_matrix_it02_it03_it05_it06.py
│   ├── test_kalman_gaussian_3sat.py
│   ├── test_noise_weighting_and_algorithms.py
│   └── scale_testing/           Scale/capacity tests
│
├── data/raw/segments.csv        OPSSAT-AD telemetry dataset (303k rows, 8 channels)
│
├── config/settings.py           Shared configuration
│
└── docs/                        Research paper + detailed READMEs
    ├── SISP_RESEARCH_PAPER.md   Full academic paper (8 sections, references)
    ├── SISP_KPI_SNAPSHOT.md     Static KPI tables (formulas, sources, all numbers)
    ├── SISP_REAL_TEST_RESULTS.md  OPS-SAT detector validation + correction/relay tests
    ├── README_00_OVERVIEW.md    Project overview and key numbers
    ├── README_01_STATE_MACHINE.md
    ├── README_02_SVD_CHI_SQUARE.md
    ├── README_03_CORRECTION_ALGORITHMS.md
    ├── README_04_SIGNAL_PHYSICS.md
    ├── README_05_ENERGY_STUDY.md
    └── README_06_TEST_RESULTS.md
```

---

## Quick Start

### 1. Install dependencies

```bash
# Install everything (SVD pipeline + simulation + dashboards):
pip install -r requirements.txt
```

`requirements.txt` covers three groups — annotated by which component uses each:

| Group | Packages | Used by |
|---|---|---|
| SVD pipeline | `pandas`, `pyarrow`, `requests`, `scikit-learn`, `joblib` | `sisp_svd_anomaly.py`, `sisp/`, `pipelines/` |
| Simulation & dashboards | `numpy`, `scipy`, `matplotlib`, `streamlit`, `skyfield` | `simulation for signal and physics/*.py` |
| Protocol harness | *(stdlib `ctypes` only)* | `python_satellite_sim_v2.py`, `all_tests/*.py` |

### 2. Run all Python tests

```bash
# One-shot (PowerShell):
.\all_tests\run_python_tests.ps1

# Or individually:
PYTHONIOENCODING=utf-8 python all_tests/test_dual_phy_437.py
PYTHONIOENCODING=utf-8 python all_tests/test_integration_matrix_it02_it03_it05_it06.py
PYTHONIOENCODING=utf-8 python all_tests/test_kalman_gaussian_3sat.py
PYTHONIOENCODING=utf-8 python all_tests/test_noise_weighting_and_algorithms.py
```

### 3. Run C++ tests

```bash
"c++ implemnetation/build/Release/test_runner.exe"
# Expected: 273/273 PASS
```

### 4. JS/Cesium protocol visualizer (live demo)

```bash
cd simulation
npm install
npm run dev
# Opens: http://localhost:5173
# Shows: 8-sat constellation with real OPS-SAT anomaly detection,
#        correction/relay/borrow packet log, satellite state panel
```

### 5. Physical layer simulation (Streamlit)

```bash
streamlit run "simulation for signal and physics/sisp_unified_sim.py"
# Opens: http://localhost:8501
# Tabs: Geometry (LoS+Doppler), PHY (BER/PER, ALOHA collision proxy),
#        Timing & Energy, Dual-PHY protocol, KPIs, Robustness Analysis
```

### 6. Sustainability & impact dashboard (Streamlit)

```bash
streamlit run "simulation for signal and physics/sisp_value_dashboard.py"
# Default: http://localhost:8501 (use --server.port to change)
# Tabs: Overview, Orbital Sustainability, Sensor Quality, Energy & Climate,
#        50-Year Projection, Assumptions & Formulas, Debris-Risk KPIs
# All numbers derive from sidebar sliders — no hardcoded values.
```

### 7. SVD anomaly detection

```bash
# List available channels
python sisp_svd_anomaly.py --list-channels

# Run on all channels
python sisp_svd_anomaly.py

# Run on one channel with plots
python sisp_svd_anomaly.py --channel CADC0894 --plot

# Save results to CSV
python sisp_svd_anomaly.py --out results/svd_results.csv
```

### 8. Validate BPSK BER (Monte Carlo)

```bash
python "simulation for signal and physics/validate_bpsk_awgn.py" --bits 500000
```

---

## Documentation Index

| Document | What it covers |
|---|---|
| [docs/SISP_RESEARCH_PAPER.md](docs/SISP_RESEARCH_PAPER.md) | Full paper: state machine, SVD, Kalman, physics, results, end-of-life, novelty |
| [docs/SISP_KPI_SNAPSHOT.md](docs/SISP_KPI_SNAPSHOT.md) | All KPIs with explicit formulas, sources, and recalculated numbers |
| [docs/SISP_REAL_TEST_RESULTS.md](docs/SISP_REAL_TEST_RESULTS.md) | OPS-SAT ingestion, detector validation, correction/relay/borrow tests |
| [docs/README_00_OVERVIEW.md](docs/README_00_OVERVIEW.md) | Project overview and key numbers |
| [docs/README_01_STATE_MACHINE.md](docs/README_01_STATE_MACHINE.md) | All 21 states, 24 events, transition flows, Python API |
| [docs/README_02_SVD_CHI_SQUARE.md](docs/README_02_SVD_CHI_SQUARE.md) | SVD rank selection, chi-square NIS gate, tuning |
| [docs/README_03_CORRECTION_ALGORITHMS.md](docs/README_03_CORRECTION_ALGORITHMS.md) | Kalman, weighted median, hybrid, NIS-gated — benchmark tables |
| [docs/README_04_SIGNAL_PHYSICS.md](docs/README_04_SIGNAL_PHYSICS.md) | GMSK BER, K=7 union bound, full 9-step link budget, Doppler, dual-PHY |
| [docs/README_05_ENERGY_STUDY.md](docs/README_05_ENERGY_STUDY.md) | Per-frame energy, correction snapshot, bulk relay |
| [docs/README_06_TEST_RESULTS.md](docs/README_06_TEST_RESULTS.md) | All extracted log metrics and result tables |

---

## SISP vs Baseline

Without SISP, a satellite with a failed sensor degrades or ends its mission early, waits up to 90 minutes for a ground-station pass to downlink data, and must be replaced at full launch cost when hardware fails.
With SISP, the same satellite borrows a working sensor from a neighbour in under 5 seconds, relays data through ISL during 45% of each orbit instead of 10%, and extends its operational life by ~45% — cutting replacement launches, launch CO₂, and orbital debris proportionally.
Correction quality improves by **94.3% RMSE** over 30-day cycles (Kalman, IT-05) and holds at **85.6%** under 10% packet loss (IT-06), validated by 273/273 automated C++ tests and 10 Python integration scenarios.
The protocol overhead is negligible: a full correction round with 8 neighbours takes **~850 ms**, costs **3.66 J** on the requesting satellite, and a no-relay daily operating tempo (24 corrections + 288 heartbeats) uses **317 mWh/day — 0.26% of a 5 W onboard energy budget**.
Full details, formulas, and assumption transparency: [`docs/SISP_KPI_SNAPSHOT.md`](docs/SISP_KPI_SNAPSHOT.md) · [`docs/SISP_RESEARCH_PAPER.md`](docs/SISP_RESEARCH_PAPER.md).

---

## Protocol Event Codes

> **Important:** Always use these exact integer values in Python harnesses.

| Code | Name | Trigger |
|---|---|---|
| 12 | `FAULT_DETECTED` | Sensor fault detected internally |
| 13 | `TIMER_EXPIRED` | RTOS tick, deadline passed |
| 14 | `ENERGY_LOW` | Power monitor threshold |
| 21 | `CRITICAL_FAILURE` | Catastrophic self-failure |
| 22 | `RESET` | Ground command |

---

## Tuning Points

| What to change | File | Symbol |
|---|---|---|
| Correction algorithm | `c++ implemnetation/src/sisp_state_machine.cpp` | `ctx.correction_filter` via `sim_use_kalman_filter()` |
| Kalman noise parameters | `c++ implemnetation/src/sim_hooks.cpp` | `sim_use_kalman_filter(ctx, q, r)` |
| SVD rank / threshold | `sisp_svd_anomaly.py` | `CONFIG` block at top of file |
| PHY profile selection | `c++ implemnetation/src/sisp_state_machine.cpp` | `select_tx_phy()` |
| DEGR score formula | `c++ implemnetation/src/sisp_protocol.cpp` | `compute_degr()` |
| Frame size | `c++ implemnetation/include/sisp_protocol.hpp` | `FRAME_SIZE` (currently 64 bytes) |
| Timer deadlines | `c++ implemnetation/src/sisp_state_machine.cpp` | `ctx.timer_deadline_ms = g_current_time_ms + N` |

---

## References

- Murota & Hirade (1981): GMSK BER, α_BT=0.68 for BT=0.3
- Heller & Jacobs (1971): K=7 R=1/2 Viterbi union bound, d_free=10, coeff=36
- Dallas et al. (2020): CO₂ per launch, npj Microgravity
- OPSSAT-AD dataset: Zenodo 12588359
- UCS Satellite Database: ucsusa.org/satellite-database
