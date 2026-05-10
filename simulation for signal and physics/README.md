# simulation for signal and physics

Physical-layer models, link budget analysis, orbital geometry, and sustainability
impact dashboards for the SISP protocol. Two physics modules:

- **Module M1 — Geometry:** Earth-blockage line-of-sight, slant range, Doppler (Skyfield/SGP4)
- **Module M3 — Physical layer:** AWGN BER/PER, GMSK BT=0.3, K=7 Conv union bound, RS(255,223), dual-PHY 437 MHz

---

## Files

| File | What it does | Run |
|---|---|---|
| `sisp_unified_sim.py` | Main Streamlit app — 5 tabs: geometry, BER/PER, timing+energy, dual-PHY protocol probe, KPIs | `streamlit run` |
| `sisp_value_dashboard.py` | Sustainability & impact dashboard — orbital, energy, climate, 50-yr projection, all assumptions transparent | `streamlit run` |
| `sisp_signal_sim.py` | Focused PHY app — BER curves, link budget vs distance, PER curves | `streamlit run` |
| `sisp_common_band_sim.py` | 437 MHz common-band study — 12.5/25 kHz profiles, multiple modulations and FEC | `streamlit run` |
| `validate_bpsk_awgn.py` | Monte Carlo BER validation — simulated vs theoretical BPSK/AWGN (validates M3 formulas) | `python` |
| `orbital geometry.py` | Console script — Skyfield LoS, slant range, Doppler example (validates M1 formulas) | `python` |

**Study notes** (internal reference, not scripts):
- `study geometry.md` — M1 derivations: ECI frames, LoS criterion, Doppler formula
- `study signal process.md` — M3 derivations: BPSK passband model, link budget, BER/PER
- `tradeoff.md` — RF architecture trade study: Ka-band vs UHF, dual-band rationale
- `SISP_SCIENTIFIC_REPORT_INTERSAT_UHF.md` — Full scientific report (geometry → link budget → BER → energy → KPIs)
- `UHF_437_two_mode_phy_hardware_math_study.md` — Hardware-grounded 437 MHz two-profile PHY study
- `common_band_437mhz_evaluation.md` — UHF-only scenario for degraded/emergency operation

---

## Install dependencies

From the **repo root** (recommended — installs everything):

```bash
pip install -r requirements.txt
```

Or install only this folder's deps:

```bash
pip install -r "simulation for signal and physics/requirements.txt"
# numpy>=1.26  scipy>=1.13  matplotlib>=3.9  streamlit>=1.35  skyfield>=1.48
```

The C++ protocol probe (Protocol Message Energy tab in `sisp_unified_sim.py`) also requires
`c++ implemnetation/build/bin/Release/sisp.dll` — prebuilt and committed to the repo.

---

## Run

### Unified simulation (start here)

```bash
# From repo root:
streamlit run "simulation for signal and physics/sisp_unified_sim.py"
```

Opens **http://localhost:8501** with five tabs:

| Tab | Contents |
|---|---|
| Geometry (LoS + Doppler) | TLE input → Earth-blockage LoS windows, slant range, Doppler, ground-station contact |
| PHY (BER/PER) | BER curves for GMSK/BPSK/FSK + FEC levels; PER vs distance at selected link budget |
| Timing & Energy | Correction snapshot timing (5-second window check); bulk dump time/energy with ARQ |
| Protocol Message Energy | C++ DLL probe → frame counts per service; dual-PHY breakdown (frame byte 8 decoded) |
| KPI Dashboard | Energy per MiB, % of daily budget, ISL vs ground-link comparison |

**Sidebar controls** (shared across all tabs):
- Carrier frequency (default 437 MHz)
- Channel bandwidth: 12.5 kHz (CTRL) or 25 kHz (BULK)
- Tx/Rx power, antenna gains, pointing and misc losses
- Receiver noise figure → auto-computes T_sys
- Doppler guard margin (default 1.5 dB for 437 MHz ISL)
- Modulation: GMSK BT=0.3, BPSK, QPSK, 2-FSK coherent/noncoherent
- FEC: None / Conv K=7 R=1/2 / Conv+RS(255,223)

### Sustainability & impact dashboard

```bash
streamlit run "simulation for signal and physics/sisp_value_dashboard.py"
```

Opens **http://localhost:8503**. All values derive from sidebar sliders — no hardcoded numbers.
Every metric has an expandable **Show calculation** trace showing the exact formula and substituted values.

### PHY-only app

```bash
streamlit run "simulation for signal and physics/sisp_signal_sim.py"
```

### 437 MHz common-band study

```bash
streamlit run "simulation for signal and physics/sisp_common_band_sim.py"
```

### BER Monte Carlo validation

```bash
# From repo root:
python "simulation for signal and physics/validate_bpsk_awgn.py" --bits 500000
```

Expected output: simulated BER matches `0.5·erfc(√(Eb/N0))` within <5% at all noise levels.

### Geometry console example

```bash
python "simulation for signal and physics/orbital geometry.py"
```

---

## Key physics models implemented

| Model | Formula | File | Reference |
|---|---|---|---|
| GMSK BT=0.3 BER | `P_b = 0.5·erfc(√(0.68·Eb/N0))` | `sisp_unified_sim.py` | Murota & Hirade 1981 |
| Conv K=7 union bound | `P_b ≤ 36·Q(√(10·Eb/N0))` | `sisp_unified_sim.py` | Heller & Jacobs 1971 |
| RS(255,223) proxy | binomial tail `P(Nerr > 16)` | `sisp_unified_sim.py` | — |
| FSPL | `20log(d) + 20log(f) + 20log(4π/c)` | `sisp_unified_sim.py` | Friis 1946 |
| Noise figure → T_sys | `T_rx = 290·(F−1)` | `sisp_unified_sim.py` | IEEE Std 60268 |
| Earth-blockage LoS | `γ < arccos(R/rA) + arccos(R/rB)` | `sisp_unified_sim.py` | Vallado 2008 |
| Doppler shift | `Δf = f·ḋ/c` | `sisp_unified_sim.py` | — |
| Frame PER | `PER = 1 − exp(512·ln(1−p))` | `sisp_unified_sim.py` | — |

---

## Deeper reading

- Full scientific report: [`SISP_SCIENTIFIC_REPORT_INTERSAT_UHF.md`](SISP_SCIENTIFIC_REPORT_INTERSAT_UHF.md)
- Research paper: [`../docs/SISP_RESEARCH_PAPER.md`](../docs/SISP_RESEARCH_PAPER.md)
- Signal physics README: [`../docs/README_04_SIGNAL_PHYSICS.md`](../docs/README_04_SIGNAL_PHYSICS.md)
- Energy study README: [`../docs/README_05_ENERGY_STUDY.md`](../docs/README_05_ENERGY_STUDY.md)
- KPI snapshot (tables for slides): [`../docs/SISP_KPI_SNAPSHOT.md`](../docs/SISP_KPI_SNAPSHOT.md)
