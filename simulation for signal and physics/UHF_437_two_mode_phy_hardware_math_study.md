# UHF 437 MHz two‑mode PHY study (10 kHz control + 20 kHz emergency bulk)

This document is a **hardware‑grounded** and **math‑complete** redo of the 437 MHz “common band” study.

**Goal (your spec):**
- **Always keep a narrow 10 kHz control channel** alive for corrections + basic protocol traffic.
- In emergency / bulk relay, **temporarily switch** to a **larger band (20 kHz allowed)** and optionally a different modulation/FEC to reduce time/energy.
- Keep **Convolutional + Reed–Solomon** as the FEC family.
- Include **thermal noise**, **path loss**, **Doppler**, and explicit **BER/PER vs $E_b/N_0$**.
- Assume **no pointing loss** (spherical / omni concept).

This is an engineering study aligned to the equations and assumptions implemented in:
- `simulation for signal and physics/sisp_common_band_sim.py`

---

## 0) Executive conclusion (hardware‑realistic “final choice”)

### A. What COTS UHF flight radios commonly support
Across representative CubeSat‑class UHF radios, **FSK/GFSK/GMSK/AFSK** are the common, easy‑to‑operate modulations. They tolerate:
- oscillator phase noise,
- Doppler/frequency error,
- PA nonlinearity (constant envelope),
- low‑complexity receivers.

**BPSK/QPSK are not “bad” mathematically**, but they are **less commonly offered as fixed modem modes** in COTS UHF transceivers. Implementing them typically implies an **SDR/custom modem** (more compute + verification + integration risk).

### B. Recommended two‑profile approach (fits your “10 kHz always + 20 kHz emergency”)
- **Control PHY (always on):** 10 kHz target → implement as a **12.5 kHz channel** on real radios, **2‑FSK‑family (GFSK/GMSK)**, **Conv+RS(255,223)**.
  - Why: maximizes compatibility with real radios; robust to Doppler/frequency error; keeps PER low on 64‑byte protocol frames.
- **Emergency/Bulk PHY (only when needed):** 20 kHz target → implement as a **25 kHz channel** (or equivalent bonded mode) on real radios, **same 2‑FSK‑family but higher bitrate**, keep **Conv+RS**.
  - Why: halves transfer time (for same framing) with minimal hardware disruption.

**If you want BPSK/QPSK anyway:** make that an SDR‑only option (GomSpace SDR‑class or similar platform) and treat it as a separate integration path.

### C. Why 12.5 kHz / 25 kHz is the practical “final bandwidth” choice
Even if the protocol spec says “10 kHz control + 20 kHz emergency”, a large fraction of UHF flight radios and ground infrastructure are built around **12.5 kHz and 25 kHz channel spacing / IF filters**.

So for implementation and procurement:
- Treat **12.5 kHz** as “the closest real hardware channel” to your 10 kHz control requirement.
- Treat **25 kHz** as “the closest real hardware channel” to your 20 kHz emergency/bulk requirement.

The math in this document and the Streamlit simulator already takes bandwidth $B$ as an explicit parameter, so swapping 10k→12.5k and 20k→25k is a transparent and consistent update.

---

## 1) Satellite industry hardware snapshot (web survey)

The goal of this section is not “who is best”, but “what is *actually implemented* in flight UHF radios”.

### 1.1 AAC Clyde Space — Pulsar‑UTRX (UHF/UHF)
Source: https://www.aac-clyde.space/what-we-do/space-products-components/communications/pulsar-utrx

Key points from the product page:
- **Modulation/data rates:** “implements **9600 bps GMSK** and **1200 bps AFSK**”
- **FEC:** “transparent downlink mode … optional **½‑rate CCSDS convolutional encoder**”
- **Channel spacing:** **25 kHz (TX)**, **12.5 kHz (RX)**
- **RF power:** adjustable **27–33 dBm**

This is highly consistent with the idea that a practical UHF baseline is **GMSK/FSK‑family**, with optional convolutional coding.

### 1.2 EnduroSat — UHF Transceiver
Source: https://www.endurosat.com/products/uhf-transceiver/

Key points visible on the technical specs:
- **Default modulation:** **2GFSK**
- **Additional modulation:** **GMSK**
- **Data rate:** configurable **1.2–19.6 kbps**
- **Frequency range option:** includes **435–438 MHz**
- **RF power:** **27 dBm or 33 dBm**

Again: FSK‑family dominates.

### 1.3 GomSpace — NanoCom SDR MK3 (SDR platform)
Source: https://gomspace.com/product/software-defined-radio/

Key point:
- An SDR platform is explicitly marketed for “**custom RF applications**” and “custom broadband and multiband communications”.

Interpretation:
- If the mission truly needs **BPSK/QPSK** (coherent PSK), **SDR‑class** hardware is the more realistic path than assuming a fixed UHF transceiver exposes PSK modes.

### 1.4 Practical conclusion from hardware
- For the “final choice” in a **COTS UHF transceiver** environment: treat **(G)FSK/GMSK** as baseline.
- Use **BPSK/QPSK** only if you are explicitly selecting an SDR/custom modem stack.

---

## 2) What you are optimizing (time, energy, probability of success)

For a fixed transmit power, you’re always trading:
- **Speed** (higher $R_b$) vs
- **reliability** (higher $E_b/N_0$ at the demod input) vs
- **overhead** (FEC expansion and/or ARQ retries).

The key “protocol‑level” driver in SISP is:
- On‑air unit is a **64‑byte frame** ($L=512$ bits before FEC expansion).
- **PER is what matters**, because a single corrupted 64‑byte frame is a failed protocol unit.

---

## 2.5) BER/PER requirements for inter‑satellite links: what is standardized vs what we choose

You’re right that **inter‑satellite UHF links (space↔space)** are not as “documented by one public standard” as spacecraft↔ground telemetry chains.

Still, two things carry over almost directly:
- The same link‑budget physics (FSPL + $kTB$) and the same modulation/coding families.
- The same *engineering practice* of stating a performance objective (BER/PER) and then picking modulation/FEC/ARQ to satisfy it with margin.

### What CCSDS‑type standards do (and do not) give you
- They standardize **framing concepts and coding/modulation options** widely used in space links.
- They typically do **not** mandate a universal “required BER” because acceptable residual error depends on higher layers (CRC, ARQ, file transfer protocol) and mission risk.

So in this study we explicitly choose a **protocol‑level objective** and translate it into a BER target.

### Mapping your 64‑byte frame PER target to a BER target

For independent bit errors (AWGN assumption), with $L=512$ bits:

$$\mathrm{PER} = 1-(1-\mathrm{BER})^{L}$$

For small BER this becomes:

$$\mathrm{PER}\approx L\cdot\mathrm{BER}=512\cdot\mathrm{BER}$$

Therefore, as a direct design rule for SISP frames:
- Target **PER ≤ $10^{-2}$** (1% frame loss) ⇒ **BER ≲ $2\times10^{-5}$**
- Target **PER ≤ $10^{-3}$** (0.1% frame loss) ⇒ **BER ≲ $2\times10^{-6}$**
- Target **PER ≤ $10^{-4}$** (0.01% frame loss) ⇒ **BER ≲ $2\times10^{-7}$**

How to apply this:
- **Control / correction frames:** pick a stricter PER (e.g., $10^{-3}$ or better) so the 5‑second correction window isn’t dominated by retries.
- **Bulk transfer frames:** if ARQ is enabled, higher PER can still converge, but it increases time/energy by roughly $1/(1-\mathrm{PER})$.

---

## 3) Link budget model (path loss + thermal noise)

### 3.1 Received power
In dB units (as used in the simulator):

$$P_r\,(\mathrm{dBm}) = P_t + G_t + G_r - L_{fs} - L_{misc} - L_{point}$$

This study uses **$L_{point}=0$ dB** (your “spherical / no pointing loss” requirement).

### 3.2 Free‑space path loss
With distance $d$ and carrier $f$:

$$L_{fs}\,(\mathrm{dB}) = 20\log_{10}(d) + 20\log_{10}(f) + 20\log_{10}\left(\frac{4\pi}{c}\right)$$

(Equivalent to the standard FSPL formula when $d$ is in meters and $f$ is in Hz.)

### 3.3 Thermal noise
Assume receiver noise is thermal‑dominated:

$$N = kTB$$

Convert to dBm:

$$N\,(\mathrm{dBm}) = 10\log_{10}(kTB) + 30$$

### 3.4 SNR and $E_b/N_0$

$$\mathrm{SNR} = \frac{C}{N} = \frac{C}{N_0B}$$

and

$$\frac{E_b}{N_0} = \mathrm{SNR}\cdot\frac{B}{R_b}$$

In dB:

$$\left(\frac{E_b}{N_0}\right)_{dB} = \mathrm{SNR}_{dB} + 10\log_{10}\left(\frac{B}{R_b}\right)$$

**Important consequence (why 20 kHz is not “free”):**
- If you widen bandwidth *and also increase bitrate* ($R_b \propto B$), then $E_b$ goes down (bits are sent faster at the same power), and $E_b/N_0$ typically drops by ~3 dB for each 2× in $R_b$.
- This is exactly the “fairness note” already stated in the existing evaluation doc.

---

## 4) Doppler (why coherent PSK is harder at UHF without SDR‑grade tracking)

Doppler shift magnitude is approximately:

$$f_d \approx \frac{v_r}{c} f_c$$

At $f_c=437$ MHz and $v_r\approx 7.5$ km/s (LEO‑class), the order of magnitude is:

$$f_d \sim 11\ \mathrm{kHz}$$

Key implication for a **10 kHz control channel**:
- Doppler is **comparable to the channel width**, so you must have **frequency tracking** (AFC, Doppler pre‑compensation, or a modem tolerant of frequency error).
- **Constant‑envelope FSK/GMSK** links are commonly used here specifically because they are operationally tolerant and have strong heritage.

This doesn’t “ban” BPSK/QPSK, but it increases the required modem sophistication.

---

## 5) BER models (uncoded) used in this study

These match `sisp_common_band_sim.py`.

Let $\gamma = E_b/N_0$ (linear).

### 5.1 BPSK and Gray‑QPSK (coherent)

$$P_b = Q(\sqrt{2\gamma}) = \tfrac{1}{2}\,\mathrm{erfc}(\sqrt{\gamma})$$

BPSK and Gray‑coded QPSK have the **same** BER vs $E_b/N_0$.

### 5.2 Orthogonal 2‑FSK (coherent)

$$P_b = Q(\sqrt{\gamma})$$

### 5.3 Orthogonal 2‑FSK (noncoherent)

$$P_b = \tfrac{1}{2}e^{-\gamma/2}$$

### 5.4 Quick numeric table (uncoded)

The following is included because it’s the key intuition: BPSK/QPSK is more power‑efficient than FSK in ideal coherent AWGN.

| $E_b/N_0$ (dB) | BPSK BER | 2FSK coherent BER | 2FSK noncoherent BER |
|---:|---:|---:|---:|
| -2 | 1.306e-01 | 2.135e-01 | 3.647e-01 |
| 0  | 7.865e-02 | 1.587e-01 | 3.033e-01 |
| 2  | 3.751e-02 | 1.040e-01 | 2.264e-01 |
| 4  | 1.250e-02 | 5.650e-02 | 1.424e-01 |
| 6  | 2.388e-03 | 2.301e-02 | 6.831e-02 |
| 8  | 1.909e-04 | 6.004e-03 | 2.132e-02 |
| 10 | 3.872e-06 | 7.827e-04 | 3.369e-03 |

---

## 6) Convolutional + Reed–Solomon model (engineering model, same as simulator)

This study keeps the exact “engineering approximations” already used in the repository simulator.

### 6.1 Convolutional coding (R=1/2)
- In the simulator, convolutional coding is approximated by a constant coding gain offset:

$$\left(\frac{E_b}{N_0}\right)_{\mathrm{eff}} = \left(\frac{E_b}{N_0}\right) + G_{\mathrm{conv}}$$

with

$$G_{\mathrm{conv}} \approx 10\log_{10}(5) \approx 7\ \mathrm{dB}$$

Then BER is evaluated using the uncoded formulas at $(E_b/N_0)_{eff}$.

**Note:** real convolutional performance depends on constraint length, puncturing, interleaving, decoder, etc. This is intentionally a simplified study.

### 6.2 Reed–Solomon RS(255,223) over bytes, $t=16$
The simulator models RS decode failure probability as a binomial tail on byte errors.

Given a post‑conv bit error rate $p_b$, approximate byte error probability:

$$p_{byte} = 1-(1-p_b)^8$$

RS decode fails if byte errors exceed $t=16$:

$$p_{fail} = P(X>16),\quad X\sim\mathrm{Binomial}(n=255, p=p_{byte})$$

The simulator converts this to an “effective BER” proxy:

$$p_{b,post} \approx 0.5\,p_{fail}$$

This is a pragmatic “PER‑driving” model, not a standards‑exact post‑FEC BER.

### 6.3 Coding expansion (on‑air bits per 64B protocol frame)
Let the 64B frame contain $L=512$ information bits.

- None: expansion $=1.0$ → on‑air bits $=512$
- Conv R=1/2: expansion $=2.0$ → on‑air bits $=1024$
- Conv+RS(255,223) combined rate $R=0.5\cdot223/255\approx 0.437$ → expansion $\approx 2.287$ → on‑air bits $\approx 1171$

These constants match the simulator.

---

## 7) PER model for the 64‑byte protocol frame

For independent bit errors (AWGN assumption), with $L=512$ info bits:

$$\mathrm{PER} = 1-(1-\mathrm{BER})^{L}$$

For small BER, approximation:

$$\mathrm{PER} \approx L\cdot\mathrm{BER}$$

**Important implication:** long frames punish you hard.
Example for BPSK uncoded:
- At $E_b/N_0=6$ dB: BER $\approx 2.4\times10^{-3}$ → PER(64B) $\approx 0.706$ (unusable).
- At $E_b/N_0=10$ dB: BER $\approx 3.9\times10^{-6}$ → PER(64B) $\approx 0.002$.

So for 64‑byte frames you often need **very low BER**, and that’s why **FEC matters** even when raw SNR looks “ok”.

---

## 8) Time + energy models (aligned to the Streamlit simulator)

### 8.1 Bitrate model (spectral efficiency)
In the simulator we use an engineering mapping:

$$R_b = B\cdot\eta$$

where $\eta$ is an assumed spectral efficiency.

The simulator uses:
- BPSK: $\eta\approx1$ b/s/Hz
- QPSK: $\eta\approx2$ b/s/Hz
- Orthogonal 2‑FSK: $\eta\approx0.5$ b/s/Hz

### 8.2 Frame time

$$t_{frame} = \frac{L\cdot\text{expansion}}{R_b}$$

### 8.3 Correction snapshot timing (SISP relevance)
For request + $N$ neighbor responses, repeated $R$ times, sequential channel access:

$$t_{snap} \approx R\cdot(1+N)\cdot t_{frame} + 2\frac{d}{c}$$

### 8.4 Energy model
The simulator separates a DC power model from RF link math:
- $P_{TX,DC}$: electrical power during transmit
- $P_{RX,DC}$: electrical power during receive

For a single continuous transfer of duration $t$:

$$E_{bulk} \approx t\,(P_{TX,DC}+P_{RX,DC})$$

For the correction snapshot, the simulator also breaks down requester TX vs neighbor RX, etc.

### 8.5 ARQ retry model (optional)
The simulator models expected transmissions per successful frame as:

$$E[T] = \frac{1}{1-\mathrm{PER}}$$

Then total expected time is multiplied by that factor.

---

## 9) Concrete numeric tables: 10 kHz vs 20 kHz (time + energy)

These tables are meant to be “protocol‑actionable”: 64‑byte framing + Conv/RS overhead.

### 9.1 Bulk example used in existing evaluation
Assumptions (same as the quick note, now fully quantified):
- Failure dump: **1 MiB**
- Compression: **3×** (so effective bytes $\approx 349{,}525$)
- Useful payload per 64B protocol frame: **45 bytes** → frames required **7768**
- DC power model: $P_{TX,DC}=10$ W, $P_{RX,DC}=2.5$ W (sim defaults)
- ARQ ignored here (assume PER is small after FEC)

#### A) 10 kHz channel (normal)
| Modulation family | FEC | Derived bitrate | Frame time | Total time | Total energy (TX+RX) |
|---|---|---:|---:|---:|---:|
| BPSK‑like | None | 10.0 kbps | 51.2 ms | 6.63 min | 1.38 Wh |
| BPSK‑like | Conv | 10.0 kbps | 102.4 ms | 13.26 min | 2.76 Wh |
| BPSK‑like | Conv+RS | 10.0 kbps | 117.1 ms | 15.16 min | 3.16 Wh |
| QPSK‑like | None | 20.0 kbps | 25.6 ms | 3.31 min | 0.69 Wh |
| QPSK‑like | Conv | 20.0 kbps | 51.2 ms | 6.63 min | 1.38 Wh |
| QPSK‑like | Conv+RS | 20.0 kbps | 58.5 ms | 7.58 min | 1.58 Wh |
| 2FSK/GMSK | None | 5.0 kbps | 102.4 ms | 13.26 min | 2.76 Wh |
| 2FSK/GMSK | Conv | 5.0 kbps | 204.8 ms | 26.51 min | 5.52 Wh |
| 2FSK/GMSK | Conv+RS | 5.0 kbps | 234.2 ms | 30.32 min | 6.32 Wh |

#### B) 20 kHz channel (emergency)
Same framing, just 2× bandwidth → 2× bitrate at same spectral efficiency.

| Modulation family | FEC | Derived bitrate | Frame time | Total time | Total energy (TX+RX) |
|---|---|---:|---:|---:|---:|
| BPSK‑like | Conv+RS | 20.0 kbps | 58.5 ms | 7.58 min | 1.58 Wh |
| QPSK‑like | Conv+RS | 40.0 kbps | 29.3 ms | 3.79 min | 0.79 Wh |
| 2FSK/GMSK | Conv+RS | 10.0 kbps | 117.1 ms | 15.16 min | 3.16 Wh |

**Key observation:** doubling bandwidth **cuts time and energy roughly in half** for a fixed file size, *but* it also reduces $E_b$ (because bits are sent faster at the same RF power). So you only get the time/energy win if the link margin still supports the required PER.

### 9.3 Same bulk example, mapped to real COTS channelization (12.5 kHz vs 25 kHz) with sender/receiver energy split

This section answers explicitly:
- energy of **sender alone** (TX)
- energy of **receiver alone** (RX)
- energy of **both together** (TX+RX)

All numbers below are computed with the same framing model and DC power model as the Streamlit simulator:
- Dump sizes: **1 MiB / 5 MiB / 10 MiB**
- Compression: **3×**
- Useful payload: **45 bytes per 64B frame** → frames scale linearly with dump size
- FEC: **Conv+RS** (coding expansion ≈ 2.287×)
- Power model: $P_{TX,DC}=10$ W, $P_{RX,DC}=2.5$ W
- ARQ: ignored (assumes PER is small enough after FEC; if not, scale time/energy by $1/(1-\mathrm{PER})$)

Derived bit rates use the same “spectral efficiency” mapping as the simulator:
- BPSK‑like: $\eta\approx 1$ b/s/Hz
- QPSK‑like: $\eta\approx 2$ b/s/Hz
- 2FSK/GMSK: $\eta\approx 0.5$ b/s/Hz

#### A) 12.5 kHz channel

**1 MiB dump**

| Modulation family | Derived bitrate | Total time | Energy (sender TX) | Energy (receiver RX) | Total energy (TX+RX) |
|---|---:|---:|---:|---:|---:|
| BPSK‑like | 12.50 kbps | 12.13 min | 2.02 Wh | 0.51 Wh | 2.53 Wh |
| QPSK‑like | 25.00 kbps | 6.06 min | 1.01 Wh | 0.25 Wh | 1.26 Wh |
| 2FSK/GMSK | 6.25 kbps | 24.26 min | 4.04 Wh | 1.01 Wh | 5.05 Wh |

**5 MiB dump**

| Modulation family | Derived bitrate | Total time | Energy (sender TX) | Energy (receiver RX) | Total energy (TX+RX) |
|---|---:|---:|---:|---:|---:|
| BPSK‑like | 12.50 kbps | 60.63 min | 10.11 Wh | 2.53 Wh | 12.63 Wh |
| QPSK‑like | 25.00 kbps | 30.32 min | 5.05 Wh | 1.26 Wh | 6.32 Wh |
| 2FSK/GMSK | 6.25 kbps | 121.27 min | 20.21 Wh | 5.05 Wh | 25.26 Wh |

**10 MiB dump**

| Modulation family | Derived bitrate | Total time | Energy (sender TX) | Energy (receiver RX) | Total energy (TX+RX) |
|---|---:|---:|---:|---:|---:|
| BPSK‑like | 12.50 kbps | 121.27 min | 20.21 Wh | 5.05 Wh | 25.26 Wh |
| QPSK‑like | 25.00 kbps | 60.63 min | 10.11 Wh | 2.53 Wh | 12.63 Wh |
| 2FSK/GMSK | 6.25 kbps | 242.53 min | 40.42 Wh | 10.11 Wh | 50.53 Wh |

#### B) 25 kHz channel

**1 MiB dump**

| Modulation family | Derived bitrate | Total time | Energy (sender TX) | Energy (receiver RX) | Total energy (TX+RX) |
|---|---:|---:|---:|---:|---:|
| BPSK‑like | 25.00 kbps | 6.06 min | 1.01 Wh | 0.25 Wh | 1.26 Wh |
| QPSK‑like | 50.00 kbps | 3.03 min | 0.51 Wh | 0.13 Wh | 0.63 Wh |
| 2FSK/GMSK | 12.50 kbps | 12.13 min | 2.02 Wh | 0.51 Wh | 2.53 Wh |

**5 MiB dump**

| Modulation family | Derived bitrate | Total time | Energy (sender TX) | Energy (receiver RX) | Total energy (TX+RX) |
|---|---:|---:|---:|---:|---:|
| BPSK‑like | 25.00 kbps | 30.32 min | 5.05 Wh | 1.26 Wh | 6.32 Wh |
| QPSK‑like | 50.00 kbps | 15.16 min | 2.53 Wh | 0.63 Wh | 3.16 Wh |
| 2FSK/GMSK | 12.50 kbps | 60.63 min | 10.11 Wh | 2.53 Wh | 12.63 Wh |

**10 MiB dump**

| Modulation family | Derived bitrate | Total time | Energy (sender TX) | Energy (receiver RX) | Total energy (TX+RX) |
|---|---:|---:|---:|---:|---:|
| BPSK‑like | 25.00 kbps | 60.63 min | 10.11 Wh | 2.53 Wh | 12.63 Wh |
| QPSK‑like | 50.00 kbps | 30.32 min | 5.05 Wh | 1.26 Wh | 6.32 Wh |
| 2FSK/GMSK | 12.50 kbps | 121.27 min | 20.21 Wh | 5.05 Wh | 25.26 Wh |

**Interpretation for the “final choice”:**
- If you constrain to **real transceiver modes**, compare primarily within the **2FSK/GMSK rows**, then decide if emergency uses **25 kHz** or bonding.
- The “BPSK/QPSK” rows remain useful as a **mathematical lower bound** (what an SDR/coherent modem could achieve at the same DC power model), but many COTS UHF radios do not expose coherent PSK as a flight‑qualified fixed mode.

### 9.2 Correction snapshot time (5‑second timer relevance)
Assumptions:
- N=8 neighbors
- repeats=1
- distance=1000 km (prop delay is only ~6.7 ms round trip)
- FEC: Conv+RS (same as above)

With 10 kHz control:
- BPSK‑like: snapshot time ≈ **1.061 s**
- QPSK‑like: snapshot time ≈ **0.534 s**
- 2FSK/GMSK: snapshot time ≈ **2.114 s**

Even the robust 2FSK/GMSK+Conv+RS control PHY typically fits within the 5‑second correction window in the simulator’s timing model.

---

## 10) BER/PER vs distance examples (how 20 kHz can hurt reliability)

The simulator computes distance → FSPL → SNR → $E_b/N_0$ → BER → PER.

A single illustrative configuration (chosen to make the curve visible):
- $f=437$ MHz
- $P_{TX}=27$ dBm (0.5 W)
- $G_t=G_r=2$ dBi
- $T_{sys}=500$ K
- $L_{misc}=3$ dB
- $L_{point}=0$ dB

Under these assumptions:
- At around **2500–3500 km**, uncoded PER can become very large for 64B frames.
- Convolutional (with the +7 dB offset engineering model) can reduce PER dramatically.

This is precisely why the architecture “10 kHz control always + emergency bulk only when needed” is sensible: you keep the reliable low‑rate path alive while reserving the fast mode for windows where margin is adequate.

---

## 11) Why not use BPSK/QPSK globally for everything?

In ideal AWGN math, BPSK/QPSK looks attractive. In flight reality (especially at UHF narrowband):

1) **Hardware support:** many COTS UHF transceivers expose FSK/GMSK modes, not coherent PSK modes.
2) **Doppler + frequency error:** coherent PSK demands tighter carrier recovery; Doppler can be kHz‑class at 437 MHz.
3) **Power amplifier efficiency:** constant‑envelope modulations can run a PA closer to saturation (higher efficiency). Coherent PSK often needs more linearity, which can *hurt DC power efficiency* in practice.
4) **Protocol requirement:** control/corrections are small; the main bottleneck is bulk dump time. A two‑mode PHY attacks the bottleneck directly.

So “BPSK/QPSK everywhere” is only clearly superior if you are also committing to the modem + hardware stack (typically SDR‑class) that makes it operationally robust.

---

## 12) What to modify/add in the C++ protocol/state machine (design only)

This section is **design guidance only**. It does not change code.

The minimum you need is a way to:
- announce a PHY switch (control → emergency),
- confirm both peers are ready,
- schedule the switch time,
- and guarantee a safe fallback.

### 12.1 Add a “PHY profile” concept
Define a small enumeration of PHY profiles supported by the node, e.g.:
- `PHY0_CONTROL_10K_GMSK_CONV_RS`
- `PHY1_BULK_20K_GMSK_CONV_RS`
- (optional SDR path) `PHY2_BULK_20K_QPSK_CONV_RS`

Each profile implies:
- nominal bandwidth ($B$),
- modulation family,
- coding mode,
- derived bitrate,
- and any modem parameters needed.

### 12.2 New control messages (service types)
Add 2–3 lightweight control payloads carried in existing 64B frames:
- `PHY_CAPS` — advertise supported profiles (sent periodically or on join)
- `PHY_SWITCH_PROPOSE(profile_id, t_switch, t_valid)`
- `PHY_SWITCH_ACK(profile_id, t_switch)`
- (optional) `PHY_SWITCH_END(profile_id)`

**Scheduling** matters: switch at a specific offset/time so both sides change at the same moment.

### 12.3 State machine impact (high level)
In the current state machine, bulk relay is already a multi‑step handshake. Insert PHY switching as a sub‑handshake:

1) Control PHY: request relay / bulk transfer
2) Agree on PHY profile (intersection of capabilities)
3) Switch to emergency PHY at `t_switch`
4) Bulk data transfer (existing framing, just different modem settings)
5) Switch back to control PHY (explicit end message or `t_valid` timeout)

Candidate implementation areas (for later coding work):
- state logic: `c++ implemnetation/src/sisp_state_machine.cpp`
- protocol service IDs / frame payload mapping: `c++ implemnetation/include/sisp_protocol.hpp`
- encoder/decoder wiring: `c++ implemnetation/src/sisp_encoder.cpp`, `c++ implemnetation/src/sisp_decoder.cpp`

### 12.4 Backward compatibility + safety
- If a neighbor does not understand `PHY_SWITCH_*`, it will ignore it and remain on the control PHY.
- Therefore: only switch to emergency PHY after receiving an explicit ACK.
- Use a conservative timeout (`t_valid`) so nodes automatically revert to control PHY.

---

## 13) How to validate this study in the repo

1) Run the simulator:

```bash
streamlit run "simulation for signal and physics/sisp_common_band_sim.py"
```

2) Check:
- PER vs distance for control PHY
- 5‑second correction snapshot feasibility
- Bulk dump time/energy for (10 kHz control) vs (20 kHz emergency) **as a proxy** for the practical COTS mapping (12.5 kHz / 25 kHz)

3) Adjust with mission‑realistic values:
- $L_{misc}$ (implementation + polarization + feeder losses)
- $T_{sys}$ (receiver noise figure + sky temperature)
- antenna gains / geometry

---

## 14) What the “three simulations” in this repo are (and how they relate)

This repo has multiple “simulators”, but they answer different questions.

1) **PHY/link + time/energy study (UHF‑focused):**
  - `simulation for signal and physics/sisp_common_band_sim.py`
  - Purpose: compute link budget → $E_b/N_0$ → BER/PER, then map into SISP timing and **TX vs RX energy** (5‑second correction snapshot + bulk dump with optional emergency PHY override).
  - This markdown document is intended to match its equations and assumptions.

2) **Signal/BER plotting sandbox (link‑level curves; originally Ka baseline):**
  - `simulation for signal and physics/sisp_signal_sim.py`
  - Purpose: plot BER/PER curves vs $E_b/N_0$ and range for modulation/FEC combinations.
  - It uses the same “Conv gain + RS tail probability” engineering model, and is useful for quickly visualizing how coding changes shift PER.

3) **Protocol/state‑machine integration harness (end‑to‑end behavior):**
  - `python_satellite_sim_v2.py` (and the lighter `python_satellite_sim.py`)
  - Purpose: exercise the **C++ state machine** through scenarios (loss injection, multi‑sat interactions, relaying, correction propagation). It is not a link budget tool; it’s a protocol correctness + behavior tool.

And a “sanity check” script:
- `simulation for signal and physics/validate_bpsk_awgn.py` validates that the BPSK AWGN BER implementation matches the theory curve (Monte Carlo vs formula).

---

## 15) Scope notes / limitations

- AWGN BER models are not a complete channel model (no fading, interference, adjacent channel, etc.).
- The convolutional model is a constant +7 dB offset (engineering proxy).
- RS success model is a binomial byte‑error approximation.

Despite these simplifications, the document still correctly captures the *protocol‑level* trade:
- **PER is brutal** for 64‑byte frames unless BER is extremely low.
- **FEC increases time** (expansion) but can dramatically reduce retries / failure.
- **Wider emergency channels** (e.g., 25 kHz) reduce time/energy but reduce $E_b$; they must be invoked only when margin is adequate.
