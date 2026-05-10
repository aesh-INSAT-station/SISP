# Simulation for signal and physics

This folder contains standalone scripts/notes used to validate the **Module M1 (geometry)** and **Module M3 (physical layer)** math.

## What’s in here

- `sisp_signal_sim.py` — Streamlit app: BER curves, link budget vs distance, PER vs distance.
- `sisp_common_band_sim.py` — Streamlit app: 437 MHz common-band study (multiple modulations/FEC) + 5-second correction-window timing/energy.
- `validate_bpsk_awgn.py` — Monte‑Carlo sanity check: simulated BER vs theoretical BPSK/AWGN.
- `orbital geometry.py` — Skyfield-based LoS + slant range + Doppler example.
- `study geometry.md`, `study signal process.md` — study notes.

## Install dependencies

```bash
pip install -r "simulation for signal and physics/requirements.txt"
```

## Run

### Physical layer app

```bash
streamlit run "simulation for signal and physics/sisp_signal_sim.py"
```

### Common-band (437 MHz) study

```bash
streamlit run "simulation for signal and physics/sisp_common_band_sim.py"
```

### BPSK/AWGN validation

```bash
python "simulation for signal and physics/validate_bpsk_awgn.py" --bits 2000000
```

### Geometry example

```bash
python "simulation for signal and physics/orbital geometry.py"
```
