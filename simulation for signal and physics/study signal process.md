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
$$L_{fs} = 120\text{ dB} + 194.3\text{ dB} - 169.5\text{ dB} = 144.8\text{ dB}$$

### 2.2 Doppler Shift
For two LEO satellites moving with a relative radial velocity $v_r$, the Doppler shift $\Delta f$ is:
$$\Delta f = f_c \cdot \frac{v_r}{c}$$
For non-coplanar LEOs, $v_r \approx 1\text{ km/s}$. At $26\text{ GHz}$, this results in a shift of $\Delta f \approx 86.7\text{ kHz}$. **Doppler pre-compensation is strictly required**, as this shift consumes nearly the entire channel bandwidth.

### 2.3 Thermal Noise
The received noise is modeled as Additive White Gaussian Noise (AWGN). The noise power $N$ in bandwidth $B$ is:
$$N = k_B \cdot T_{sys} \cdot B$$
Assuming a Ka-band CubeSat system temperature $T_{sys} \approx 280\text{ K}$, the noise spectral density is $N_0 = k_B T_{sys} = -174.1\text{ dBm/Hz}$. 
For a matched bandwidth of $B = 100\text{ kHz}$, total noise power $N = -114.1\text{ dBm}$.

---

## 3. Complete Link Budget

$$\text{SNR}(\text{dB}) = P_{tx} + G_{tx} + G_{rx} - L_{fs} - L_{point} - N$$
$$\frac{E_b}{N_0}(\text{dB}) = \text{SNR}(\text{dB}) + 10\log_{10}\left(\frac{B}{R_b}\right)$$

**Baseline Link (1000 km, 26 GHz):**
* **Tx Power:** $+30\text{ dBm}$ ($1\text{ W}$)
* **Antenna Gains:** $+10\text{ dBi}$ (Tx) and $+10\text{ dBi}$ (Rx)
* **Path Loss:** $-144.8\text{ dB}$
* **Pointing Loss:** $-2\text{ dB}$
* **Noise Power:** $-114.1\text{ dBm}$
* **Total SNR & Eb/N0:** $\mathbf{+17.3\text{ dB}}$

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

---

## 5. Energy vs. Battery Duty Cycle

* **Tx Active Cost:** $10\text{ W}$ DC
* **Rx Active Cost:** $2.5\text{ W}$ DC
* **Tx Time per Day (Typical):** $< 1\text{ second}$ ($\approx 0.001\text{ Wh}$)
* **Rx Time per Day (Windowed):** $\approx 1\text{ hour}$ ($\approx 2.5\text{ Wh}$)

For a 30 Wh CubeSat battery, operating the SISP protocol consumes roughly **10-15%** of the daily power budget, making it highly suitable as a secondary/diagnostic payload.

---

## 6. Simulation Source Code (Streamlit)

Save as `sisp_signal_sim.py` and run `streamlit run sisp_signal_sim.py`:

```python
import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from scipy.special import erfc, comb

def calc_ber_uncoded(ebn0_db):
    ebn0_lin = 10**(ebn0_db / 10)
    return 0.5 * erfc(np.sqrt(ebn0_lin))

def calc_ber_conv(ebn0_db):
    ebn0_lin = 10**(ebn0_db / 10)
    return 0.5 * erfc(np.sqrt(5 * ebn0_lin))

def calc_ber_concatenated(ebn0_db):
    ber_c = calc_ber_conv(ebn0_db)
    p_byte = 1 - (1 - ber_c)**8 
    p_rs = np.zeros_like(p_byte)
    for i in range(len(p_byte)):
        if p_byte[i] > 1e-10:
            p_rs[i] = comb(255, 17) * (p_byte[i]**17) * ((1 - p_byte[i])**238)
        else:
            p_rs[i] = 0.0
    return p_rs / 2 

def calc_link_budget(d_km, p_tx_dbm, f_c_ghz, g_tx, g_rx, t_sys, b_hz, rb_bps):
    c = 3e8
    f_c_hz = f_c_ghz * 1e9
    d_m = d_km * 1000
    l_fs_db = 20 * np.log10(d_m) + 20 * np.log10(f_c_hz) + 20 * np.log10(4 * np.pi / c)
    l_point_db = 2.0
    n_w = 1.38e-23 * t_sys * b_hz
    n_dbm = 10 * np.log10(n_w) + 30
    snr_db = p_tx_dbm + g_tx + g_rx - l_fs_db - l_point_db - n_dbm
    ebn0_db = snr_db + 10 * np.log10(b_hz / rb_bps)
    return snr_db, ebn0_db

def calc_per(ber, uncoded_bits):
    coded_bits = int(uncoded_bits * 2.29) 
    return 1 - (1 - ber)**coded_bits

st.title("SISP Module M3: Physical Layer")
packets = {"CORRECTION_REQ (8B)": 64, "CORRECTION_RSP (22B)": 176, "Simulator Frame (64B)": 512}

tab1, tab2, tab3 = st.tabs(["Plot 1: BER Curves", "Plot 2: Distance Range", "Plot 3: PER vs Range"])

with tab1:
    ebn0_range = np.linspace(0, 14, 500)
    fig1, ax1 = plt.subplots(figsize=(10, 5))
    ax1.semilogy(ebn0_range, calc_ber_uncoded(ebn0_range), label='Uncoded BPSK')
    ax1.semilogy(ebn0_range, calc_ber_concatenated(ebn0_range), label='Concatenated (Conv+RS)')
    ax1.axhline(y=1e-6, color='red', linestyle='--', label='Target BER (10^-6)')
    ax1.set(ylim=(1e-12, 1), xlabel='Eb/N0 (dB)', ylabel='BER')
    ax1.legend()
    st.pyplot(fig1)

with tab2:
    p_tx = st.slider("Tx Power (dBm)", 20.0, 40.0, 30.0)
    d_range = np.logspace(2, 5, 500)
    _, ebn0_ka = calc_link_budget(d_range, p_tx, 26.0, 10, 10, 280, 1e5, 1e5)
    fig2, ax2 = plt.subplots(figsize=(10, 5))
    ax2.semilogx(d_range, ebn0_ka, label='Ka-Band (26 GHz)')
    ax2.axhline(y=4.5, color='green', linestyle='--', label='Min Viable (4.5 dB)')
    ax2.set(xlabel='Distance (km)', ylabel='Received Eb/N0 (dB)')
    ax2.legend()
    st.pyplot(fig2)

with tab3:
    d_range_per = np.linspace(100, 100000, 500)
    _, ebn0_per = calc_link_budget(d_range_per, p_tx, 26.0, 10, 10, 280, 1e5, 1e5)
    ber_for_per = calc_ber_concatenated(ebn0_per)
    fig3, ax3 = plt.subplots(figsize=(10, 5))
    for name, bits in packets.items():
        ax3.semilogy(d_range_per, calc_per(ber_for_per, bits), label=f'{name}')
    ax3.axhline(y=1e-4, color='black', linestyle='--')
    ax3.set(ylim=(1e-6, 1), xlim=(10000, 100000), xlabel='Distance (km)', ylabel='PER')
    ax3.legend()
    st.pyplot(fig3)