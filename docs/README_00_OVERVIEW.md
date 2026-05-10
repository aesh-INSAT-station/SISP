# SISP — Project Overview

**SISP (Satellite Inter-Service Protocol)** is a complete autonomous cooperative protocol stack for CubeSat constellations. It allows satellites to correct degraded sensors, relay data across visibility gaps, and borrow healthy sensors from neighbours — all without ground intervention.

---

## Repository Layout

```
SISP/
├── c++ implemnetation/          # Protocol C++ library (DLL + test runner)
│   ├── include/                 # Public headers (protocol, state machine, correction, hooks)
│   ├── src/                     # Implementation
│   ├── tests/                   # 273 unit/integration tests
│   └── build/                   # MSVC build output (sisp.dll, test_runner.exe)
│
├── simulation for signal and physics/  # Physical layer and protocol simulation
│   ├── sisp_unified_sim.py      # Main Streamlit app (5 tabs)
│   ├── validate_bpsk_awgn.py    # Monte Carlo BER validation
│   ├── SISP_SCIENTIFIC_REPORT_INTERSAT_UHF.md
│   └── requirements.txt
│
├── all_tests/                   # Python integration test suite
│   ├── test_dual_phy_437.py     # Dual-PHY verification (NEW)
│   ├── test_kalman_gaussian_3sat.py
│   ├── test_noise_weighting_and_algorithms.py
│   ├── test_integration_matrix_it02_it03_it05_it06.py
│   └── ...
│
├── logs/                        # Test run logs (auto-generated)
├── docs/                        # Research paper + detailed READMEs (this folder)
├── data/raw/segments.csv        # OPSSAT-AD telemetry dataset
├── python_satellite_sim_v2.py   # Level 3 multi-satellite Python harness
└── README.md                    # Root quick-start guide
```

---

## Three Core Services

| Service | Trigger | Flow | Protocol messages |
|---|---|---|---|
| **Correction** | `FAULT_DETECTED` | Broadcast REQ → collect RSPs → run filter | `CORRECTION_REQ`, `CORRECTION_RSP` |
| **Relay** | `ENERGY_LOW` or `GS_LOST` | Broadcast REQ → handshake → fragment data | `RELAY_REQ`, `RELAY_ACCEPT`, `DOWNLINK_DATA`, `DOWNLINK_ACK` |
| **Borrow** | `GS_VISIBLE` | Broadcast REQ → decision → sensor stream | `BORROW_REQ`, `BORROW_DECISION`, `DOWNLINK_DATA` |

---

## Quick Start

### Install dependencies
```bash
pip install -r "simulation for signal and physics/requirements.txt"
```

### Run Streamlit simulation
```bash
streamlit run "simulation for signal and physics/sisp_unified_sim.py"
```
Open **http://localhost:8501** in your browser.

### Run all Python tests
```bash
PYTHONIOENCODING=utf-8 python all_tests/test_dual_phy_437.py
python all_tests/test_integration_matrix_it02_it03_it05_it06.py
python all_tests/test_kalman_gaussian_3sat.py
python all_tests/test_noise_weighting_and_algorithms.py
```

### Run C++ tests
```bash
"c++ implemnetation/build/Release/test_runner.exe"
```
Expected: **273/273 PASS**.

---

## Key Numbers at a Glance

| Metric | Value |
|---|---|
| C++ test coverage | 273/273 PASS |
| 30-day RMSE improvement (Kalman) | **94.3%** |
| Packet-loss resilience (10% PLR) | **85.6%** improvement |
| GMSK BT=0.3 ISI penalty vs BPSK | 1.67 dB |
| Max Doppler @ 437 MHz, LEO | ~10.9 kHz |
| Correction snapshot time (8 neighbours) | ~850 ms (<5 s timer) |
| 1 MiB relay energy | ~2.53 Wh (0.84% daily budget) |

---

## Docs in This Folder

| File | Contents |
|---|---|
| `SISP_RESEARCH_PAPER.md` | Full academic-style paper |
| `README_00_OVERVIEW.md` | This file |
| `README_01_STATE_MACHINE.md` | Protocol state machine architecture |
| `README_02_SVD_CHI_SQUARE.md` | Anomaly detection pipeline |
| `README_03_CORRECTION_ALGORITHMS.md` | Kalman, median, hybrid filters |
| `README_04_SIGNAL_PHYSICS.md` | Link budget, BER, PER, dual-PHY |
| `README_05_ENERGY_STUDY.md` | Per-service energy analysis |
| `README_06_TEST_RESULTS.md` | Extracted test logs and result tables |
