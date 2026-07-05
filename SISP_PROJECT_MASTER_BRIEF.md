# SISP Project Master Brief

## Executive Summary

SISP, the Satellite Inter-Service Protocol, is a cooperative, autonomous, self-healing protocol stack for CubeSat and smallsat constellations. It gives satellites the ability to correct degraded sensors, relay mission data across visibility gaps, and temporarily borrow healthy sensor readings from neighbouring spacecraft without waiting for ground intervention.

The central idea is simple and powerful: a satellite constellation should not behave like isolated hardware units. It should behave like a resilient network. When one node loses trust in its own sensor, another node can help. When one node misses a ground pass, another can relay. When one node becomes degraded, the rest of the constellation can know, adapt, and continue operating without cascading failure.

SISP turns that operating model into a tested technical system. The repository contains a deterministic C++ protocol implementation, fixed 64-byte frame encoding, a 21-state and 24-event finite state machine, pluggable correction filters, DEGR trust scoring, OPSSAT-AD SVD anomaly detection, 437 MHz UHF signal and link-budget models, Streamlit simulation dashboards, energy analysis, sustainability KPIs, and automated C++ and Python validation suites.

The strongest measured results are:

| Result | Evidence |
|---|---:|
| C++ protocol tests | 273/273 passing |
| Long-term correction quality | 94.3% RMSE improvement in the 30-day IT-05 scenario |
| Packet-loss resilience | 85.6% RMSE improvement under 10% packet loss |
| Dual-PHY validation | 8/8 assertions passing |
| Relay recovery | 109/109 bytes recovered through corruption, reordering, and replay |
| Runtime | 500 correction rounds in about 0.004 s, about 0.009 ms per round |
| Failure isolation | Healthy nodes record failed peers without cascading into critical failure |

SISP is best positioned today as a validated prototype and research-grade mission-assurance stack. It is not yet flight-qualified software, but it has already crossed the line from concept into implemented, simulated, measured, and testable engineering.

## One-Line Pitch

SISP is a lightweight autonomous protocol that lets CubeSat constellations self-correct sensor faults, relay mission data, and borrow healthy sensor readings through low-power inter-satellite links.

## The Problem

Small satellites are affordable and flexible, but they remain fragile in orbit. A single failed or drifting sensor can reduce mission quality. A missed ground-station pass can delay or lose mission data. A power constraint can force a satellite to choose between communication and survival. For many CubeSat missions, there is not enough mass, power, or budget to solve every risk with duplicated hardware.

The current operating model is too often ground-centric and satellite-isolated:

| Problem | Operational Consequence |
|---|---|
| Sparse ground-station visibility | Data can wait up to an orbital cycle before reaching operators |
| Sensor drift or failure | The satellite may keep producing poor data or become mission-limited |
| Limited onboard redundancy | Hardware failures are hard to mask in small spacecraft |
| High replacement cost | Premature failure forces new builds, launches, and operational overhead |
| No constellation-level trust fabric | One failed node can pollute decisions unless faults are isolated |

This is a structural weakness. In a constellation, one satellite's weakness should not automatically become mission failure. The network should be able to share sensing, communication opportunity, and operational trust.

## The SISP Insight

SISP treats cooperation as a protocol service.

Instead of relying only on ground commands or onboard duplicate sensors, SISP lets satellites request help from nearby satellites using bounded, deterministic service flows. It turns neighbour satellites into a software-defined redundancy layer.

The insight is that the constellation already has distributed assets:

- Multiple sensors observing related environments.
- Multiple communication windows.
- Multiple power states.
- Multiple health states.
- Multiple paths to the ground.

SISP gives those assets a common language and a safe control structure.

## Core Services

SISP defines three primary autonomous services.

| Service | Trigger | What Happens | Mission Value |
|---|---|---|---|
| Correction | Local sensor fault or degraded reading | The satellite broadcasts a correction request, receives neighbour readings, weights them by trust, filters suspicious inputs, and computes a corrected estimate | Keeps degraded satellites useful |
| Relay | Ground-station loss, low energy, or visibility gap | The satellite negotiates with a neighbour, fragments payloads, transfers data, and receives acknowledgement | Reduces missed-contact and latency risk |
| Borrow | Local sensor unavailable or temporary need for another sensor | The satellite requests a healthy neighbour sensor stream and receives data from an accepted provider | Converts hardware redundancy into a network service |

These services are supported by heartbeat, status, failure, acknowledgement, and payload messages inside a compact binary protocol.

## Product Vision

SISP can become a mission-assurance layer for small satellite constellations. It can be delivered as:

| Product Form | Audience | Value |
|---|---|---|
| Embedded protocol SDK | CubeSat operators and flight-software teams | Add cooperative autonomy to onboard software |
| Mission simulation toolkit | Mission designers, universities, integrators | Test correction, relay, energy, and link feasibility before launch |
| Resilience dashboard | Operators, investors, insurers, agencies | Translate technical resilience into mission, financial, and sustainability impact |
| Research and education platform | Universities and labs | Study distributed satellite autonomy with real protocol and telemetry tooling |

The long-term vision is a standard cooperative service layer for small spacecraft, starting with correction, relay, and borrowing, then expanding toward authenticated trust, scheduling, routing, hardware-in-the-loop validation, and flight demonstration.

## Technical Architecture

SISP is built as a layered system.

| Layer | Role | Implementation Evidence |
|---|---|---|
| Service layer | Correction, relay, borrow, heartbeat, status, failure | C++ finite state machine |
| Protocol layer | 64-byte frames, service codes, payloads, CRC | C++ encoder and decoder |
| Trust layer | DEGR health score and response weighting | C++ protocol and correction logic |
| Correction layer | Weighted median, Kalman, hybrid filters | C++ pluggable filter interface |
| Anomaly layer | Per-channel SVD reconstruction-error detection | Python pipeline using OPSSAT-AD data |
| PHY model | 437 MHz UHF narrow control and wider bulk profiles | Python simulation and dual-PHY tests |
| Energy model | Frame-level timing and power accounting | Streamlit simulation and energy docs |
| Impact layer | Replacement, launch mass, CO2, and cost models | KPI dashboard and snapshot |

This is not one algorithm pretending to be a system. It is a system: protocol, state logic, message encoding, correction math, telemetry anomaly detection, signal physics, energy accounting, and impact modelling.

## Repository Assets

| Path | Purpose |
|---|---|
| `c++ implemnetation/include/` | Public protocol, state machine, correction, encoder, decoder, and simulation hook headers |
| `c++ implemnetation/src/` | Core C++ implementations |
| `c++ implemnetation/tests/` | C++ unit and integration tests |
| `all_tests/` | Python integration scenarios for correction, relay, borrow, packet loss, dual-PHY, failure isolation, and scale testing |
| `sisp/` | Modular Python package for ingestion, preprocessing, anomaly detection, and evaluation |
| `pipelines/` | Thin orchestration scripts for ingest, preprocess, and SVD detection |
| `simulation for signal and physics/` | Streamlit apps and studies for geometry, BER/PER, energy, dual-PHY, and sustainability |
| `docs/` | Architecture, state machine, SVD, correction, signal physics, energy, test results, KPI snapshot, pitch, and research paper |
| `data/raw/` | OPSSAT-AD telemetry dataset artifacts |

## Deterministic Embedded State Machine

The protocol core is governed by a deterministic finite state machine with 21 states and 24 events. It uses a static pre-allocated transition table:

```text
g_trans[STATE_COUNT][EVT_COUNT]
```

This design is important for embedded flight software:

- No heap allocation during operation.
- O(1) transition dispatch.
- Bounded action functions.
- Predictable timer behaviour.
- Clear reset and failure semantics.
- Suitability for RTOS-style execution.

Major state groups include:

| Domain | Example States |
|---|---|
| Idle and recovery | `IDLE`, `TIMEOUT`, `ERROR`, `CRITICAL_FAIL` |
| Correction requester | `CORR_WAIT_RSP`, `CORR_COLLECTING`, `CORR_COMPUTING`, `CORR_DONE` |
| Correction responder | `CORR_RESPONDING` |
| Relay sender | `RELAY_WAIT_ACCEPT`, `RELAY_SENDING`, `RELAY_WAIT_ACK`, `RELAY_DONE` |
| Relay provider | `RELAY_RECEIVING`, `RELAY_STORING`, `RELAY_DOWNLINKING` |
| Borrow requester | `BORROW_WAIT_ACCEPT`, `BORROW_RECEIVING`, `BORROW_DONE` |
| Borrow provider | `BORROW_SAMPLING`, `BORROW_SENDING` |

The failure design is especially important. A received failure message does not push the receiving satellite into critical failure. It records the failed neighbour and continues operating. Only local `CRITICAL_FAILURE` moves the node itself into `CRITICAL_FAIL`. This prevents constellation-wide failure cascades.

## Protocol Wire Format

SISP uses a fixed 64-byte physical frame. This keeps parsing predictable and makes timing and energy calculations straightforward.

Frame characteristics:

- 64 bytes, or 512 bits, fixed frame size.
- Compact packed header.
- Sender, receiver, sequence, flags, service code, and DEGR fields.
- Transport extension region for PHY profile and session metadata.
- Typed payloads for correction, relay, borrow, status, heartbeat, and failure.
- CRC-8/MAXIM checksum.

This fixed-frame approach is a deliberate engineering trade-off. It limits peak payload efficiency but improves determinism, testing, bounded memory use, and embedded reliability.

## Service Messages

| Message | Purpose |
|---|---|
| `CORRECTION_REQ` | Request neighbour sensor readings |
| `CORRECTION_RSP` | Return a sensor reading and health context |
| `RELAY_REQ` | Ask a neighbour to relay data |
| `RELAY_ACCEPT` | Accept a relay request |
| `RELAY_REJECT` | Reject a relay request |
| `DOWNLINK_DATA` | Carry fragmented relay or borrowed data |
| `DOWNLINK_ACK` | Acknowledge downlink fragments |
| `STATUS_BROADCAST` | Share energy, sensor mask, uptime, and PHY capability |
| `HEARTBEAT` | Share basic liveness and DEGR |
| `HEARTBEAT_ACK` | Acknowledge heartbeat |
| `BORROW_REQ` | Request a healthy sensor stream |
| `BORROW_DECISION` | Accept or reject a borrow request |
| `FAILURE` | Broadcast local critical failure |

## Correction Service Flow

The correction flow is the heart of SISP.

```text
1. A satellite detects a local sensor fault.
2. It broadcasts CORRECTION_REQ.
3. Neighbours respond with CORRECTION_RSP.
4. The requester buffers valid readings.
5. Each reading is weighted by the sender's DEGR trust score.
6. Suspicious or incompatible readings are rejected.
7. A timer closes the response window.
8. A correction filter computes the corrected value.
9. The satellite returns to normal operation with a usable estimate.
```

Measured correction quality:

| Scenario | Raw Error | Corrected Error | Improvement |
|---|---:|---:|---:|
| 30-day drift, Kalman, IT-05 | RMSE 8.909 | RMSE 0.504 | 94.3% |
| 10% packet loss, 7 days, IT-06 | RMSE 8.290 | RMSE 1.197 | 85.6% |
| Nominal 3-satellite Kalman | 2.502 steady-state | 1.304 steady-state | 47.9% |
| Large-fault 3-satellite Kalman | 22.71 steady-state | 8.47 steady-state | 62.7% |

The result is not just cleaner data. It is retained mission utility. A satellite that would otherwise degrade can keep contributing useful measurements.

## DEGR Trust Model

SISP uses DEGR, a 4-bit degradation score from 0 to 15, to represent satellite health.

DEGR is designed as a continuous trust signal, not a binary good/bad label. This matters because space systems often degrade gradually. A partially degraded satellite may still provide useful information, but it should carry less influence.

Correction weights are computed as:

```text
w_i = max(0.05, 1 - DEGR_i / 15)
```

| DEGR | Meaning | Weight |
|---:|---|---:|
| 0 | Healthy | 1.000 |
| 4 | Mild degradation | 0.733 |
| 8 | Moderate degradation | 0.467 |
| 12 | Severe degradation | 0.200 |
| 14 | Near failure | 0.067 |
| 15 | Failed | 0.050 floor |

The 0.05 floor prevents inputs from silently disappearing. The system remains explicit about degraded participants while making sure healthy neighbours dominate the correction.

Benchmark evidence shows inverse-error DEGR weighting outperforming neutral equal weighting in mixed-quality scenarios:

| DEGR Model | Corrected Error | Gain Over Raw |
|---|---:|---:|
| inverse_error | 19.06 | 22.54 |
| neutral | 22.47 | 19.14 |
| proportional_error | 27.85 | 13.75 |

## Correction Algorithms

SISP supports multiple correction algorithms behind one C++ interface.

| Algorithm | Strength | Best Use |
|---|---|---|
| Weighted Average | Simple fallback | Minimal configuration or baseline mode |
| Weighted Median | Robust to outliers and persistent bad peers | Small groups with biased or corrupted responders |
| Kalman Filter | Strong smoothing and drift tracking | Gaussian noise, long-term drift, general correction |
| Hybrid Filter | Median prefilter plus Kalman smoothing | Unknown or mixed fault environments |
| NIS-Gated Kalman concept | Rejects statistically inconsistent measurements | Spike/outlier scenarios with innovation gating |

The documentation recommends Kalman for Gaussian and drift-heavy scenarios and Hybrid for production-like unknown conditions. This is a strong architecture decision: SISP does not hardcode one correction worldview. The protocol is stable while the correction strategy can evolve.

## Anomaly Detection Pipeline

The SVD anomaly detection subsystem uses the OPSSAT-AD telemetry dataset. Each telemetry segment contains 19 engineered features and metadata including channel, segment, train split, and anomaly label.

The pipeline is intentionally leakage-resistant:

1. Ingest data from OPSSAT-AD.
2. Split by telemetry channel.
3. Fit preprocessing only on nominal training rows.
4. Median-impute missing values.
5. Transform zero-variance fit-row features into binary deviation indicators.
6. Winsorize continuous features using fit-row quantiles.
7. Scale continuous features with fit-row statistics.
8. Train per-channel `TruncatedSVD`.
9. Choose rank using a 90% explained-variance rule, clamped between 2 and 15.
10. Score rows by squared reconstruction error.
11. Threshold at the 95th percentile of nominal fit-row errors.
12. Report confusion matrix, precision, recall, F1, and ROC-AUC.

Why this works:

Nominal telemetry tends to live in a lower-dimensional pattern space. A truncated SVD basis captures that normal structure. Anomalous segments reconstruct poorly because they do not fit the nominal subspace. Reconstruction error becomes the anomaly signal.

The docs report CADC0894 reaching ROC-AUC around 0.84 with a rank around 4. More importantly, the pipeline is structured correctly: all learned medians, caps, scalers, SVD bases, and thresholds are fit only on nominal training rows.

## Relay Service

The relay service solves a practical orbital problem: a satellite may have data but no direct ground-station opportunity. Instead of waiting, it can move that data through another satellite.

Relay flow:

```text
1. Satellite loses ground visibility or enters a low-energy relay condition.
2. It broadcasts RELAY_REQ.
3. A neighbour accepts with RELAY_ACCEPT.
4. The payload is fragmented into DOWNLINK_DATA frames.
5. The receiver stores and reassembles fragments.
6. DOWNLINK_ACK confirms delivery.
```

Validated relay resilience includes:

- Corrupted fragment dropped by checksum.
- Tail fragment arriving before head fragment.
- Missing middle fragment retried.
- Duplicate replay suppressed.
- Full payload recovered.

The documented relay text resilience test recovered 109/109 bytes after corruption, out-of-order delivery, retry, and duplicate replay.

## Borrow Service

Sensor borrowing is one of SISP's most distinctive ideas. If a satellite cannot rely on a local sensor, it can request a healthy neighbour's sensor stream.

Borrow flow:

```text
1. Borrower broadcasts BORROW_REQ.
2. Healthy neighbours respond with BORROW_DECISION.
3. The borrower accepts a provider.
4. The provider sends sensor data using DOWNLINK_DATA.
5. The borrower uses the remote sensor stream for the requested window.
```

This turns sensor redundancy from a hardware-only feature into a network feature. A mission can gain resilience without duplicating every sensor on every satellite.

## Dual-PHY 437 MHz Design

SISP targets practical low-power UHF assumptions around the 435-438 MHz amateur satellite allocation, using two profiles on the same 437 MHz center region.

| Profile | Bandwidth | Bit Rate | Use |
|---|---:|---:|---|
| `CONTROL_437_NARROW` | 12.5 kHz | 12.5 kbps | Correction, relay control, borrow control, status, heartbeat, failure |
| `BULK_437_WIDE` | 25 kHz | 25 kbps | `DOWNLINK_DATA` and `DOWNLINK_ACK` when supported |

The state machine selects PHY per frame:

- Control messages always stay on the narrow robust control profile.
- Bulk data and acknowledgements may upgrade to wide profile.
- Broadcast messages remain on control.
- If the peer does not support bulk, SISP falls back to control.

This design keeps command and coordination traffic robust while allowing higher throughput for data transfer when both sides support it.

The dual-PHY correctness test passes 8/8 assertions and confirms that control-service frames do not incorrectly use the bulk PHY.

## Signal Physics

SISP's signal model is grounded in practical UHF satellite communication assumptions.

Baseline:

- 437 MHz UHF carrier region.
- GMSK BT=0.3.
- Constant-envelope modulation suitable for smallsat power amplifiers.
- K=7, R=1/2 convolutional coding.
- RS(255,223) outer coding approximation.
- 64-byte frames.
- Free-space path loss, receiver noise, Doppler, BER, PER, and link margin modelling.

Key physical numbers:

| Quantity | Value |
|---|---:|
| UHF free-space path loss at 1000 km | about 145.3 dB |
| Ka-band path loss at 26 GHz and 1000 km | about 180.7 dB |
| UHF path-loss advantage over Ka at same distance | about 35 dB |
| Maximum LEO Doppler at 437 MHz and 7.5 km/s | about 10.9 kHz |
| GMSK BT=0.3 penalty vs BPSK | about 1.67 dB |
| Conv+RS coding expansion | about 2.287x |
| Control frame time at 12.5 kbps with Conv+RS | about 93.6 ms |
| Bulk frame time at 25 kbps with Conv+RS | about 46.8 ms |

The docs report maximum usable ranges around 2,800 km for the control profile and 2,100 km for the bulk profile under reference UHF assumptions. These exceed typical LEO neighbour spacing, meaning geometry and scheduling become the main limiting factors rather than raw link budget.

## Energy Model

SISP uses transparent frame-level energy accounting:

```text
E_TX = P_TX * frame_time
E_RX = P_RX * frame_time
frame_time = air_bits / bit_rate
```

Reference assumptions:

| Parameter | Value |
|---|---:|
| Tx DC power | 10 W |
| Rx DC power | 2.5 W |
| Frame size | 64 bytes, 512 bits |
| Conv+RS air bits per frame | about 1,171 bits |
| Control frame time | about 93.6 ms |
| Bulk frame time | about 46.8 ms |

Correction energy remains small under the documented scenarios. With 8 neighbours, a correction snapshot fits comfortably under the 5-second timer, taking roughly 849 ms of on-air time and around 12.2 J network energy per event under the detailed energy study. With 24 correction events per day, this is around 0.081 Wh per day, a tiny fraction of typical CubeSat daily energy generation.

For bulk relay, the docs estimate a 1 MiB compressed relay over the 25 kHz bulk profile at about 6.1 minutes and about 1.26 Wh total TX+RX energy. This is operationally meaningful but affordable when scheduled around visibility and energy windows.

The energy message is clear: SISP's routine correction traffic is negligible, and its emergency relay traffic is measurable, schedulable, and realistic.

## Validation Evidence

SISP has a broad validation surface.

### C++ Tests

| Group | Tests Passing | Coverage |
|---|---:|---|
| Encoder / Decoder | 70/70 | Service codes, checksum detection, payload round-trip |
| Payload Codec | 65/65 | Typed payload serialization and parsing |
| 512-bit Frame Pipeline | 21/21 | Frame-level behaviour and heartbeat/status updates |
| State Machine | 38/38 | Transitions, timers, response collection, relay paths |
| DEGR Computation | 20/20 | Health scoring and clamping |
| Protocol Simulation | 25/25 | Correction, relay, heartbeat, plugins, error frames |
| Level-2 Matrix | 34/34 | Correction, relay, borrow, failure, reset |
| Total | 273/273 | Full protocol test suite |

### Python Integration Tests

| Test Area | Evidence |
|---|---|
| Dual-PHY selection | 8/8 assertions pass |
| No-cascade failure | Healthy nodes remain IDLE while recording failed peers |
| Borrow addressing | Broadcast request followed by unicast decision and accepted provider data |
| Relay resilience | 109/109 bytes recovered after corruption, reordering, retry, and replay |
| Kalman correction | Strong improvement in nominal and large-fault scenarios |
| Algorithm comparison | Kalman and Hybrid outperform baselines under multiple noise profiles |
| Integration matrix | DEGR weighting, relay gap, 30-day correction, and packet-loss scenarios pass |

### BER Validation

The BPSK AWGN Monte Carlo validation uses 500,000 bits and matches theory within expected variance across tested Eb/N0 values. This supports the correctness of the communication simulation layer.

## Impact

SISP creates impact at several levels: mission, economic, environmental, scientific, and strategic.

### Mission Impact

| Mission Need | SISP Contribution |
|---|---|
| Keep degraded satellites useful | Correct degraded readings using trusted neighbour data |
| Reduce missed-contact risk | Relay payloads through satellites with better visibility |
| Replace some hardware redundancy | Borrow healthy sensor streams from neighbouring spacecraft |
| Prevent cascading faults | Record failed neighbours without declaring healthy nodes failed |
| Improve operator confidence | Provide deterministic, tested, explainable protocol behaviour |

The mission effect is continuity. SISP helps keep data flowing and spacecraft useful even when individual components degrade.

### Economic Impact

The KPI snapshot models a 100-satellite reference constellation with:

- 3-year baseline design life.
- 45% SISP-enabled life extension assumption.
- 12% annual sensor failure rate.
- 60% sensor recovery through borrowing.
- 5 kg satellite mass.
- $500K unit satellite cost.
- $6,000/kg launch cost.

Under that reference scenario, the docs estimate:

| Metric | Baseline | With SISP | Change |
|---|---:|---:|---:|
| Replacement launches per year | 33.3 | 23.0 | 10.3 fewer per year |
| Satellite mass launched per year | 167 kg | 115 kg | 52 kg avoided per year |
| Sensor failures recovered | 0 | 7.2 per year | 7.2 retained missions |

The 50-year high-growth model estimates about $12B in replacement cost savings. These are modelled values, not flight measurements, but they show the scale of the opportunity if cooperative autonomy extends usable mission life.

### Environmental Impact

Fewer premature replacements mean fewer launches, less mass to orbit, and lower launch-associated emissions.

The reference KPI model estimates:

| Metric | Modeled Impact |
|---|---:|
| CO2 avoided per year in 100-satellite scenario | about 3,100 t CO2-eq |
| CO2 avoided over 50-year growth model | about 7 Mt CO2-eq |
| Satellite mass avoided over 50-year growth model | about 115,000 t |
| Replacement launches avoided over 50-year growth model | about 23,000 |

The sustainability argument is not that software alone solves space sustainability. The stronger and more credible claim is that autonomous resilience reduces premature replacement pressure, which reduces the material and launch footprint of constellation operations.

### Scientific and Data Impact

SISP preserves data continuity. That matters wherever small satellites are used for longitudinal observation:

- Earth observation.
- Agriculture monitoring.
- Climate and environmental sensing.
- Disaster response.
- Space-weather monitoring.
- University research missions.
- Remote infrastructure monitoring.

Sensor drift and data gaps can undermine scientific datasets. SISP's correction and borrowing services can protect continuity during faults and visibility gaps.

### Strategic Impact

SISP changes the operating philosophy of smallsat constellations:

| Old Model | SISP Model |
|---|---|
| Each satellite survives alone | Satellites cooperate as a network |
| Redundancy is mainly hardware | Redundancy can be shared as a service |
| Ground contact is the recovery bottleneck | Local autonomous recovery can happen in orbit |
| Faults are local surprises | Health becomes shared trust context |
| Link protocols move bits only | SISP moves mission intent: correct, relay, borrow, fail safely |

This is the strategic value: SISP is not just a communication feature. It is a mission-resilience layer.

## Market and Users

Primary users:

- CubeSat constellation operators.
- University satellite teams.
- Earth-observation smallsat companies.
- Space sustainability programs.
- Mission assurance teams.
- Aerospace integrators.
- Defense and disaster-response remote-sensing missions.
- Satellite insurance and risk-analysis stakeholders.

High-value use cases:

| Use Case | SISP Benefit |
|---|---|
| Sensor drift recovery | Correct readings before mission data degrades beyond usability |
| Missed ground pass mitigation | Relay data through a better-positioned neighbour |
| Temporary sensor loss | Borrow sensor readings from a healthy spacecraft |
| Constellation health awareness | Use DEGR, heartbeat, status, and failure messages |
| Emergency data preservation | Move priority data during short visibility windows |
| Pre-launch mission assurance | Simulate correction, relay, energy, and link feasibility |

## Competitive Differentiation

| Existing Approach | Limitation | SISP Advantage |
|---|---|---|
| Hardware redundancy | Adds mass, cost, and power | Uses neighbours as software-defined redundancy |
| Ground-only recovery | Slow and visibility-limited | Enables autonomous in-orbit correction |
| DTN/store-and-forward | Moves data but does not correct sensors | Adds correction and borrowing services |
| Low-level radio protocols | Provide links but not mission semantics | Defines service-level correction, relay, borrow, and failure logic |
| Expensive high-rate crosslinks | Costly and power-hungry | Uses modest UHF-compatible assumptions |
| Offline anomaly detection | Happens after data reaches ground | Positions anomaly screening before correction decisions |

SISP's defensibility is the integration:

- Deterministic embedded protocol.
- Trust-aware correction.
- Anomaly screening.
- Sensor borrowing.
- Relay resilience.
- Dual-PHY frame selection.
- Energy and sustainability modelling.
- Automated validation.

The innovation is the complete cooperative autonomy stack.

## Business Models

SISP can support multiple commercialization paths.

### 1. Protocol Licensing

License the embedded protocol stack to smallsat operators and integrators.

Revenue streams:

- Annual software license.
- Per-mission integration fee.
- Support and maintenance.
- Custom protocol adaptation.

### 2. Mission Assurance Toolkit

Sell the simulation, dashboard, and validation layer as a pre-launch mission assurance product.

Revenue streams:

- Simulation studies.
- Fault modelling.
- Link and energy analysis.
- Investor or grant readiness reports.
- Operator-facing resilience dashboards.

### 3. Embedded Flight Software Module

Package SISP as a flight-software component for onboard autonomy.

Revenue streams:

- Flight software integration.
- Hardware-in-the-loop validation.
- Certification support.
- Long-term mission support.

### 4. Open-Core Research Standard

Keep the core research protocol visible and accessible while monetizing mission-specific tooling, hardware integration, dashboards, and enterprise support.

This path could work well for universities, standards discussions, and sustainability-oriented partners.

## Roadmap

### Completed

- C++ protocol state machine.
- Fixed-frame encoder and decoder.
- Correction, relay, borrow, heartbeat, status, and failure services.
- DEGR trust scoring.
- Pluggable correction filters.
- Python integration harnesses.
- SVD anomaly detection pipeline.
- UHF 437 MHz signal physics model.
- Energy and sustainability dashboards.
- C++ and Python validation suites.
- Pitch, KPI, architecture, and research documentation.

### Next 3 Months

- Normalize public protocol specification and versioning.
- Re-run and archive fresh C++ and Python logs.
- Add continuous integration for C++ and Python tests.
- Align all documentation numbers and remove stale references.
- Package Streamlit demos for repeatable presentations.
- Create a hardware-in-the-loop test plan.

### Next 6 Months

- Integrate with COTS UHF radios or SDR testbed.
- Validate timing, BER/PER, frame recovery, and PHY switching over real or emulated RF.
- Add authentication and replay protection for security hardening.
- Expand scale tests to 25, 50, and 100 nodes.
- Build mission-specific telemetry adapters.

### Next 12 Months

- Secure a university, lab, or smallsat partner.
- Run flatsat demonstration.
- Validate correction, relay, and borrow over representative hardware.
- Prepare flight demonstration proposal.
- Package SISP as SDK plus simulation dashboard suite.

## Risks and Mitigations

| Risk | Why It Matters | Mitigation |
|---|---|---|
| Not flight-qualified yet | Space software requires high assurance | Position current work as validated prototype; pursue HIL and flatsat validation |
| Energy assumptions vary by mission | Operators need credible numbers | Keep calculators transparent and scenario-adjustable |
| Spectrum coordination constraints | UHF use depends on mission and licensing | Keep PHY profile configurable for mission-specific bands |
| Security and spoofing | Malicious frames could affect trust | Add authentication, signed health beacons, and replay protection |
| Bad neighbours bias correction | Faulty readings can degrade estimates | Use DEGR weighting, anomaly gates, hybrid filters, and failure isolation |
| Scaling to dense constellations | Broadcast storms and contention can emerge | Bound neighbour counts, schedule correction windows, and add priority rules |
| Simulation-to-flight gap | Models may miss hardware effects | Validate with SDR/COTS radios, RF emulation, and flatsat testing |

These are real risks, but they are engineering risks with clear next steps, not conceptual blockers.

## Why SISP Is Credible

SISP is credible because it ties ambition to implementation.

It does not stop at saying "satellites should cooperate." It defines messages, states, timers, payloads, trust scores, correction algorithms, PHY profiles, energy formulas, tests, and dashboards.

It does not stop at saying "correction improves quality." It documents 94.3% RMSE improvement in a 30-day drift scenario and 85.6% improvement under 10% packet loss.

It does not stop at saying "relay is robust." It tests corruption, reordering, retry, duplicate replay, and full payload recovery.

It does not stop at saying "failure isolation matters." It encodes no-cascade behaviour in the transition model and validates it.

It does not stop at saying "this is low-power." It computes frame time, coding expansion, energy per event, relay energy, and daily budget share.

This is the difference between an idea and a technical platform.

## Pitch Narrative

CubeSats are transforming access to space, but their operating model is still too fragile. A small satellite can lose mission value because one sensor drifts, one ground pass is missed, or one subsystem becomes degraded. For a low-cost spacecraft, adding duplicate hardware everywhere is expensive. Waiting for the ground is slow. Replacing satellites early increases cost, launch mass, and environmental footprint.

SISP changes the model. It lets satellites cooperate autonomously. A satellite with a degraded sensor can ask neighbours for readings, weight them by trust, filter suspicious values, and compute a corrected estimate. A satellite without ground visibility can relay through another spacecraft. A satellite missing a local sensor can borrow a healthy sensor stream. A failed satellite can be recorded by the network without causing healthy nodes to fail with it.

Technically, SISP is built around a deterministic C++ finite state machine, compact 64-byte frames, DEGR health scoring, pluggable correction filters, OPSSAT-AD SVD anomaly detection, and practical 437 MHz UHF link assumptions. The system is validated by 273 passing C++ tests, Python integration scenarios, dual-PHY checks, BER validation, relay resilience tests, and correction-quality benchmarks.

The impact is direct: better mission continuity, lower replacement pressure, more available data, and a more sustainable constellation operating model. SISP gives small satellites a cooperative survival layer.

## Suggested Demo Story

1. Show a small constellation where one satellite's sensor starts drifting.
2. Trigger `FAULT_DETECTED`.
3. Show `CORRECTION_REQ` broadcast and neighbour `CORRECTION_RSP` replies.
4. Show DEGR weighting and Kalman or Hybrid correction.
5. Present the 94.3% RMSE improvement result.
6. Trigger a visibility gap and show relay negotiation.
7. Demonstrate payload recovery after fragment corruption and reordering.
8. Trigger a borrow request and show a healthy neighbour providing sensor data.
9. Show the dual-PHY profile selection for control versus data.
10. Close on energy and sustainability dashboards.

This demo communicates the full value chain: fault, cooperation, trust, correction, relay, borrowing, energy, and impact.

## Key Claims to Use Publicly

Use these confidently:

- SISP is an implemented cooperative protocol stack for CubeSat constellations.
- The C++ protocol suite reports 273/273 passing tests.
- The correction system achieves 94.3% RMSE improvement in the documented 30-day drift scenario.
- The correction system maintains 85.6% improvement under 10% packet loss in the documented integration test.
- The relay path recovers a multi-fragment payload through corruption, out-of-order delivery, retry, and duplicate replay.
- The state machine explicitly prevents received failure messages from cascading healthy satellites into critical failure.
- The protocol uses fixed 64-byte frames and deterministic state transitions suitable for constrained embedded targets.
- The PHY model uses practical 437 MHz UHF assumptions with narrow control and wider bulk profiles.
- The energy model shows routine correction traffic is a very small fraction of daily CubeSat energy budgets under documented assumptions.

Use these with modelled/scenario language:

- SISP can reduce replacement pressure by extending useful mission life.
- SISP can reduce launch mass and launch-associated CO2 when it avoids premature replacements.
- The KPI dashboard's 100-satellite reference scenario estimates about 3,100 t CO2-eq avoided per year.
- The 50-year high-growth scenario estimates about $12B in replacement cost savings and about 7 Mt CO2-eq avoided.

Avoid presenting modelled sustainability outcomes as flight-proven measurements. They are scenario-derived impact estimates.

## Closing Statement

SISP gives small satellites a cooperative survival layer. It transforms a constellation from a group of isolated spacecraft into a resilient network where satellites can share sensing, communication opportunity, and operational trust.

The project is technically strong because it integrates protocol design, embedded implementation, anomaly detection, correction algorithms, physical-layer modelling, energy accounting, and validation into one coherent system. The project is commercially compelling because it addresses a real pain point for CubeSat missions: fragile spacecraft need resilience without heavy, expensive hardware redundancy. The project is socially and environmentally meaningful because longer-lived, more reliable satellites can reduce replacement pressure, launch mass, and emissions.

SISP is not merely a communication protocol. It is a mission-continuity platform for the next generation of cooperative satellite constellations.

