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

$$E_{\text{network}} \approx \left((1+N)P_{TX} + 2NP_{RX}\right)t_{\text{frame}}$$

The requester-only battery cost is:

$$E_{\text{requester}} \approx \left(P_{TX} + NP_{RX}\right)t_{\text{frame}}$$

### Numerics (N=8, Conv+RS, 12.5 kHz)

| Item | Value |
|---|---|
| Frame time | 93.68 ms |
| Total on-air time | $9 \times 93.68 + 6.7 \approx 850$ ms |
| Within 5-second timer? | **YES** (850 ms << 5000 ms) |
| Requester TX energy | $10 \times 0.09368 = 0.937$ J |
| Requester RX energy | $2.5 \times 8 \times 0.09368 = 1.87$ J |
| **Requester battery** | **2.81 J per correction event** |
| Neighbours TX energy | $8 \times 10 \times 0.09368 = 7.49$ J |
| Neighbours RX energy | $8 \times 2.5 \times 0.09368 = 1.87$ J |
| **Network total** | **12.18 J per correction event** |

At 24 corrections per day:

Requester battery:

$$E_{\text{daily,corr,requester}} = 24 \times 2.81 \approx 67.4\,\text{J} \approx 0.0187\,\text{Wh}$$

Network total:

$$E_{\text{daily,corr,network}} = 24 \times 12.18 \approx 292\,\text{J} \approx 0.0812\,\text{Wh}$$

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
| Frame time (25 kHz, Conv+RS) | 46.84 ms |
| PER @ 1000 km | ~0.1% |
| Expected frames (ARQ) | 7,775.8 |
| **Total time** | **7,775.8 x 46.84 ms = 364.2 s = 6.07 min** |
| Tx energy | $364.2 \times 10 = 3,642$ J = 1.012 Wh |
| Rx energy | $364.2 \times 2.5 = 910.5$ J = 0.253 Wh |
| **Total energy** | **4,552 J = 1.265 Wh** |
| Fits in 15-min LoS? | **YES** |

For 10 MiB relay:

| Config | Time | Total energy |
|---|---|---|
| 25 kHz GMSK Conv+RS | ~60.7 min | 12.65 Wh |
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

**Daily single-satellite operating tempo (analytic mode):**

Assumptions: 24 correction cycles initiated per day, 8 responding neighbours, and 12 heartbeat broadcasts/hour (one every 5 minutes). The correction row reports the initiating satellite's battery cost; the network total for those same correction events is 292 J = 0.0812 Wh.

| Activity | Frames/day seen by one satellite | Battery energy |
|---|---:|---:|
| Correction initiator | 24 TX + 192 RX | 67.4 J = 0.0187 Wh |
| Own heartbeat TX | 288 TX | 269.8 J = 0.0749 Wh |
| Neighbour heartbeat RX | 2,304 RX | 539.6 J = 0.1499 Wh |
| Failure | 0 | 0 |
| **Total, no relay** | 2,808 TX/RX frame actions | **876.8 J = 0.2436 Wh** |

---

## Spacecraft Energy Budget

Typical CubeSat energy constraints:

| Item | Typical value |
|---|---|
| Battery capacity | 100 Wh |
| Daily energy generation | 300 Wh |
| Non-comms load | 200 Wh/day |
| **Available for comms** | **100 Wh/day** |

SISP correction initiator overhead (24 events/day) at **0.0187 Wh = 0.0062% of daily generation** is negligible.

Heartbeat maintenance with 8 neighbours and 12 heartbeats/hour at **0.2248 Wh/day = 0.075% of daily generation** is also small.

One 1 MiB relay at **1.265 Wh = 0.42% of daily generation** is affordable.

One 10 MiB relay at **12.65 Wh = 4.2% of daily generation** is significant; plan around LoS windows.

---

## Ground-Link vs ISL Comparison

For the same 1 MiB payload, UHF downlink to ground (437 MHz, 1200 km slant range, 20 dBi ground antenna):

| Metric | ISL (sat-to-sat) | Downlink (sat-to-ground) |
|---|---|---|
| Spacecraft Tx energy | 1.012 Wh | 1.012 Wh |
| Total time | 6.07 min | ~6.07 min |
| Availability | LoS to neighbour (~30–45 min/orbit) | Ground pass (~10–15 min/pass) |

**Conclusion:** The ISL path costs only marginally more energy than the ground downlink at the same frequency and power. The ISL advantage is **availability** — neighbours are visible far more often than ground stations, enabling more frequent corrections and emergency relays.

---

## Energy vs Neighbourhood Size Trade-off

As $N$ increases (more neighbours responding to a correction request):

$$E_{\text{network}}(N) = \left((1+N)P_{TX} + 2NP_{RX}\right)t_{\text{frame}}$$

| N | $t_{\text{snap}}$ | $E_{\text{snap}}$ | Correction quality gain |
|---|---|---|---|
| 1 | 194 ms | 2.34 J | minimal |
| 4 | 475 ms | 6.56 J | good |
| **8** | **850 ms** | **12.18 J** | **optimal** |
| 16 | 1,599 ms | 23.42 J | diminishing returns |

The recommended neighbourhood size is **N = 4–8**, balancing correction quality against energy cost and the 5-second timer constraint.
