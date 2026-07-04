
# SISP: A Satellite Inter-Service Protocol with Distributed Sensor Correction, Anomaly Detection, and Dual-Frequency UHF Physical Layer

**Authors:** SISP Team — AESH 2026 Hackathon  
**Date:** May 2026  
**Keywords:** Inter-satellite link, state machine, time‑lagged SVD anomaly detection, Kalman correction, UHF 437 MHz, dual‑PHY, energy budget

---

## Abstract

We present SISP (Satellite Inter-Service Protocol), a lightweight protocol stack for autonomous cooperative behaviour in CubeSat constellations. SISP provides three core services—sensor correction, data relay, and sensor borrowing—governed by a deterministic finite‑state machine implemented in C++. Sensor corrections are computed by a pluggable filter layer offering weighted‑median, Kalman, and hybrid algorithms. Anomalous telemetry is pre‑screened using an on‑board time‑lagged SVD detector before correction decisions are made, preventing corrupted readings from polluting the distributed estimate. The physical layer targets the 435–438 MHz amateur satellite band with a dual‑profile approach: a 12.5 kHz always‑on control channel (GMSK BT=0.3, 9600 bps) and a 25 kHz emergency bulk channel (GMSK, 19 200 bps). Rigorous link budget, BER, and PER models—validated by Monte Carlo simulation—confirm feasibility across the full LEO neighbour visibility range. Experimental results from 273 C++ unit tests and ten Python integration scenarios demonstrate: **94.3 % RMSE improvement** over 30‑day correction cycles, **85.6 % error reduction** under 10 % packet loss, and **bulk transfer of 1 MiB within 7.9 min at 1.65 Wh** total link energy. The protocol overhead is negligible: a full correction round with 8 neighbours takes **~1.10 s**, costs **3.66 J** on the requesting satellite, and a no‑relay daily operating tempo consumes **~0.26 % of a 5 W onboard energy budget**.

---

## 1. Introduction

Small satellite constellations face a fundamental tradeoff between autonomy and communication cost. Ground operators cannot respond quickly to on‑orbit faults; yet inter‑satellite radio links are constrained in bandwidth, duty cycle, and energy. SISP addresses this by distributing sensor correction, relay, and borrowing tasks among neighbours within a single, coherent protocol.

The protocol design goals are:
- **Autonomy.** A satellite with a degraded sensor can independently request and apply a correction from healthy neighbours within a 5‑second window.
- **Energy efficiency.** All protocol messages fit in a fixed 64‑byte frame. The physical layer uses GMSK, the cheapest practical modulation, on a globally available spectrum allocation (437 MHz).
- **Fault isolation.** One satellite’s failure must never cascade. The state machine explicitly records but does not propagate critical failures.
- **Correctness.** All algorithm correctness claims are backed by reproducible Monte Carlo tests and 273 automated unit tests.

---

## 2. State Machine Architecture

### 2.1 Design Rationale

SISP’s state machine is the single source of truth for all on‑board protocol behaviour. It is implemented as a static 21×24 transition table in C++, initialized once and then read‑only, eliminating dynamic dispatch overhead and enabling deterministic timing on embedded RTOS targets.

Every satellite runs one state machine context (`SISP::Context`). The context stores all per‑session state: current state, peer ID, timer deadline, correction response buffer (up to 8 neighbours × 3‑axis readings), relay fragment buffer, and neighbour trust tables. The context is 2 KB on‑heap and holds no pointers to heap‑allocated data except the optional correction filter plugin.

### 2.2 States

Twenty‑one states cover all service flows plus error conditions.

| Group | States |
|---|---|
| Idle | `IDLE` |
| Correction requester | `CORR_WAIT_RSP` → `CORR_COLLECTING` → `CORR_COMPUTING` → `CORR_DONE` |
| Correction responder | `CORR_RESPONDING` |
| Relay sender | `RELAY_WAIT_ACCEPT` → `RELAY_SENDING` → `RELAY_WAIT_ACK` → `RELAY_DONE` |
| Relay provider | `RELAY_RECEIVING` → `RELAY_STORING` → `RELAY_DOWNLINKING` |
| Borrow requester | `BORROW_WAIT_ACCEPT` → `BORROW_RECEIVING` → `BORROW_DONE` |
| Borrow provider | `BORROW_SAMPLING` → `BORROW_SENDING` |
| Failure | `TIMEOUT`, `ERROR`, `CRITICAL_FAIL` |

### 2.3 Events

Twenty‑four events drive all transitions.

- **Packet‑received events** (`RX_CORRECTION_REQ`, `RX_RELAY_REQ`, …) are injected by the decoder when a valid frame arrives.
- **Internal/timer events** (`FAULT_DETECTED = 12`, `ENERGY_LOW = 14`, `CRITICAL_FAILURE = 21`, `TIMER_EXPIRED = 13`, …) are injected by the sensor layer or the RTOS tick handler.

The event codes are fixed integer values matching the `SISP::Event` enum. All Python harnesses must use these exact values.

### 2.4 Key Transitions and Actions

| State / Event | Next State | Action |
|---|---|---|
| `IDLE + FAULT_DETECTED` | `CORR_WAIT_RSP` | broadcast `CORRECTION_REQ`, set 5 s timer |
| `IDLE + RX_CORRECTION_REQ` | `CORR_RESPONDING` | unicast `CORRECTION_RSP` with own reading |
| `CORR_WAIT_RSP + RX_RSP` | `CORR_COLLECTING` | buffer reading + DEGR weight |
| `CORR_COLLECTING + TIMER` | `CORR_COMPUTING` | run configured correction filter |
| `IDLE + ENERGY_LOW` | `RELAY_WAIT_ACCEPT` | broadcast `RELAY_REQ`, set 10 s timer |
| `RELAY_WAIT_ACCEPT + ACCEPT` | `RELAY_SENDING` | fragment payload, unicast `DOWNLINK_DATA` |
| `ANY + CRITICAL_FAILURE` | `CRITICAL_FAIL` | set DEGR=15, broadcast `FAILURE` |
| `ANY_STATE + RX_FAILURE` | `(same state)` | record foreign failure, do NOT cascade |
| `ANY_STATE + RESET` | `IDLE` | clear context, preserve `self_id` |

### 2.5 Dual‑PHY Selection

The `select_tx_phy()` function in the state machine selects between two 437 MHz profiles per frame:

- **`CONTROL_437_NARROW` (0x00):** 12.5 kHz channel, always‑on. Used for all control messages: `CORRECTION_REQ/RSP`, `RELAY_REQ/ACCEPT/REJECT`, `FAILURE`, `HEARTBEAT`, `BORROW_REQ/DECISION`.
- **`BULK_437_WIDE` (0x01):** 25 kHz channel. Used for `DOWNLINK_DATA` and `DOWNLINK_ACK` only, **after** the relay/borrow handshake confirms both peers are ready to switch.

The PHY profile byte (frame byte 8) serves as a confirmation, not as the primary switching trigger. Test results confirm 100 % correct PHY selection across all service types (Section 7.1).

### 2.6 Failure Isolation

A critical design constraint is that observing a neighbour’s failure must not cascade. The transition table maps `RX_FAILURE` to a *self‑loop* action on every state. The action records the failed satellite’s ID and clears its trust entry but does **not** invoke `CRITICAL_FAILURE`. This was validated in integration test IT‑02.

### 2.7 Frame Format

All frames are fixed 64 bytes. The 5‑byte packed header encodes:

```
Byte 0: [ SVC[3:0] (high nibble) | SNDR[7:4] (low nibble) ]
Byte 1: [ SNDR[3:0]              | RCVR[7:4]              ]
Byte 2: [ RCVR[3:0]              | SEQ[7:4]               ]
Byte 3: [ SEQ[3:0]               | DEGR[3:0]              ]
Byte 4: [ FLAGS[3:0]             | CKSM[3:0]              ]
```

The transport extension (bytes 5–N) carries the PHY profile (byte 8), a **constellation group identifier** (byte 6) for basic isolation between operators, and session/datagram metadata. Frames with an unrecognized group ID are silently dropped. The last byte is a full‑frame CRC‑8/MAXIM checksum.

## 3. On‑Board Anomaly Detection via Time‑Lagged SVD

### 3.1 Motivation

Sensor correction is only meaningful when the input readings are plausible. Before injecting a neighbour’s response into the Kalman filter, SISP screens it using an on‑board anomaly detector that runs on the raw sensor time series. This prevents corrupted or adversarial readings from biasing the distributed estimate.

### 3.2 Time‑Lagged SVD Detector

Each satellite maintains a sliding window of the last \(W\) scalar readings from a single sensor channel. The window is embedded into a Hankel matrix \(H \in \mathbb{R}^{m \times n}\) (typical size \(m=n \approx 50\)). The SVD of \(H = U\Sigma V^\top\) is computed, and the ratio of the off‑diagonal singular value energy to the total energy,

\[
\rho = \frac{\sum_{i=2}^{\min(m,n)} \sigma_i}{\sum_{i} \sigma_i},
\]

is tracked over time. Under nominal operation the singular spectrum is dominated by a few large singular values and \(\rho\) remains small. A sudden increase in \(\rho\) indicates a structural break in the time series (e.g., sensor drift, stuck value, or noise burst), triggering the `FAULT_DETECTED` event.

The detector is lightweight: for typical window sizes the SVD can be updated efficiently using a rank‑1 update, and the threshold \(\tau_\rho\) is set once from historical nominal segments.

### 3.3 Validation on OPS‑SAT Telemetry

As a feasibility study, we trained a static per‑channel SVD model on the OPSSAT‑AD benchmark~\cite{opssat_ad}, which provides 2 123 expert‑labelled telemetry segments. The static model used 19 aggregate features and a 95 %‑percentile reconstruction‑error threshold, achieving ROC‑AUC up to 0.99. While the on‑board method uses the time‑lagged approach, the static study confirms that the nominal sensor behaviour is tightly bounded and that SVD‑based detection is effective. Details of the static validation are omitted here for brevity; the focus of the on‑board implementation is the sliding‑window Hankel‑SVD described above.

---

## 4. Correction Algorithms

### 4.1 Architecture: Pluggable Filter Interface

The correction layer is fully decoupled from the protocol. All filters implement:

```cpp
class CorrectionFilter {
public:
    virtual bool apply(const CorrectionInput& in, CorrectionOutput& out) = 0;
};
```

`CorrectionInput` carries up to 8 neighbour readings (`Vec3Reading`: x, y, z, timestamp_ms) and their DEGR‑derived weights. `CorrectionOutput` carries the corrected vector and a confidence score. The filter can be set, replaced, or cleared at runtime.

### 4.2 DEGR Weighting

The neighbour degradation score DEGR ∈ [0, 15] is derived from four telemetry sources: Kalman K‑factor deviation (max 5), SVD residual (max 5), mission age (max 3), and ADCS orbit error (max 2). The weight assigned to satellite \(i\) is

\[
w_i = \max(0.05,\; 1 - \mathrm{DEGR}_i / 15).
\]

A healthy satellite (DEGR = 0) has weight 1.0; a near‑failed satellite (DEGR = 14) has weight 0.067. Inverse‑error weighting improves steady‑state error by 17.8 % over neutral weighting in our tests.

### 4.3 Algorithms

Three correction filters are implemented:
- **Weighted Median:** computes each axis independently by sorting readings and accumulating DEGR weights until 50 % is reached. Breakdown point 50 %, but can amplify noise at high levels.
- **Kalman Filter:** a 6‑state EKF tracking position and velocity. Fuses neighbour readings via DEGR‑weighted measurement and inflates measurement noise when the neighbourhood is degraded. Optimal for Gaussian noise.
- **Hybrid Filter:** chains weighted median (robust pre‑processing) followed by Kalman (temporal smoothing). Recommended for mixed‑quality neighbourhoods.

Detailed performance is reported in Section 7.2.

---

## 5. Physical Layer Analysis

### 5.1 Frequency Selection and Channelization

SISP targets the **435–438 MHz** amateur satellite allocation. Two profiles are defined:
- **`CONTROL_437_NARROW`**: 12.5 kHz bandwidth, GMSK BT=0.3, **9 600 bps** (0.768 b/s/Hz).
- **`BULK_437_WIDE`**: 25 kHz bandwidth, GMSK BT=0.3, **19 200 bps**.

These bitrates are directly supported by flight‑proven COTS UHF transceivers (AAC Pulsar‑UTRX, EnduroSat UHF Transceiver), avoiding the need for an SDR or custom modem.

### 5.2 GMSK BER Model

The GMSK BT=0.3 bit error probability follows Murota & Hirade~\cite{murota_hirade}:

\[
P_b^{\text{GMSK}} = \frac{1}{2}\operatorname{erfc}\!\left(\sqrt{\alpha_{BT} \cdot E_b/N_0}\right),\quad \alpha_{BT}=0.68,
\]

giving a 1.67 dB penalty versus BPSK.

### 5.3 Forward Error Correction

Two concatenated codes are used:
- Convolutional code K=7, R=1/2 (soft‑decision Viterbi). Post‑decoding BER is bounded by the Heller‑Jacobs union bound: \(P_b^{\text{CONV}} \leq 36\,Q(\sqrt{10\,E_b/N_0})\).
- Reed‑Solomon RS(255,223), \(t=16\). Byte error probability and decode failure are modelled via a binomial tail.

The combined coding expansion is 2.287×.

### 5.4 Link Budget

Free‑space path loss at 437 MHz and 1000 km is 145.2 dB. System noise temperature is \(T_{sys} \approx 1130\) K (NF = 5 dB, omnidirectional antenna). For the control channel (12.5 kHz, 9.6 kbps):

\[
\frac{E_b}{N_0} = P_{tx} + G_t + G_r - L_{fs} - L_{misc} - L_{\text{Doppler}} - 10\log_{10}(k T_{sys} B) + 10\log_{10}\!\left(\frac{B}{R_b}\right).
\]

With \(P_{tx}=30\) dBm, \(G_t=G_r=2\) dBi, \(L_{misc}=3\) dB, \(L_{\text{Doppler}}=1.5\) dB (Doppler shift ≈10.9 kHz), we obtain \(E_b/N_0 \approx 9.9\) dB. The margin over the ~5.5 dB required for PER ≤ 1 % (Conv+RS) is **~4.4 dB**. The bulk channel at 19.2 kbps enjoys the same \(B/R_b\) ratio, hence identical margin. Maximum usable range exceeds 2 800 km; geometry, not link budget, limits neighbourhood size.

### 5.5 PER and Frame Timing

For a 64‑byte frame (512 info bits), air bits after coding: \(512 \times 2.287 = 1\,171\) bits.
- **Control frame time:** \(1\,171 / 9\,600 = 122.0\) ms.
- **Bulk frame time:** \(1\,171 / 19\,200 = 61.0\) ms.

PER at 1000 km with the above margin is ~0.1 %. Monte Carlo validation confirms BPSK theoretical BER to within 0.4 % relative error at all tested Eb/N0 values.

---

## 6. Energetic Analysis

### 6.1 Frame‑Level Energy Model

Transmission energy: \(E_{TX} = P_{TX,DC} \cdot t_{\text{frame}}\), reception energy: \(E_{RX} = P_{RX,DC} \cdot t_{\text{frame}}\), with \(P_{TX,DC}=10\) W, \(P_{RX,DC}=2.5\) W. All values below are generated by `scripts/energy_audit.py`.

### 6.2 Correction Snapshot

For \(N=8\) neighbours at 1000 km:
\[
t_{\text{snap}} = 9 \times 122.0\ \text{ms} + 2 \times 3.3\ \text{ms} \approx 1.10\ \text{s} \ll 5\ \text{s}.
\]

Requester battery per event: \((10 + 8 \times 2.5) \times 0.122 = 3.66\) J.
Network total: \(((1+8)\times10 + 2\times8\times2.5) \times 0.122 = 15.86\) J.

At 24 requester‑initiated corrections/day, the requester’s battery spends \(24 \times 3.66 = 87.8\) J = 0.0244 Wh. The network total for those events is \(24 \times 15.86 = 380.6\) J = 0.106 Wh.

### 6.3 Bulk Relay

1 MiB payload, 3× compression, 45 B payload/frame → 7 768 frames. With ARQ at PER = 0.1 %, expected transmissions: 7 775.8 frames.

\[
t_{\text{bulk}} = 7\,775.8 \times 0.0610\ \text{s} = 474.3\ \text{s} = 7.91\ \text{min}.
\]

Sender TX energy: \(474.3 \times 10 = 4\,743\) J = 1.32 Wh.
Receiver RX: \(474.3 \times 2.5 = 1\,186\) J = 0.33 Wh.
**Link total: 5 929 J = 1.65 Wh**, about 0.55 % of a 300 Wh daily generation.

### 6.4 Daily Protocol Operating Tempo

With 24 correction initiations/day, 12 heartbeat broadcasts/hour (288 TX, 2 304 RX frames/day), the total no‑relay energy for one satellite is:

\[
E_{\text{day}} = 24 \times 3.66\ \text{J} + (288 \times 10 + 2\,304 \times 2.5) \times 0.122\ \text{s} = 87.8\ \text{J} + 1\,051.2\ \text{J} = 1\,139\ \text{J} \approx 0.316\ \text{Wh}.
\]

This represents **0.26 %** of a 5 W continuous onboard power budget (120 Wh/day), and an even smaller fraction of a typical CubeSat’s 300 Wh/day generation.

---

## 7. Results and Evaluation

### 7.1 Dual‑PHY Correctness

Eight assertions confirm that control frames use only the 12.5 kHz channel and bulk frames use only the 25 kHz channel, with zero violations.

### 7.2 Correction Algorithm Performance

In a 30‑day systematic‑drift test (IT‑05), Kalman correction reduces RMSE from 8.909 to 0.504 (**94.3 %** improvement). Under 10 % packet loss (IT‑06), corrected RMSE is 1.197 vs. raw 8.290 (**85.6 %** improvement). The hybrid filter is the best overall in mixed fault regimes. DEGR‑weighting provides a 17.8 % additional gain over neutral weights.

### 7.3 Monte Carlo BER Validation

500 000‑bit BPSK simulation matches theoretical BER within 5 % relative error at all tested Eb/N0 values.

### 7.4 C++ Unit Test Coverage

All 273 unit tests pass: encoder/decoder (70), payload codec (65), frame pipeline (21), state machine (38 + 34 matrix), DEGR (20), protocol simulation (25).

---

## 8. Limitations and Future Work

- **Security:** Currently a static constellation group identifier provides basic isolation; future work will add cryptographic authentication.
- **Borrowing for imaging:** The current borrow service transfers generic 3‑axis vectors; extension to imaging payloads (with attitude, calibration, and exposure metadata) is planned.
- **Interference simulation:** The PHY model includes Doppler and AWGN, but adjacent‑channel interference and multipath will be added in a future release.
- **Hardware‑in‑the‑loop:** On‑orbit validation with a real UHF transceiver is needed to confirm BER/PER behaviour.

---

## 9. Impact and Conclusion

SISP demonstrates that a small, deterministic protocol stack can provide meaningful distributed sensor correction in a CubeSat constellation using commodity UHF hardware. The on‑board time‑lagged SVD detector, DEGR‑weighted correction filters, and hardware‑realistic GMSK dual‑PHY link enable autonomous extension of satellite mission life with negligible energy overhead (0.26 % of a 5 W continuous budget). All key performance claims are backed by reproducible simulation and 273 unit tests. SISP fills the integrator gap left by DARPA F6 and the decentralized collaboration layer identified as open by the 2024 DSIN survey, in a form small enough to run on existing COTS hardware.

---

## References

1. Murota, K., & Hirade, K. (1981). GMSK modulation for digital mobile radio telephony. *IEEE Trans. Commun.*, 29(7), 1044–1050.
2. OPSSAT-AD Dataset. Zenodo record 12588359.
```