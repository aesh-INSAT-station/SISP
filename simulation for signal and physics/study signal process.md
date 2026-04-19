# SISP Module M3: Physical Layer and Signal Model

## 1. The Transmitted Signal Model

SISP uses BPSK (Binary Phase Shift Keying) for its Inter-Satellite Links (ISL). The continuous-time passband signal transmitted by satellite A is modeled as:
$$s(t) = \sqrt{2P_{tx}} \cdot b(t) \cdot \cos(2\pi f_c t + \varphi_0)$$
where $b(t) \in \{-1, +1\}$ is the NRZ baseband bit stream with duration $T_b = 1/R_b$ ($R_b$ is the bit rate), $f_c$ is the carrier frequency, and $\varphi_0$ is the initial phase offset.

The energy per bit is given by:
$$E_b = P_{tx} \cdot T_b = \frac{P_{tx}}{R_b}$$
For the SISP Ka-band baseline of $P_{tx} = 1\text{ W}$ ($30\text{ dBm}$) and $R_b = 100\text{ kbps}$, the energy per bit is $E_b = 10^{-5}\text{ J}$ ($-50\text{ dBJ}$).

---

## 2. Channel Impairments

### 2.1 Free-Space Path Loss (Friis Equation)
The received signal power at distance $d$ is dictated by the Friis transmission equation. In decibels, the free-space path loss $L_{fs}$ is:
$$L_{fs}(\text{dB}) = 20\log_{10}(d) + 20\log_{10}(f_c) + 20\log_{10}\left(\frac{4\pi}{c}\right)$$
At $d = 1000\text{ km}$ and $f_c = 26\text{ GHz}$:
$$L_{fs} = 120\text{ dB} + 208.3\text{ dB} - 147.5\text{ dB} \approx 180.7\text{ dB}$$

### 2.2 Doppler Shift
For two LEO satellites moving with a relative radial velocity $v_r$, the Doppler shift $\Delta f$ is:
$$\Delta f = f_c \cdot \frac{v_r}{c}$$
For non-coplanar LEOs, $v_r \approx 1\text{ km/s}$. At $26\text{ GHz}$, this results in a shift of $\Delta f \approx 86.7\text{ kHz}$. **Doppler pre-compensation is strictly required**, as this shift consumes nearly the entire channel bandwidth.

### 2.3 Thermal Noise
The received noise is modeled as Additive White Gaussian Noise (AWGN). The noise power $N$ in bandwidth $B$ is:
$$N = k_B \cdot T_{sys} \cdot B$$
Assuming a Ka-band CubeSat system temperature $T_{sys} \approx 280\text{ K}$, the noise spectral density is $N_0 = k_B T_{sys} = -174.1\text{ dBm/Hz}$. 
For a matched bandwidth of $B = 100\text{ kHz}$, total noise power $N \approx -124.1\text{ dBm}$.

---

## 3. Complete Link Budget

$$\text{SNR}(\text{dB}) = P_{tx} + G_{tx} + G_{rx} - L_{fs} - L_{point} - N$$
$$\frac{E_b}{N_0}(\text{dB}) = \text{SNR}(\text{dB}) + 10\log_{10}\left(\frac{B}{R_b}\right)$$

**Baseline Link (1000 km, 26 GHz):**
* **Tx Power:** $+30\text{ dBm}$ ($1\text{ W}$)
* **Antenna Gains:** $+23\text{ dBi}$ (Tx) and $+23\text{ dBi}$ (Rx)
* **Path Loss:** $180.7\text{ dB}$
* **Pointing Loss:** $2\text{ dB}$
* **Noise Power:** $-124.1\text{ dBm}$
* **Total SNR & $E_b/N_0$ (with $B=R_b$):** $\mathbf{+17.4\text{ dB}}$

> Note: with $+10\text{ dBi}$ antennas at both ends, the same 1000 km Ka-band link gives $E_b/N_0 \approx -8.6\text{ dB}$ (i.e., it will not close without shorter ranges or higher gain/power).

---

## 4. Forward Error Correction (FEC) & PER Analysis

SISP employs a concatenated coding scheme to ensure data integrity at extended ranges.

**1. Uncoded BPSK:**
$$\text{BER}_{\text{BPSK}} = \frac{1}{2}\text{erfc}\left(\sqrt{\frac{E_b}{N_0}}\right)$$

**2. Inner Code (Rate-1/2 Convolutional, K=7):**
$$\text{BER}_{\text{conv}} \approx \frac{1}{2}\text{erfc}\left(\sqrt{5\frac{E_b}{N_0}}\right)$$

**3. Outer Code (Reed-Solomon RS(255,223)):**
The residual symbol error rate after correcting up to $t=16$ errors is:
$$P_{RS} \approx \binom{255}{17} P_{byte}^{17} (1-P_{byte})^{238}$$
This scheme provides a coding gain of $\approx 7\text{ dB}$, achieving a $10^{-6}$ BER at an $E_b/N_0$ of **$4.5\text{ dB}$**.

**Packet Error Rate (PER):**
The probability that an $L$-bit coded packet drops is:
$$\text{PER}(L, p_b) = 1 - (1 - p_b)^L \approx L \cdot p_b$$
By enforcing a **fixed 64-byte frame size** (512 uncoded bits $\rightarrow$ ~1172 coded bits on-air), the worst-case PER remains $\approx 10^{-3}$ at threshold limits, providing massive fade margin.

In practice, PER is sensitive to the chosen coding/decoder model and to how framing/checksums are applied; use the Streamlit simulator sweep to read off the PER vs distance curve directly.

---

## 5. Energy vs. Battery Duty Cycle

* **Tx Active Cost:** $10\text{ W}$ DC
* **Rx Active Cost:** $2.5\text{ W}$ DC
* **Tx Time per Day (Typical):** $< 1\text{ second}$ ($\approx 0.001\text{ Wh}$)
* **Rx Time per Day (Windowed):** $\approx 1\text{ hour}$ ($\approx 2.5\text{ Wh}$)

For a 30 Wh CubeSat battery, operating the SISP protocol consumes roughly **10-15%** of the daily power budget, making it highly suitable as a secondary/diagnostic payload.

---

## 6. Simulation Source Code (Streamlit)

Run the interactive Streamlit simulator (source of truth):

```bash
streamlit run sisp_signal_sim.py
```
