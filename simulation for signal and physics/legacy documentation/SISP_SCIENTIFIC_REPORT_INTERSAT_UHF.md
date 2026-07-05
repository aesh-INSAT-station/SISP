# SISP Inter‑Satellite Communications Study (UHF 437 MHz)

Scientific report: **geometry → RF link budget → BER/PER → protocol time/energy → system KPIs**.

This document is intentionally rigorous and explicit about assumptions. Where the literature provides no inter‑sat “standard target”, we frame requirements as **engineering targets** derived from protocol packet error constraints.

## 0) Scope and objectives

**Domain:** inter‑satellite communication (ISL), not ground links.

**Objective:** quantify the feasibility and energy/time cost of running the SISP protocol over narrowband UHF (437 MHz) under realistic constraints (channelization, Doppler, Earth blockage).

Deliverables:
- A unified, reproducible simulator that merges geometry + PHY + protocol energy attribution.
- Protocol‑actionable numbers: per‑message energy, bulk dump time/energy, and the “5‑second correction window” feasibility.
- Business KPIs: energy per MiB, percent of daily energy budget, accessible contact time, and comparison to a downlink‑to‑Earth case.

## 1) Repository mapping (source of truth)

The model is implemented directly in the repo.

### 1.1 Unified simulator entry point

- `simulation for signal and physics/sisp_unified_sim.py`
  - Tabs:
    - **Geometry:** Earth blockage + Doppler using Skyfield.
    - **PHY:** AWGN link budget → $E_b/N_0$ → BER/PER.
    - **Timing & Energy:** correction snapshot and bulk dump.
    - **Protocol Message Energy:** counts frames by service from the *actual* C++ state machine emissions (via `sisp.dll`), then converts frames → energy.
    - **KPI Dashboard:** energy per MiB, % budget, and ground‑link comparison.

### 1.2 Legacy scripts (retained)

- `simulation for signal and physics/orbital geometry.py` — original geometry console output.
- `simulation for signal and physics/sisp_common_band_sim.py` — original UHF common‑band Streamlit.
- `simulation for signal and physics/sisp_signal_sim.py` — original PHY Streamlit.
- `simulation for signal and physics/validate_bpsk_awgn.py` — Monte Carlo sanity check for BPSK/AWGN.

## 2) Geometry (spherical Earth blockage + Doppler)

### 2.1 State vectors and line‑of‑sight criterion

Let satellites $A$ and $B$ have ECI position vectors $\mathbf{r}_A(t)$ and $\mathbf{r}_B(t)$.
Define $r_A=\|\mathbf{r}_A\|$ and $r_B=\|\mathbf{r}_B\|$.
The central angle between them is:

$$
\gamma(t) = \arccos\left( \frac{\mathbf{r}_A\cdot\mathbf{r}_B}{r_A\,r_B} \right)
$$

Let Earth exclusion radius be $R_{excl}=R_E + h_{clear}$.
Line‑of‑sight exists when:

$$
\gamma(t) < \arccos\left(\frac{R_{excl}}{r_A}\right) + \arccos\left(\frac{R_{excl}}{r_B}\right)
$$

This is implemented in the unified simulator Geometry tab.

### 2.2 Slant range and Doppler

Slant range:

$$d(t)=\|\mathbf{r}_B(t)-\mathbf{r}_A(t)\|$$

Range rate:

$$\dot{d}(t)=\frac{(\mathbf{r}_B-\mathbf{r}_A)\cdot(\mathbf{v}_B-\mathbf{v}_A)}{\|\mathbf{r}_B-\mathbf{r}_A\|}$$

First‑order Doppler shift:

$$\Delta f(t) \approx f_c\,\frac{\dot{d}(t)}{c}$$

For 437 MHz, Doppler can be kHz‑class; this strongly favors constant‑envelope, robust demodulators (FSK/GMSK) unless coherent carrier recovery is high‑quality.

## 3) Link budget and $E_b/N_0$

### 3.1 FSPL and noise power

Free‑space path loss:

$$L_{fs}(dB)=20\log_{10}(d) + 20\log_{10}(f) + 20\log_{10}\left(\frac{4\pi}{c}\right)$$

Noise power in bandwidth $B$:

$$N = kT_{sys}B$$

In dBm:

$$N_{dBm} = 10\log_{10}(kT_{sys}B) + 30$$

### 3.2 SNR and $E_b/N_0$

$$\mathrm{SNR}_{dB}=P_{tx,dBm}+G_t+G_r - L_{fs}-L_{point}-L_{misc}-N_{dBm}$$

$$\frac{E_b}{N_0} (dB)=\mathrm{SNR}_{dB}+10\log_{10}\left(\frac{B}{R_b}\right)$$

The simulator uses this mapping for UHF and for optional ground‑link comparisons.

## 4) BER and PER models (engineering models)

### 4.1 Uncoded AWGN

For coherent BPSK (and Gray QPSK):

$$P_b = Q(\sqrt{2E_b/N_0}) = \frac{1}{2}\,\mathrm{erfc}(\sqrt{E_b/N_0})$$

Orthogonal BFSK:
- coherent: $P_b=Q(\sqrt{E_b/N_0})$
- non‑coherent: $P_b=\frac{1}{2}\exp(-E_b/(2N_0))$

### 4.2 Convolutional code proxy

The repo uses a **constant coding gain** approximation for convolutional coding by shifting the effective $E_b/N_0$ by ~7 dB.
This is a proxy, not a standards modem curve.

### 4.3 RS(255,223) decode failure proxy

Post‑conv BER is converted to byte error probability $p_{byte}=1-(1-P_b)^8$.
RS decode failure probability:

$$p_{fail}=P(N_{byte\_errors} > 16)$$

computed via a binomial tail.
If RS fails, the output is treated as random bits, giving a post‑FEC BER proxy of $0.5\,p_{fail}$.

### 4.4 PER mapping

For a packet with $n$ protected bits and i.i.d. residual BER $p$:

$$\mathrm{PER} = 1-(1-p)^n$$

SISP uses a fixed 64‑byte frame; thus PER is computed for $n=512$ bits.

## 5) Protocol timing and energy models

### 5.1 Fixed framing and coding expansion

Each transmission uses one 64‑byte protocol frame.
Coding expansion factor is:

- NONE: $1$
- CONV: $1/R_{conv}=2$
- CONV+RS: $1/(R_{conv}R_{rs}) \approx 2.287$

On‑air bits per frame:

$$n_{air}=512\times \mathrm{expansion}$$

Frame time:

$$t_{frame}=\frac{n_{air}}{R_b}$$

### 5.2 Correction snapshot (5‑second timer)

For one requester and $N$ neighbours responding, with repeats factor $r$:

$$t_{snap} \approx r(1+N)t_{frame} + 2\,t_{prop}$$

Energy is computed using a DC power model:

$$E_{TX}=P_{TX,DC}\,t,\quad E_{RX}=P_{RX,DC}\,t$$

The unified simulator reports requester TX/RX and neighbours TX/RX contributions.

### 5.3 Bulk dump

Bulk dump frames required:

$$N_{frames}=\left\lceil \frac{\mathrm{bytes}_{eff}}{\mathrm{payload\_bytes\_per\_frame}} \right\rceil$$

If ARQ is assumed with per‑frame PER, expected transmissions per delivered frame:

$$E[T]=\frac{1}{1-\mathrm{PER}}$$

Total time:

$$t_{bulk}=N_{frames}E[T]t_{frame}$$

Energy is computed for sender TX and receiver RX separately.

## 6) Message‑level energy attribution (service breakdown)

A central requirement for business/ops is: “which messages cost how much energy?”.

The unified simulator provides two approaches:

1) **Measured via C++**: it loads `c++ implemnetation/build/bin/Release/sisp.dll`, registers a TX callback, runs a short scenario, and counts frames emitted per service.
2) **Analytic daily mix**: user specifies daily counts (corrections/day, heartbeats/hour, failures/day, relay ops) and the tool converts those frame counts into energy and percentages.

**Important modeling note:** the C++ probe counts *attempted* transmissions at the protocol layer, not PHY‑level packet drops. A first‑order PHY loss adjustment is applied by scaling counts by $1/(1-\mathrm{PER})$.

## 7) KPI definitions (business‑oriented)

The simulator reports:

- **Energy per delivered MiB** (Wh/MiB) for ISL, including expected retries.
- **Percent of daily generated energy** spent on comms.
- **Percent of battery capacity** spent on comms.
- **Energy margin (Wh/day)** after non‑comms loads.
- **Ground‑link comparison**: spacecraft TX energy per MiB under a downlink link budget.

These KPIs are not “standards” — they are mission economics levers.

## 8) How to run

Install dependencies:

```bash
pip install -r "simulation for signal and physics/requirements.txt"
```

Run unified simulator:

```bash
streamlit run "simulation for signal and physics/sisp_unified_sim.py"
```

For message energy attribution via C++:
- Ensure the C++ build produced `sisp.dll` in `c++ implemnetation/build/bin/Release/`.

## 9) Limitations and what would make it more “standards‑accurate”

- AWGN is not the full channel: interference, adjacent channel leakage, frequency error, and non‑Gaussian effects are not modeled.
- Convolutional coding gain is modeled as a constant offset, not a true curve.
- RS post‑decode model uses a binomial byte‑error proxy.
- The PHY loss adjustment in message attribution uses a simple expected multiplier, not a full ARQ/ACK state model.

Despite these limitations, the stack is **coherent**: geometry → range → link budget → PER → time/energy → protocol‑level consequences.
