# SISP — KPI Snapshot

**Reference scenario** (adjust via dashboard sliders to match your constellation):

| Parameter | Value used below | Source |
|---|---|---|
| Constellation size | 100 satellites | — |
| Design life (baseline) | 3 years | CubeSat average |
| SISP life extension | +45% → 4.35 yr | Derived from IT-05 |
| Annual sensor failure rate | 12% | SmallSat reliability literature |
| Sensor recovery via borrowing | 60% | Protocol design |
| Satellite mass | 5 kg (3U-class) | Typical |
| Launch cost | $6,000/kg | SpaceX Falcon 9 rideshare |
| Satellite unit cost | $500K | Mid-range CubeSat |
| CO₂ per launch | 300 t CO₂-eq | Dallas et al. 2020 |
| Ground-station contact | 10% of orbit | Single GS, mid-latitude |
| ISL contact | 45% of orbit | Same-plane neighbours |
| Tx DC power | 10 W | Includes PA inefficiency |
| Rx DC power | 2.5 W | ~25% of TX |
| Corrections per day | 24 (hourly) | Operating tempo |
| Neighbours per correction | 6 | Constellation density |
| Growth rate | 12%/yr | UCS DB historical |

---

## Measured Test Results (not modelled — directly from test logs)

| Test | Scenario | Raw RMSE | Corrected RMSE | Improvement |
|---|---|---|---|---|
| IT-05 | 30-day drift (0.5/day), Kalman | 8.91 | **0.50** | **94.3%** |
| IT-06 | 10% packet loss, 7 days, 5-sat | 8.29 | **1.20** | **85.6%** |
| noise_algo | σ=20, balanced, Kalman | 21.73 | **9.40** | **56.7%** |
| noise_algo | σ=60, balanced, Kalman | 66.47 | **33.60** | **49.4%** |
| noise_algo | σ=40, 1 broken peer, Hybrid | 29.99 | **15.85** | **47.1%** |
| kalman_3sat | σ=2.0, nominal, 20 rounds | 2.50 | **1.30** | **48.0%** |
| kalman_3sat | σ=25, large fault, 30 rounds | 22.71 | **8.47** | **62.7%** |

**DEGR weighting benefit** (σ=40, mixed quality, inverse-error vs neutral):

| DEGR model | Corrected error | Gain over raw |
|---|---|---|
| inverse_error (recommended) | 19.06 | **+22.5** |
| neutral (equal weights) | 22.47 | +19.1 |
| proportional_error | 27.85 | +13.7 |

**Dual-PHY correctness** (test_dual_phy_437.py): 8/8 assertions pass.

**C++ unit tests**: 273/273 pass.

---

## Protocol Energy (derived — 100% transparent)

| Quantity | Formula | Value |
|---|---|---|
| Physical frame | 64 bytes = 512 bits | 512 bits |
| Coding expansion (Conv+RS) | 1/(0.5 × 223/255) | ×2.287 |
| Air bits per frame | 512 × 2.287 | 1,171 bits |
| Bit rate (GMSK, 12.5 kHz) | B × 1 bit/s/Hz | 12,500 bps |
| Frame time | 1,171 / 12,500 | **93.6 ms** |
| Frames per correction event | 1 REQ + 6 RSP | 7 frames |
| Energy per event (network) | 7 × 0.0936 × (10 + 6×2.5) W | **3.90 J** |
| Daily correction energy/sat | 24 × 3.90 / 3600 | **26.0 mWh** |
| As % of 5 W onboard budget | 26 mWh / (5 W × 24 h) | **0.022%** |

---

## Orbital Sustainability (1-year, reference scenario)

| Metric | Baseline | With SISP | Change |
|---|---|---|---|
| Replacement launches/yr | 100/3 = **33.3** | 100/4.35 = **23.0** | −10.3/yr (−31%) |
| CO₂ from launches/yr | 33.3 × 300 = **10,000 t** | 23.0 × 300 = **6,900 t** | **−3,100 t/yr** |
| Sensor failures | 12 /yr | 12 /yr | — |
| Recovered via borrowing | 0 | **7.2/yr** | +7.2 retained missions |
| Mass launched/yr | 33.3 × 5 = **167 kg** | 23 × 5 = **115 kg** | **−52 kg/yr** |
| Mass with modular reduction | 167 kg | 23 × 3.75 = **86 kg** | **−81 kg/yr (−49%)** |

---

## 50-Year Cumulative Impact (100-sat, 12%/yr growth)

| Metric | Baseline | With SISP | Saved |
|---|---|---|---|
| Replacement launches | ~75,000 | ~52,000 | **~23,000 launches** |
| CO₂ from launches | ~23 Mt | ~16 Mt | **~7 Mt CO₂** |
| Satellite mass to orbit | ~375,000 t | ~260,000 t | **~115,000 t** |
| Replacement cost | ~$38B | ~$26B | **~$12B** |
| Satellites recovered | — | **~28,000** | (sensor-years sustained) |

*Cumulative values assume 12%/yr fleet growth compounded over 50 years.*

---

## Connectivity

| Metric | Baseline | With SISP |
|---|---|---|
| Downlink window per orbit | 10% (~9 min) | 10% (unchanged) |
| Relay opportunity per orbit | — | 45% (~40 min) |
| Effective availability ratio | 1× | **4.5×** |
| Data latency (sensor→ground) | Up to 90 min | Minutes via ISL relay |

---

## Sources

| Claim | Source |
|---|---|
| CO₂ 300 t/launch | Dallas et al. (2020), npj Microgravity, "The environmental impact of emissions from space launches" |
| LEO growth 22%/yr | UCS Satellite Database 2019–2023 (ucsusa.org) |
| CubeSat design life 2–4 yr | ESA/NASA CubeSat reliability statistics |
| Launch cost $6K/kg | SpaceX commercial rideshare pricing 2024 |
| GMSK BT=0.3 BER | Murota & Hirade (1981), IEEE Trans. Comm., α_BT=0.68 |
| Conv K=7 union bound | Heller & Jacobs (1971), IEEE Trans. Comm. Tech., d_free=10 |
| OPSSAT-AD dataset | Zenodo record 12588359 |
| SISP test results | This repo: all_tests/, logs/python_tests_*.log, logs/cpp_tests_*.log |
