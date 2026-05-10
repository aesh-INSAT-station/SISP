# Signal Physics: Link Budget, BER/PER, Dual-PHY 437 MHz

**Source files:**
- `simulation for signal and physics/sisp_unified_sim.py` — Streamlit simulation
- `simulation for signal and physics/SISP_SCIENTIFIC_REPORT_INTERSAT_UHF.md`
- `simulation for signal and physics/UHF_437_two_mode_phy_hardware_math_study.md`
- `simulation for signal and physics/validate_bpsk_awgn.py` — Monte Carlo validation

---

## Frequency Band

SISP uses the **435–438 MHz amateur satellite allocation** (ITU Region 1/2/3).

- Globally available, no coordination required for CubeSats.
- Supported by COTS UHF transceivers (AstroDev Lithium-1, GomSpace AX100, etc.).
- 35.5 dB path loss advantage over Ka-band (26 GHz) at the same distance.

---

## Dual-PHY Architecture

Two physical layer profiles share the same 437 MHz centre frequency:

| Profile | Enum | Bandwidth | Bit rate (GMSK) | Usage |
|---|---|---|---|---|
| `CONTROL_437_NARROW` | `0x00` | 12.5 kHz | 12,500 bps | All control messages |
| `BULK_437_WIDE` | `0x01` | 25 kHz | 25,000 bps | `DOWNLINK_DATA`, `DOWNLINK_ACK` |

The state machine selects the profile per-frame in `select_tx_phy()`. The choice is encoded in **frame byte 8** and validated in `test_dual_phy_437.py` (8/8 assertions pass).

---

## Modulation

### GMSK BT=0.3 (baseline)

Gaussian Minimum Shift Keying with bandwidth-time product BT = 0.3.

**Why GMSK?**
- Constant envelope → tolerates non-linear power amplifiers (common in small satellites).
- Supported in all COTS UHF radios as the hardware modem mode.
- Robust to phase noise and moderate Doppler.

**BER formula** (Murota & Hirade, 1981, §III):

$$P_b^{\text{GMSK}} = \frac{1}{2}\operatorname{erfc}\!\left(\sqrt{\alpha_{BT} \cdot \frac{E_b}{N_0}}\right)$$

| BT | $\alpha_{BT}$ | Penalty vs BPSK |
|---|---|---|
| ∞ (BPSK limit) | 1.00 | 0 dB |
| 0.5 | 0.76 | 1.2 dB |
| **0.3** | **0.68** | **1.67 dB** |
| 0.2 | 0.53 | 2.8 dB |

The 1.67 dB penalty at BT=0.3 is the price of hardware simplicity.

### Other supported modulations (Streamlit simulation)

| Label | Key | BER formula |
|---|---|---|
| BPSK (coherent) | `BPSK` | $\frac{1}{2}\operatorname{erfc}(\sqrt{E_b/N_0})$ |
| QPSK (Gray, coherent) | `QPSK` | same as BPSK per bit |
| 2-FSK coherent | `2FSK_COH` | $Q(\sqrt{E_b/N_0})$ |
| 2-FSK noncoherent | `2FSK_NONCOH` | $\frac{1}{2}e^{-E_b/(2N_0)}$ |

---

## Forward Error Correction

### Stage 1: Convolutional K=7, R=1/2

NASA/3GPP standard code. Soft-decision Viterbi decoding.

**Post-decoding BER (Heller-Jacobs union bound):**

$$P_b^{\text{CONV}} \leq 36 \cdot Q\!\left(\sqrt{10 \cdot \frac{E_b}{N_0}}\right)$$

where $d_{\text{free}} = 10$ is the free distance of the K=7 R=1/2 code and 36 is the leading spectral coefficient. This replaces the sloppy constant +7 dB proxy used in early literature.

**Coding expansion:** $1/R = 2.0$ (doubles the on-air bit count).

### Stage 2: RS(255, 223), t=16

Reed-Solomon outer code. Corrects up to 16 byte errors per 255-byte codeword.

Byte error probability from Viterbi residual BER $p$:

$$p_{\text{byte}} = 1 - (1-p)^8$$

RS decode failure (more than 16 byte errors):

$$p_{\text{fail}} = P(N_{\text{err}} > 16) = \sum_{j=17}^{255} \binom{255}{j} p_{\text{byte}}^j (1-p_{\text{byte}})^{255-j}$$

Post-RS BER (failed blocks → random): $P_b^{\text{RS}} = 0.5 \cdot p_{\text{fail}}$

**Combined coding expansion:** $1/(0.5 \times 223/255) \approx 2.287$.

---

## Link Budget

### Free-Space Path Loss

$$L_{fs}(\text{dB}) = 20\log_{10}(d_{\text{m}}) + 20\log_{10}(f_{\text{Hz}}) + 20\log_{10}\!\left(\frac{4\pi}{c}\right)$$

| Distance | 437 MHz | 26 GHz (Ka-band) |
|---|---|---|
| 400 km | 139.6 dB | 175.0 dB |
| 1000 km | 145.3 dB | 180.7 dB |
| 2000 km | 151.3 dB | 186.7 dB |

### Receiver Noise

System noise temperature from receiver noise figure NF and antenna temperature:

$$T_{sys} = T_{\text{ant}} + T_0 \cdot (10^{NF/10} - 1), \quad T_0 = 290\,\text{K}$$

For NF = 5 dB, $T_{\text{ant}} = 100$ K: $T_{sys} \approx 1130$ K.

Noise power in bandwidth $B$:

$$N = kT_{sys}B \quad [\text{W}], \quad N_{\text{dBm}} = 10\log_{10}(kT_{sys}B) + 30$$

### Signal-to-Noise Ratio

$$\text{SNR}_{\text{dB}} = P_{tx} + G_t + G_r - L_{fs} - L_{\text{point}} - L_{\text{misc}} - L_{\text{Doppler}} - N_{\text{dBm}}$$

$$\frac{E_b}{N_0}\,[\text{dB}] = \text{SNR}_{\text{dB}} + 10\log_{10}\!\left(\frac{B}{R_b}\right)$$

### Doppler Guard Margin

At 437 MHz with relative velocity $v_r = 7.5$ km/s between LEO satellites:

$$\Delta f_{\max} = 437 \times 10^6 \times \frac{7500}{3 \times 10^8} \approx 10.9\,\text{kHz}$$

This nearly fills the 12.5 kHz control channel. A guard margin of **1.5 dB** is applied in the UHF link budget to account for residual frequency error after automatic frequency correction (AFC).

### Reference Link Budget (1000 km, 437 MHz, GMSK Conv+RS)

| Parameter | Value |
|---|---|
| Tx power | 30 dBm (1 W) |
| Tx gain | 2 dBi (omnidirectional) |
| Rx gain | 2 dBi |
| Path loss | 145.3 dB |
| Pointing loss | 0 dB (omnidirectional) |
| Misc loss | 3 dB |
| Doppler margin | 1.5 dB |
| Noise (12.5 kHz, 1130 K) | −124.6 dBm |
| **SNR** | **−121.3 + 30 + 4 − 4.5 + 124.6 = +8.8 dB** |
| B/Rb ratio (GMSK) | 0 dB |
| **Eb/N0** | **+8.8 dB** |
| Required Eb/N0 (PER<1%) | ~5.5 dB (GMSK Conv+RS) |
| **Link margin** | **~3.3 dB** |

---

## Packet Error Rate

For a 64-byte (512-bit) frame with bit error probability $p$:

$$\text{PER} = 1 - \exp(512 \cdot \ln(1-p)) \approx 1 - (1-p)^{512}$$

Approximate PER at 1000 km (from simulation, GMSK Conv+RS):

| Eb/N0 | BER | PER (64B frame) |
|---|---|---|
| 4 dB | ~1×10⁻³ | ~40% |
| 6 dB | ~1×10⁻⁵ | ~0.5% |
| 8 dB | ~1×10⁻⁷ | ~0.005% |
| 10 dB | ~1×10⁻⁹ | negligible |

At the reference link budget above (+8.8 dB Eb/N0), PER ≈ 0.01% — well below the ARQ retry budget.

---

## Monte Carlo Validation

From `validate_bpsk_awgn.py` (500,000 bits):

| Eb/N0 | Theory | Simulation | Match |
|---|---|---|---|
| 0 dB | 7.865×10⁻² | 7.897×10⁻² | ✓ (<1%) |
| 4 dB | 1.250×10⁻² | 1.247×10⁻² | ✓ (<1%) |
| 8 dB | 1.909×10⁻⁴ | 1.820×10⁻⁴ | ✓ (<5%) |
| 10 dB | 3.872×10⁻⁶ | 0 (no errors observed) | ✓ |

The BER implementation is validated to within Monte Carlo variance at all noise levels.

---

## Maximum Usable Range

Inverting the link budget for PER ≤ 1%, GMSK Conv+RS:

| Configuration | $d_{\max}$ |
|---|---|
| 437 MHz control (12.5 kHz), 1 W omni | ~2,800 km |
| 437 MHz bulk (25 kHz), 1 W omni | ~2,100 km |
| Ka-band (26 GHz), 1 W, +23 dBi directive | ~4,400 km |

All ranges exceed typical LEO inter-satellite spacing (400–600 km). **Geometry, not link budget, limits neighbourhood size.**

---

## Running the Streamlit Simulation

```bash
streamlit run "simulation for signal and physics/sisp_unified_sim.py"
```

**Tab 1 — Geometry:** Earth blockage + Doppler from TLE inputs. Shows LoS windows, slant range, and Doppler evolution.

**Tab 2 — PHY (BER/PER):** BER curves for all modulations and FEC levels. PER vs distance at selected link budget parameters.

**Tab 3 — Timing & Energy:** Correction snapshot timing (5-second window check) and bulk dump time/energy.

**Tab 4 — Protocol Message Energy:** Run C++ DLL probe; see frame counts per service and dual-PHY breakdown table.

**Tab 5 — KPI Dashboard:** Energy per MiB, % of daily budget, ground-link comparison.
