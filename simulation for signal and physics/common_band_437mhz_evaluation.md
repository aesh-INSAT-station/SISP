# Common-Band 437 MHz Evaluation (Documentation Notes)

This note evaluates the idea of running SISP on a **single “common band” at ~437 MHz** (UHF) for *failure / degraded* operation, while keeping the **Ka-band baseline comparison** for documentation.

Important: this is a **physics + timing study** only. The C++ protocol implementation remains unchanged.

---

## 1) What “common band” means here

- Use **one RF band (UHF ~437 MHz)** for *everything* when Ka-band pointing/alignment is unavailable or too costly.
- In failure mode, trade bandwidth for robustness using:
  - lower spectral efficiency modulation,
  - stronger FEC (or lower code rate),
  - repetition (“double-send”),
  - and/or **data reduction (compression / summarization)**.

This maps to the real-world reality that in a fault scenario you often care more about **getting *some* validated data out** than streaming a full high-rate dump.

---

## 2) “Common” UHF band + bandwidth expectations (non-authoritative)

- Many CubeSat-class systems use UHF around **435–438 MHz** (often “437 MHz”) because it’s widely supported and has heritage.
- Bandwidth is frequently **narrow** (e.g., 10–25 kHz-class channels) compared to S/Ka systems.

Regulatory allocations and allowable bandwidth depend on the mission and jurisdiction. Treat bandwidth as a **design parameter** in the sim.

### 2.1 Other common smallsat RF bands (context)

For documentation completeness (not specific to SISP), other commonly seen smallsat comms bands include:

- **VHF (~145 MHz class)**: legacy/educational links, narrowband, low data rates.
- **UHF (~435–438 MHz class)**: common CubeSat heritage, narrow-to-moderate data rates.
- **S-band (~2.2–2.3 GHz class)**: higher data rates than VHF/UHF with more demanding RF.
- **X/Ka-band**: high-throughput downlinks and/or ISLs, typically requires high-gain antennas and pointing.

Exact usable sub-bands depend on licensing/allocations.

---

## 3) Modulation / coding options worth comparing

For a 437 MHz common-band link, practical candidates include:

- **2-FSK / GFSK**: constant-envelope, tolerant of PA nonlinearity, common in smallsat radios.
- **BPSK**: better power efficiency than FSK in ideal coherent AWGN, but requires coherent carrier recovery.
- **QPSK**: doubles bit rate at the same symbol rate, but requires higher SNR for the same BER at a fixed bandwidth.

For FEC, the current study keeps the same “engineering model” used in the existing simulator:

- None
- Convolutional (R=1/2) using a constant ~7 dB gain approximation
- Conv + RS(255,223) using an RS decode-failure probability model

---

## 4) Failure-mode data reduction (compression / “send less”)

For the large `RELAY_DATA`-style dump case, a single-band UHF design only becomes viable if you *reduce bytes*.

Typical knobs:

- **Compression**: log/text often compresses well (2×–10× is plausible; depends on content).
- **Delta encoding**: send only changes since last good state.
- **Feature summaries**: send statistical aggregates (means/variances/outliers) instead of raw time series.
- **Tiered payload**: transmit a small “must-have” digest first, then optional chunks if the window allows.

This is consistent with the “failure state” concept: deliver a verified minimum set within limited time/energy.

---

## 5) Timing link to the C++ correction path (why bitrate matters)

The C++ state machine starts a strict **5-second** collection timer after `CORRECTION_REQ` is sent.

- Fixed on-air unit in the protocol is a **64-byte frame**.
- Propagation delay is usually negligible for LEO ISL:
  - 1000 km one-way is ~3.3 ms.

So the 5-second timer is mostly about **on-air time**, not distance.

If you assume sequential access (worst-case TDMA-like), the rough time budget is:

$$t_{total} \approx (1 + N_{rsp}) \cdot t_{frame} \cdot N_{repeats} + 2\,\frac{d}{c}$$

where $t_{frame} = \frac{\text{bits-on-air}}{R_b}$.

At low bit rates, repetition or strong coding can push you over 5 seconds.

---

## 6) Where the simulator lives / how to run

The Streamlit tool is in:

- `simulation for signal and physics/sisp_common_band_sim.py`

Run:

```bash
streamlit run "simulation for signal and physics/sisp_common_band_sim.py"
```

What it shows:

- Eb/N0 vs distance and PER vs distance (64B protocol frame)
- Bulk-dump time/energy with optional compression + ARQ assumption
- A direct “**meets 5 seconds?**” check for `CORRECTION_REQ/RSP` collection

---

## 7) Quick numeric example: 10 kHz vs 2×10 kHz (bonded) + compression

This example is meant to match the intuition in the trade study (“UHF can take ~25–30 minutes for big dumps”).

Assumptions (rough but protocol-relevant):

- Fixed 64B protocol frame
- Conv+RS coding expansion $\approx 2.286\times$ (so a 64B frame is ~1171 bits on-air)
- 2-FSK with spectral efficiency $\approx 0.5$ b/s/Hz
- Useful payload per frame: 45 bytes (to leave room for envelopes/headers)
- Failure dump: 1 MiB, compressed by 3× (so ~0.33 MiB transmitted)

Then:

- **10 kHz channel** → $R_b \approx 5$ kbps → bulk time **~30.3 minutes**
- **2×10 kHz bonded channel (20 kHz)** → $R_b \approx 10$ kbps → bulk time **~15.2 minutes**

This is where geometry matters:

- If your LoS window is ~15 minutes (Module M1 style), the bonded+compressed case becomes **borderline-feasible**, while 10 kHz is typically not.

Important fairness note: if you bond channels and also scale data rate up with bandwidth at fixed power, $E_b$ drops by ~3 dB (because $E_b = P/R_b$). The simulator accounts for this via the $E_b/N_0$ calculation.

---

## 8) Updated single-band proposal (skip Ka pointing): 10 kHz control + emergency bulk mode

If we explicitly avoid Ka-band pointing/ADCS for now, the viable “UHF-only” architecture is **not** “use 10 kHz for everything all the time”. It is:

- **Normal mode:** keep a narrow **10 kHz-class control PHY** for the continuous awareness mesh (corrections, status, relay requests).
- **Emergency / relay mode:** temporarily switch to a **bulk PHY** that can be faster and/or more robust, for example:
  - **bond 2×10 kHz** (20 kHz effective bandwidth),
  - pick the best modulation/FEC combination for the target range,
  - and **shrink bytes first** (compression, delta, or **low-rank/SVD representation**) so the dump fits the LoS window.

This matches the real bottleneck: for large dumps, the binding constraint is usually the **LoS window time**, not propagation.

### 8.1 How to study it in the simulator

In the Streamlit tool (`sisp_common_band_sim.py`) → Tab “Timing/Energy”:

- Use **“Bulk bandwidth multiplier (bonding)”** to model 10 kHz vs 20 kHz.
- Use **“Use control PHY for bulk”** to keep bulk equal to control, or disable it to choose a different bulk modulation/FEC.
- Use **“Low-rank (SVD) model”** to convert a matrix dump into an estimated byte size via:

$$\text{coeffs} \approx r(m+n+1),\quad \text{size} \approx \frac{r(m+n+1)\,q}{8}$$

where $m\times n$ is the matrix, $r$ is kept rank, and $q$ is quantization bits per coefficient.

- Use **“Bulk PHY search”** to brute-force scan small candidate sets (modulation/FEC/bonding) and rank which ones fit the window with lowest time/energy.
