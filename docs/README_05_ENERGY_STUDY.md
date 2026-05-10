# Energetic Study

**Source files:**
- `simulation for signal and physics/sisp_unified_sim.py` — Streamlit: Timing & Energy tab, Protocol Message Energy tab, KPI Dashboard tab
- `simulation for signal and physics/UHF_437_two_mode_phy_hardware_math_study.md` — Numeric tables

---

## Energy Model

### Frame-Level DC Power Model

Every transmitted or received frame costs energy:

$$E_{TX} = P_{TX,DC} \cdot t_{\text{frame}}, \quad E_{RX} = P_{RX,DC} \cdot t_{\text{frame}}$$

$$t_{\text{frame}} = \frac{N_{\text{air}}}{R_b}, \quad N_{\text{air}} = 512 \times \text{expansion}$$

**Default parameters:**

| Parameter | Value |
|---|---|
| Tx DC power ($P_{TX}$) | 10 W |
| Rx DC power ($P_{RX}$) | 2.5 W |
| Frame size | 64 bytes = 512 bits |
| Conv coding expansion | 2.0× |
| Conv+RS coding expansion | 2.287× |

**Frame time for each configuration:**

| Channel | Modulation | FEC | $R_b$ (bps) | $t_{\text{frame}}$ |
|---|---|---|---|---|
| 12.5 kHz CTRL | GMSK BT=0.3 | None | 12,500 | 41 ms |
| 12.5 kHz CTRL | GMSK BT=0.3 | Conv | 12,500 | 82 ms |
| 12.5 kHz CTRL | GMSK BT=0.3 | Conv+RS | 12,500 | 93.6 ms |
| 25 kHz BULK | GMSK BT=0.3 | Conv+RS | 25,000 | 46.8 ms |

---

## Correction Snapshot Energy

### Model

One correction cycle involves 1 requester and $N$ neighbours. Each sends one frame. The total on-air time is:

$$t_{\text{snap}} \approx (1 + N) \cdot t_{\text{frame}} + 2 \cdot t_{\text{prop}}$$

$$t_{\text{prop}} = \frac{d}{c} \approx 3.3\,\text{ms at 1000 km} \quad \text{(negligible vs. frame time)}$$

Network energy (both TX and RX sides):

$$E_{\text{snap}} = \underbrace{P_{TX} \cdot t_{\text{frame}}}_{\text{requester TX}} + \underbrace{N \cdot P_{RX} \cdot t_{\text{frame}}}_{\text{neighbours RX}} + \underbrace{N \cdot P_{TX} \cdot t_{\text{frame}}}_{\text{neighbours TX}} + \underbrace{P_{RX} \cdot N \cdot t_{\text{frame}}}_{\text{requester RX}}$$

Simplified for $N$ symmetric neighbours:

$$E_{\text{snap}} \approx (1 + N)(P_{TX} + P_{RX}) \cdot t_{\text{frame}}$$

### Numerics (N=8, Conv+RS, 12.5 kHz)

| Item | Value |
|---|---|
| Frame time | 93.6 ms |
| Total on-air time | $9 \times 93.6 + 6.6 \approx 849$ ms |
| Within 5-second timer? | **YES** (849 ms ≪ 5000 ms) |
| Requester TX energy | $10 \times 0.0936 = 0.936$ J |
| Requester RX energy | $2.5 \times 8 \times 0.0936 = 1.87$ J |
| Neighbours TX energy | $8 \times 10 \times 0.0936 = 7.49$ J |
| Neighbours RX energy | $8 \times 2.5 \times 0.0936 = 1.87$ J |
| **Network total** | **~12.2 J per correction event** |

At 24 corrections per day:

$$E_{\text{daily,corr}} = 24 \times 12.2 \approx 293\,\text{J} \approx 0.081\,\text{Wh}$$

---

## Bulk Relay / Borrow Energy

### Model

For a payload of size $S$ bytes (before compression) with compression ratio $\rho$:

$$N_{\text{frames}} = \left\lceil \frac{S / \rho}{P_{\text{bytes}}}\right\rceil, \quad P_{\text{bytes}} = 45 \text{ B (default payload per 64 B frame)}$$

With ARQ and per-frame PER $p$:

$$E[\text{frames sent}] = \frac{N_{\text{frames}}}{1 - p}$$

Total bulk time:

$$t_{\text{bulk}} = E[\text{frames}] \times t_{\text{frame}}$$

Total energy:

$$E_{\text{bulk}} = t_{\text{bulk}} \times (P_{TX} + P_{RX})$$

### Numerics: 1 MiB Relay (25 kHz, GMSK, Conv+RS)

| Parameter | Value |
|---|---|
| Raw payload | 1 MiB = 1,048,576 bytes |
| Compression ratio | 3× |
| Effective bytes | 349,525 bytes |
| Frames needed | $\lceil 349,525 / 45 \rceil = 7,768$ |
| Frame time (25 kHz, Conv+RS) | 46.8 ms |
| PER @ 1000 km | ~0.1% |
| Expected frames (ARQ) | 7,776 |
| **Total time** | **7,776 × 46.8 ms ≈ 364 s ≈ 6.1 min** |
| Tx energy | $364 × 10 = 3,640$ J = 1.01 Wh |
| Rx energy | $364 × 2.5 = 910$ J = 0.25 Wh |
| **Total energy** | **4,550 J ≈ 1.26 Wh** |
| Fits in 15-min LoS? | **YES** |

For 10 MiB relay:

| Config | Time | Total energy |
|---|---|---|
| 25 kHz GMSK Conv+RS | ~61 min | 12.6 Wh |
| 25 kHz BPSK Conv+RS | ~30 min | 6.26 Wh |

**Note:** 10 MiB does NOT fit in a single 15-minute LoS window without Ka-band. 1 MiB comfortably fits.

---

## Service-Level Energy Attribution

The "Protocol Message Energy" tab in the Streamlit app runs the C++ DLL and measures frame emissions per service type.

**Representative result — Correction scenario, 5 satellites:**

| Service | TX frames | Share of network energy |
|---|---|---|
| `CORRECTION_RSP` | 4–8 | ~72% |
| `CORRECTION_REQ` | 1 (broadcast) | ~9% |
| `HEARTBEAT` | periodic | ~12% |
| `FAILURE` | rare | <1% |
| `RELAY_*`, `BORROW_*` | on-demand | remainder |

**Key insight:** Correction responses dominate because each of $N$ neighbours must transmit a full 64-byte frame. This motivates the $N \leq 8$ cap in the spec.

**Daily energy breakdown (analytic mode, 24 corrections/day, 12 HB/hour):**

| Service | Frames/day | Energy (J) |
|---|---|---|
| CORRECTION_REQ | 24 | 22.5 |
| CORRECTION_RSP | 24 × 8 = 192 | 180 |
| HEARTBEAT | 288 | 27 |
| FAILURE | 0 | 0 |
| **Total** | 504 | **229 J ≈ 0.064 Wh** |

---

## Spacecraft Energy Budget

Typical CubeSat energy constraints:

| Item | Typical value |
|---|---|
| Battery capacity | 100 Wh |
| Daily energy generation | 300 Wh |
| Non-comms load | 200 Wh/day |
| **Available for comms** | **100 Wh/day** |

SISP correction overhead (24 events/day) at **0.064 Wh = 0.064% of daily generation** — negligible.

One 1 MiB relay at **1.26 Wh = 0.42% of daily generation** — affordable.

One 10 MiB relay at **12.6 Wh = 4.2% of daily generation** — significant; plan around LoS windows.

---

## Ground-Link vs ISL Comparison

For the same 1 MiB payload, UHF downlink to ground (437 MHz, 1200 km slant range, 20 dBi ground antenna):

| Metric | ISL (sat-to-sat) | Downlink (sat-to-ground) |
|---|---|---|
| Spacecraft Tx energy | 1.01 Wh | 0.91 Wh |
| Total time | 6.1 min | ~5.5 min |
| Availability | LoS to neighbour (~30–45 min/orbit) | Ground pass (~10–15 min/pass) |

**Conclusion:** The ISL path costs only marginally more energy than the ground downlink at the same frequency and power. The ISL advantage is **availability** — neighbours are visible far more often than ground stations, enabling more frequent corrections and emergency relays.

---

## Energy vs Neighbourhood Size Trade-off

As $N$ increases (more neighbours responding to a correction request):

$$E_{\text{snap}}(N) = (1 + N)(P_{TX} + P_{RX}) \cdot t_{\text{frame}}$$

| N | $t_{\text{snap}}$ | $E_{\text{snap}}$ | Correction quality gain |
|---|---|---|---|
| 1 | 186 ms | 2.4 J | minimal |
| 4 | 468 ms | 6.1 J | good |
| **8** | **849 ms** | **12.2 J** | **optimal** |
| 16 | 1,598 ms | 20.8 J | diminishing returns |

The recommended neighbourhood size is **N = 4–8**, balancing correction quality against energy cost and the 5-second timer constraint.
