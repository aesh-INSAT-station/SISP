# Energetic Study

**Source files:**
- `scripts/energy_audit.py` — canonical calculation source for paper numbers
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

**Frame time for each configuration (hardware-realistic GMSK bitrates):**

| Channel | Modulation | FEC | $R_b$ (bps) | $t_{\text{frame}}$ |
|---|---|---|---|---|
| 12.5 kHz CTRL | GMSK BT=0.3 | None | 9,600 | 53.3 ms |
| 12.5 kHz CTRL | GMSK BT=0.3 | Conv | 9,600 | 106.7 ms |
| 12.5 kHz CTRL | GMSK BT=0.3 | Conv+RS | 9,600 | **122.0 ms** |
| 25 kHz BULK | GMSK BT=0.3 | Conv+RS | 19,200 | **61.0 ms** |

---

## Correction Snapshot Energy

### Model

One correction cycle involves 1 requester and $N$ neighbours. Each sends one frame. The total on-air time is:

$$t_{\text{snap}} \approx (1 + N) \cdot t_{\text{frame}} + 2 \cdot t_{\text{prop}}$$

$$t_{\text{prop}} = \frac{d}{c} \approx 3.3\,\text{ms at 1000 km} \quad \text{(negligible vs. frame time)}$$

Network energy (both TX and RX sides):

$$E_{\text{snap}} = \underbrace{P_{TX} \cdot t_{\text{frame}}}_{\text{requester TX}} + \underbrace{N \cdot P_{RX} \cdot t_{\text{frame}}}_{\text{neighbours RX}} + \underbrace{N \cdot P_{TX} \cdot t_{\text{frame}}}_{\text{neighbours TX}} + \underbrace{P_{RX} \cdot N \cdot t_{\text{frame}}}_{\text{requester RX}}$$

Simplified for $N$ symmetric neighbours:

$$E_{\text{network}} \approx \left((1+N)P_{TX} + 2NP_{RX}\right)t_{\text{frame}}$$

The requester-only battery cost is:

$$E_{\text{requester}} \approx \left(P_{TX} + NP_{RX}\right)t_{\text{frame}}$$

### Numerics (N=8, Conv+RS, 12.5 kHz, 9600 bps)

| Item | Value |
|---|---|
| Frame time | 122.0 ms |
| Total on-air time | $9 \times 122.0 + 6.7 \approx 1.10$ s |
| Within 5-second timer? | **YES** (1.10 s << 5000 ms) |
| Requester TX energy | $10 \times 0.1220 = 1.22$ J |
| Requester RX energy | $2.5 \times 8 \times 0.1220 = 2.44$ J |
| **Requester battery** | **3.66 J per correction event** |
| Neighbours TX energy | $8 \times 10 \times 0.1220 = 9.76$ J |
| Neighbours RX energy | $8 \times 2.5 \times 0.1220 = 2.44$ J |
| **Network total** | **15.86 J per correction event** |

At 24 corrections per day:

Requester battery:

$$E_{\text{daily,corr,requester}} = 24 \times 3.66 \approx 87.8\,\text{J} \approx 0.0244\,\text{Wh}$$

Network total:

$$E_{\text{daily,corr,network}} = 24 \times 15.86 \approx 380.6\,\text{J} \approx 0.106\,\text{Wh}$$

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

### Numerics: 1 MiB Relay (25 kHz, GMSK, Conv+RS, 19,200 bps)

| Parameter | Value |
|---|---|
| Raw payload | 1 MiB = 1,048,576 bytes |
| Compression ratio | 3× |
| Effective bytes | 349,525 bytes |
| Frames needed | $\lceil 349,525 / 45 \rceil = 7,768$ |
| Frame time (25 kHz, Conv+RS) | 61.0 ms |
| PER @ 1000 km | ~0.1% |
| Expected frames (ARQ) | 7,775.8 |
| **Total time** | **7,775.8 × 61.0 ms = 474.3 s = 7.91 min** |
| Tx energy | $474.3 \times 10 = 4,743$ J = 1.32 Wh |
| Rx energy | $474.3 \times 2.5 = 1,186$ J = 0.33 Wh |
| **Total energy** | **5,929 J = 1.65 Wh** |
| Fits in 15-min LoS? | **YES** |

For 10 MiB relay (still 19,200 bps):

| Config | Time | Total energy |
|---|---|---|
| 25 kHz GMSK Conv+RS | ~79.1 min | 16.5 Wh |

**Note:** 10 MiB does NOT fit in a single 15-minute LoS window at 19.2 kbps; Ka-band or higher-rate SDR modes would be required.

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

**Daily single-satellite operating tempo (analytic mode):**

Assumptions: 24 correction cycles initiated per day, 8 responding neighbours, and 12 heartbeat broadcasts/hour (one every 5 minutes). The correction row reports the initiating satellite's battery cost; the network total for those same correction events is 380.6 J = 0.106 Wh.

| Activity | Frames/day seen by one satellite | Battery energy |
|---|---:|---:|
| Correction initiator | 24 TX + 192 RX | 87.8 J = 0.0244 Wh |
| Own heartbeat TX | 288 TX | 351.4 J = 0.0976 Wh |
| Neighbour heartbeat RX | 2,304 RX | 702.7 J = 0.1952 Wh |
| Failure | 0 | 0 |
| **Total, no relay** | 2,808 TX/RX frame actions | **1,141.9 J = 0.317 Wh** |

---

## Spacecraft Energy Budget

Typical CubeSat energy constraints:

| Item | Typical value |
|---|---|
| Battery capacity | 100 Wh |
| Daily energy generation | 300 Wh |
| Non-comms load | 200 Wh/day |
| **Available for comms** | **100 Wh/day** |

SISP correction initiator overhead (24 events/day) at **0.0244 Wh = 0.0081% of daily generation** is negligible.

Heartbeat maintenance with 8 neighbours and 12 heartbeats/hour at **0.293 Wh/day = 0.098% of daily generation** is also small.

One 1 MiB relay at **1.65 Wh = 0.55% of daily generation** is affordable.

One 10 MiB relay at **16.5 Wh = 5.5% of daily generation** is significant; plan around LoS windows.

---

## Ground-Link vs ISL Comparison

For the same 1 MiB payload, UHF downlink to ground (437 MHz, 1200 km slant range, 20 dBi ground antenna):

| Metric | ISL (sat-to-sat) | Downlink (sat-to-ground) |
|---|---|---|
| Spacecraft Tx energy | 1.32 Wh | 1.32 Wh |
| Total time | 7.91 min | ~7.91 min |
| Availability | LoS to neighbour (~30–45 min/orbit) | Ground pass (~10–15 min/pass) |

**Conclusion:** The ISL path costs only marginally more energy than the ground downlink at the same frequency and power. The ISL advantage is **availability** — neighbours are visible far more often than ground stations, enabling more frequent corrections and emergency relays.

---

## Energy vs Neighbourhood Size Trade-off

As $N$ increases (more neighbours responding to a correction request):

$$E_{\text{network}}(N) = \left((1+N)P_{TX} + 2NP_{RX}\right)t_{\text{frame}}$$

| N | $t_{\text{snap}}$ | $E_{\text{snap}}$ | Correction quality gain |
|---|---|---|---|
| 1 | 252 ms | 3.05 J | minimal |
| 4 | 619 ms | 8.54 J | good |
| **8** | **1.10 s** | **15.86 J** | **optimal** |
| 16 | 2.09 s | 30.50 J | diminishing returns |

The recommended neighbourhood size is **N = 4–8**, balancing correction quality against energy cost and the 5-second timer constraint.