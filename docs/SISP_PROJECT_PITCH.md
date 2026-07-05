# SISP Project Pitch

## Executive Summary

SISP, the Satellite Inter-Service Protocol, is a cooperative, self-healing protocol stack for CubeSat constellations. It enables satellites to correct degraded sensors, relay data across ground-station visibility gaps, and borrow healthy sensor readings from neighboring satellites without waiting for ground intervention.

The project combines a deterministic C++ protocol implementation, an anomaly detection pipeline trained on OPSSAT-AD telemetry, physics-backed UHF inter-satellite link modeling, correction algorithms, energy analysis, sustainability modeling, Streamlit dashboards, and a reproducible validation suite.

SISP's core pitch is simple: small satellites should not fail alone. A constellation should behave like a cooperative network where one satellite's healthy sensors, communication window, and energy availability can temporarily support another. SISP turns that idea into a tested protocol with measurable impact.

## One-Line Pitch

SISP is a lightweight autonomous protocol that lets CubeSat constellations self-correct sensor faults, relay mission data, and borrow healthy sensor readings through low-power inter-satellite links.

## Short Pitch

CubeSats are low-cost, but they are fragile. A single degraded sensor, missed ground pass, or communication bottleneck can shorten mission life and force premature replacement. SISP provides a cooperative protocol layer that allows satellites to help each other in orbit.

When a satellite detects a fault, it broadcasts a correction request, collects trusted neighbor readings, filters anomalies, and computes a corrected estimate in seconds. When ground contact is unavailable, it can relay data through a neighbor. When its own sensor is unavailable, it can borrow readings from another satellite. The result is greater mission resilience, lower replacement cost, improved data availability, and reduced launch-related environmental impact.

## Problem

Small satellite constellations face four linked problems:

1. **Sensor degradation ends missions early.** CubeSats often lack redundant hardware, so a failed or drifting sensor can reduce mission quality or terminate mission usefulness.
2. **Ground-station contact is sparse.** A single satellite may see a ground station for only a small fraction of each orbit, creating latency and data-loss risk.
3. **Onboard resources are constrained.** Any solution must operate within strict limits on energy, bandwidth, memory, and compute.
4. **Failures should not cascade.** A cooperative constellation must share health information without letting one failed node pull healthy nodes into a failure state.

Traditional approaches lean on hardware redundancy, larger spacecraft, higher-power links, or ground-based intervention. Those are expensive and often incompatible with low-cost CubeSat missions.

## Solution

SISP adds a service layer for autonomous cooperation between satellites. It defines three core services:

| Service | Trigger | What SISP Does | Mission Benefit |
|---|---|---|---|
| Correction | Sensor fault detected | Requests neighbor readings, weights them by trust, filters anomalies, computes corrected estimate | Keeps degraded satellites useful |
| Relay | Low energy or ground-station loss | Negotiates a relay path, fragments payloads, sends mission data through a neighbor | Reduces data latency and missed-contact risk |
| Borrow | Ground station visible or local sensor unavailable | Requests a neighbor's healthy sensor stream | Replaces hardware redundancy with software-defined redundancy |

These services run through a deterministic finite state machine and a fixed 64-byte frame format designed for embedded flight software.

## Value Proposition

SISP creates value at three levels.

### For Satellite Operators

- Extends useful mission life by allowing degraded satellites to keep producing corrected data.
- Improves data availability by using inter-satellite relay opportunities instead of waiting only for ground contact.
- Reduces replacement pressure and launch costs.
- Provides transparent health and trust scoring across the constellation.
- Fits low-power CubeSat constraints through compact frames and UHF-compatible PHY design.

### For Mission Designers

- Reduces dependency on duplicate onboard sensors.
- Makes resilience a protocol capability instead of only a hardware capability.
- Adds testable, deterministic behavior suitable for embedded and RTOS environments.
- Allows correction algorithms to be swapped without rewriting the protocol layer.

### For Sustainability and Policy Stakeholders

- Fewer premature replacements mean less mass launched, fewer replacement launches, and lower launch-associated CO2.
- More reliable spacecraft reduce pressure to over-deploy satellites for redundancy.
- Autonomous cooperation can improve responsible constellation operation.

## Why Now

CubeSat and smallsat constellations are growing quickly, but many missions still rely on ground-centric operations and limited onboard redundancy. At the same time, inter-satellite communication hardware is becoming more accessible, and operators need ways to increase resilience without increasing spacecraft mass and cost.

SISP fits this moment because it uses modest assumptions: small fixed frames, UHF-compatible communication, low bandwidth, lightweight algorithms, and bounded neighbor sets. It does not require expensive high-rate optical or Ka-band crosslinks to deliver its core resilience benefits.

## Product Overview

SISP is not just a concept. The repository contains:

- A C++ protocol implementation with state machine, encoder, decoder, correction layer, and simulation hooks.
- Python integration harnesses that drive multi-satellite scenarios through the C++ DLL.
- A telemetry anomaly detection pipeline using per-channel TruncatedSVD on OPSSAT-AD data.
- Weighted median, Kalman, hybrid, and NIS-gated Kalman correction approaches.
- A 437 MHz signal physics study with BER, PER, Doppler, FEC, and link-budget modeling.
- Streamlit dashboards for physical simulation, protocol energy, and sustainability KPIs.
- C++ and Python test suites covering protocol behavior, correction quality, relay resilience, failure isolation, and dual-PHY selection.

## Technical Architecture

### System Layers

| Layer | Role | Implementation |
|---|---|---|
| Service layer | Correction, relay, borrow, heartbeat, failure | C++ state machine |
| Protocol layer | Fixed frame codec, service codes, payloads, CRC | C++ encoder/decoder |
| Trust layer | DEGR score and neighbor weighting | C++ protocol/correction logic |
| Correction layer | Weighted median, Kalman, hybrid filtering | C++ pluggable filters |
| Anomaly layer | SVD reconstruction error and chi-square gating | Python pipeline and research integration |
| PHY model | UHF 437 MHz control and bulk profiles | Simulation and tested PHY selection |
| Dashboard layer | Geometry, BER/PER, energy, sustainability | Streamlit |

### State Machine

The protocol is governed by a deterministic 21-state, 24-event finite state machine. It uses a static transition table for predictable dispatch and embedded suitability.

Major state domains:

- Correction requester and responder states.
- Relay sender and relay provider states.
- Borrow requester and borrow provider states.
- Timeout, error, reset, and critical failure states.

Important design choices:

- `RESET` returns any state to `IDLE`.
- `CRITICAL_FAILURE` moves only the local node to `CRITICAL_FAIL`.
- `RX_FAILURE` records a failed neighbor without cascading failure.
- Correction, relay, and borrow each have explicit timers and retry behavior.

### Frame Protocol

SISP uses a fixed 64-byte physical frame. This keeps parsing deterministic and limits memory requirements.

Frame features:

- Compact 5-byte packed header.
- Service code, sender, receiver, sequence, flags, and DEGR fields.
- Transport extension region for PHY profile and session metadata.
- Payload region for service-specific data.
- CRC-8/MAXIM checksum.

This fixed-frame design supports predictable energy and timing calculations.

### Services

#### Correction Service

1. A satellite detects a local fault.
2. It broadcasts `CORRECTION_REQ`.
3. Neighbors respond with `CORRECTION_RSP`.
4. Responses are weighted by DEGR trust score.
5. Anomaly gates reject suspicious readings.
6. A correction filter computes the corrected value.

Documented result: 94.3% RMSE improvement in the 30-day drift scenario.

#### Relay Service

1. A satellite with low energy or lost ground visibility sends `RELAY_REQ`.
2. A neighbor accepts using `RELAY_ACCEPT`.
3. Payloads are fragmented into `DOWNLINK_DATA`.
4. Receiver reassembles fragments, handles out-of-order delivery, and acknowledges with `DOWNLINK_ACK`.

Validated behavior includes corruption handling, out-of-order fragment recovery, duplicate replay suppression, and full text payload recovery.

#### Borrow Service

1. A satellite broadcasts `BORROW_REQ`.
2. Healthy neighbors reply with `BORROW_DECISION`.
3. The borrower accepts one provider.
4. Sensor data is streamed through `DOWNLINK_DATA`.

This turns sensor redundancy into a network service. Instead of carrying duplicate hardware for every sensor, a satellite can temporarily borrow readings from another spacecraft in the constellation.

### Trust and DEGR Weighting

SISP uses DEGR, a continuous degradation score from 0 to 15, to express node health. The correction layer maps DEGR into trust weights:

```text
w_i = max(0.05, 1 - DEGR_i / 15)
```

Healthy nodes receive high weight. Degraded nodes are still visible to the system but strongly down-weighted. The 0.05 floor prevents silent removal and keeps behavior explicit.

The DEGR model incorporates:

- Kalman k-factor deviation.
- SVD reconstruction residual.
- Mission age.
- Orbit or ADCS error.

In documented tests, inverse-error DEGR weighting outperformed neutral equal weighting.

### Correction Algorithms

SISP supports multiple correction algorithms through a pluggable C++ interface.

| Algorithm | Strength | Best Use |
|---|---|---|
| Weighted Median | Robust to outliers, no state | Small groups with biased or corrupted peers |
| Kalman | Strong under Gaussian noise and drift | General correction and long-term drift |
| Hybrid | Median prefilter plus Kalman smoothing | Unknown or mixed fault environments |
| NIS-Gated Kalman | Rejects statistically inconsistent innovations | Spikes and suspicious measurements |

The recommended production default from the docs is inverse-error DEGR weighting plus the hybrid filter for unknown environments, with Kalman performing especially well in Gaussian and long-term drift scenarios.

### Anomaly Detection

The anomaly subsystem uses OPSSAT-AD telemetry segments. Each segment contains 19 engineered features plus metadata.

Pipeline:

1. Ingest raw OPSSAT-AD data.
2. Split by telemetry channel.
3. Fit preprocessing only on nominal training rows.
4. Apply imputation, zero-variance handling, winsorization, and scaling.
5. Train per-channel TruncatedSVD on nominal data only.
6. Score each row by reconstruction error.
7. Threshold at the 95th percentile of nominal training reconstruction errors.

This creates an unsupervised anomaly screen that can reject corrupted readings before they influence distributed correction.

Important engineering rule: all learned preprocessing parameters are fit only on `train=True AND anomaly=False` rows, preventing label leakage.

### Physical Layer

SISP targets the 435-438 MHz amateur satellite allocation, using dual profiles on the same 437 MHz center band.

| Profile | Bandwidth | Bit Rate | Purpose |
|---|---:|---:|---|
| Control narrow | 12.5 kHz | 12.5 kbps | Correction, relay control, borrow control, heartbeat, failure |
| Bulk wide | 25 kHz | 25 kbps | Downlink data and acknowledgments when supported |

Baseline modulation:

- GMSK BT=0.3.
- Constant envelope.
- COTS UHF-radio friendly.
- Robust to moderate Doppler and nonlinear power amplifiers.

FEC model:

- Convolutional K=7, R=1/2.
- Reed-Solomon RS(255,223), t=16.
- Combined expansion about 2.287x.

The docs report typical maximum usable ranges around 2,800 km for the control profile and 2,100 km for the bulk profile under the reference UHF link assumptions, exceeding common LEO neighbor spacing.

### Energy Model

SISP's energy model is frame-based and transparent:

```text
E_TX = P_TX * frame_time
E_RX = P_RX * frame_time
frame_time = air_bits / bit_rate
```

Documented examples:

- 64-byte frame with Conv+RS on 12.5 kHz control: about 93.6 ms per frame.
- Correction with 6 neighbors: about 3.90 J network energy per event in the KPI snapshot.
- Correction with 8 neighbors: about 12.2 J network energy per event in the detailed energy study.
- 24 correction events per day remain a very small fraction of daily CubeSat energy.
- 1 MiB relay is documented between about 1.26 Wh and 2.53 Wh depending on PHY/timing assumptions, still below 1% of a 300 Wh/day spacecraft generation budget in the conservative case.

Pitch takeaway: SISP's routine correction overhead is negligible, and emergency or bulk relay is operationally affordable when scheduled intelligently.

## Validation and Evidence

### Test Coverage

The repository documents:

- 273/273 C++ tests passing.
- Python integration tests passing across correction, relay, borrow, dual-PHY, failure isolation, packet loss, and algorithm benchmarks.
- Monte Carlo BER validation with 500,000 simulated bits.
- Dual-PHY correctness with 8/8 assertions passing.

### Key Quantitative Results

| Claim | Evidence | Result |
|---|---|---:|
| C++ protocol correctness | Unit/integration tests | 273/273 pass |
| 30-day correction quality | IT-05 Kalman drift scenario | 94.3% RMSE improvement |
| Packet-loss resilience | IT-06, 10% packet loss, 7 days | 85.6% improvement |
| Dual-PHY correctness | `test_dual_phy_437.py` | 8/8 assertions pass |
| Relay resilience | Corrupt, out-of-order, duplicate fragments | 109/109 bytes recovered |
| Failure isolation | No-cascade failure test | Healthy nodes avoid cascade |
| Runtime speed | 500 correction rounds | about 0.009 ms/round |
| BER model validation | 500,000-bit Monte Carlo | within expected variance |

### Credibility Positioning

SISP should be pitched as a validated prototype and research-grade protocol stack, not as flight-qualified software yet. The strong claim is that the concept has been implemented, simulated, measured, and tested against realistic constraints. The next step is hardware-in-the-loop and mission-partner validation.

## Impact

### Operational Impact

SISP improves:

- Mission continuity when individual sensors degrade.
- Time-to-correction by allowing autonomous neighbor-assisted recovery.
- Data availability through relay opportunities.
- Fault awareness across the constellation.
- Operator confidence through deterministic, testable behavior.

### Economic Impact

The KPI snapshot models a 100-satellite constellation with:

- 3-year baseline design life.
- 45% SISP-enabled life extension.
- 12% annual sensor failure rate.
- 60% sensor recovery through borrowing.
- 5 kg satellite mass.
- $500K satellite unit cost.
- $6,000/kg launch cost.

Under those assumptions, the docs estimate:

- Replacement launches reduced from 33.3/year to 23.0/year.
- About 10.3 fewer replacements per year.
- About 52 kg less satellite mass launched per year, before modular mass effects.
- Long-term replacement cost savings in the billions under a high-growth 50-year model.

These are model-based values, and the dashboard makes the assumptions adjustable.

### Environmental Impact

The sustainability model estimates:

- About 3,100 t CO2 avoided per year for the reference 100-satellite scenario.
- About 7 Mt CO2 avoided over 50 years under the compounded growth scenario.
- Less launched mass and fewer replacement launches.

The environmental pitch is not that software alone solves space sustainability. It is that autonomous resilience reduces premature replacement, which reduces the material and launch footprint of constellation operations.

### Scientific and Data Impact

SISP can help missions preserve data continuity when sensors drift or fail. This matters for Earth observation, environmental monitoring, climate data collection, agriculture, disaster response, and any smallsat mission where a partial sensor failure can create gaps in longitudinal datasets.

## Competitive Landscape

| Existing Approach | Limitation | SISP Advantage |
|---|---|---|
| Hardware redundancy | Adds mass, cost, and power | Uses neighboring satellites as software-defined redundancy |
| Ground-only recovery | Slow and contact-window limited | Enables autonomous correction in orbit |
| DTN/store-and-forward only | Moves data but does not correct sensors | Adds correction and borrowing services |
| Standard low-level link protocols | No application-level sensor services | Defines correction, relay, borrow, failure semantics |
| High-end crosslinks | Expensive and power-hungry | Uses modest UHF-compatible assumptions |
| Offline anomaly detection | Happens after data reaches ground | Screens readings before they affect correction |

SISP's differentiation is the combination of protocol services, trust-weighted correction, anomaly gating, dual-PHY selection, energy accounting, and failure isolation in one coherent stack.

## Market and Use Cases

### Primary Users

- CubeSat constellation operators.
- University and research satellite missions.
- Earth observation smallsat teams.
- Space sustainability and mission-assurance programs.
- Defense, disaster response, and remote-sensing missions that need resilient data continuity.

### Use Cases

1. **Sensor drift recovery**
   - A satellite's magnetometer or environmental sensor drifts over time.
   - SISP uses neighbor readings to correct the estimate and preserve data quality.

2. **Missed ground pass mitigation**
   - A satellite loses direct ground visibility.
   - It relays data through a neighbor with a better downlink opportunity.

3. **Sensor borrowing**
   - A payload sensor fails or becomes unavailable.
   - The satellite borrows a healthy neighbor's reading stream during critical windows.

4. **Constellation health awareness**
   - Satellites share failure and degradation status.
   - The network avoids trusting bad nodes while preventing failure cascades.

5. **Educational and research platform**
   - Universities can study real protocol behavior, anomaly detection, and link budgets in one reproducible stack.

## Business Model Options

SISP can be positioned in several ways depending on the audience.

### Option 1: Protocol Licensing

License the protocol stack and simulation tooling to smallsat operators and mission integrators.

Revenue:

- Annual software license.
- Per-mission integration package.
- Support and validation services.

### Option 2: Mission Assurance Toolkit

Sell SISP as a resilience analysis and simulation toolkit before launch.

Revenue:

- Simulation studies.
- Fault and relay modeling.
- Custom mission-specific dashboards.
- Integration reports for investors, agencies, and insurers.

### Option 3: Embedded Flight Software Module

Package SISP as a flight-software component for onboard autonomy.

Revenue:

- Flight software integration.
- Hardware-in-the-loop validation.
- Certification and safety documentation.
- Long-term maintenance.

### Option 4: Open Core Research Standard

Keep the core protocol open for adoption while monetizing mission-specific tooling, dashboards, hardware integration, and enterprise support.

This may be attractive for academic, standards, and sustainability-oriented partners.

## Go-To-Market Strategy

### Phase 1: Prototype Credibility

- Consolidate docs, demos, and validation results.
- Produce a clean technical pitch and demo script.
- Run all test suites and publish reproducible logs.
- Package the Streamlit dashboards as the visual demo.

### Phase 2: Hardware-in-the-Loop

- Connect SISP to two or more COTS UHF radios.
- Validate frame timing, BER/PER behavior, and PHY switching.
- Demonstrate correction, relay, and borrow flows over real RF or RF emulation.

### Phase 3: Mission Partner Pilot

- Partner with a university CubeSat team, lab, or smallsat integrator.
- Integrate SISP into a ground testbed or flatsat.
- Validate with mission-specific sensor data and orbital geometry.

### Phase 4: Flight Demonstration

- Fly SISP as a hosted software experiment.
- Begin with noncritical telemetry sharing and relay experiments.
- Progress toward live correction and sensor borrowing.

## Roadmap

### Completed

- C++ protocol state machine.
- Fixed frame codec and service payloads.
- Pluggable correction layer.
- Python integration tests.
- SVD anomaly pipeline.
- UHF signal physics model.
- Energy and sustainability dashboards.
- Documentation and research paper.

### Next 3 Months

- Standardize versioned protocol specification.
- Resolve scenario-specific energy assumptions into one public calculator.
- Add CI automation for C++ and Python tests.
- Improve dashboard packaging and demo reproducibility.
- Prepare hardware-in-the-loop test plan.

### Next 6 Months

- Integrate with COTS radio emulator or SDR testbed.
- Add mission-specific telemetry adapters.
- Expand constellation scale tests to 25, 50, and 100 nodes.
- Add security hardening for malicious or spoofed frames.
- Produce a formal verification checklist for state-machine invariants.

### Next 12 Months

- Secure a mission partner.
- Run flatsat demonstration.
- Validate energy and link behavior with hardware.
- Prepare flight experiment proposal.
- Package SISP as SDK plus dashboard suite.

## Demo Plan for a Successful Pitch

### Demo 1: The Problem in One Minute

Show a 5-satellite constellation where one satellite has a degrading sensor and limited ground contact. Explain that the baseline satellite either waits for ground or produces bad data.

### Demo 2: Autonomous Correction

Trigger `FAULT_DETECTED`. Show:

- `CORRECTION_REQ` broadcast.
- Neighbor responses.
- DEGR weighting.
- Kalman or hybrid correction.
- RMSE improvement.

Headline result: 94.3% RMSE improvement in the 30-day documented scenario.

### Demo 3: Relay Across a Visibility Gap

Trigger `GS_LOST` or `ENERGY_LOW`. Show:

- Relay request.
- Accept handshake.
- Fragmented data.
- Out-of-order or corrupted fragment recovery.

Headline result: multi-fragment payload recovered completely in resilience tests.

### Demo 4: Borrow a Healthy Sensor

Trigger a borrow request and show:

- Broadcast `BORROW_REQ`.
- Provider decision.
- Sensor data routed from accepted satellite.

Message: SISP replaces some hardware redundancy with cooperative software redundancy.

### Demo 5: Impact Dashboard

Show adjustable assumptions:

- Constellation size.
- Design life.
- Sensor failure rate.
- Launch cost.
- CO2 per launch.

Close with the modeled economic and environmental savings.

## Suggested Pitch Deck Structure

1. **Title**
   - SISP: Autonomous Self-Healing for CubeSat Constellations.

2. **The Problem**
   - CubeSats fail early, ground contact is limited, redundancy is expensive.

3. **The Insight**
   - A constellation should cooperate like a network, not fail as isolated spacecraft.

4. **The Solution**
   - Correction, relay, and sensor borrowing through a deterministic protocol.

5. **How It Works**
   - 21-state FSM, fixed 64-byte frame, DEGR trust, SVD anomaly gate, correction filters.

6. **Product Demo**
   - Show correction, relay, borrow, and dashboard.

7. **Validation**
   - 273/273 C++ tests, Python integration tests, 94.3% RMSE improvement, 85.6% under 10% packet loss.

8. **Technical Feasibility**
   - 437 MHz UHF, GMSK, Conv+RS, link budget, low energy overhead.

9. **Impact**
   - Mission life, replacement cost, launch mass, CO2, data continuity.

10. **Market**
   - CubeSat operators, universities, Earth observation, mission assurance, integrators.

11. **Business Model**
   - Licensing, toolkit, embedded module, open-core services.

12. **Roadmap and Ask**
   - Hardware-in-the-loop, mission partner, flight demonstration.

## Pitch Talk Track

CubeSats are affordable, but they are still fragile. When one satellite loses a sensor, misses a ground pass, or starts drifting, the usual answer is to wait for ground contact or accept degraded mission data. That is slow, and for large constellations it becomes expensive.

SISP changes the operating model. It lets satellites cooperate autonomously. A satellite with a fault can ask nearby satellites for trusted readings, filter out bad inputs, and compute a corrected estimate. A satellite without ground visibility can relay data through a neighbor. A satellite with a failed sensor can borrow a healthy sensor stream from another node.

Technically, SISP is built as a deterministic C++ protocol stack with a 21-state finite state machine, compact 64-byte frames, DEGR trust weighting, SVD anomaly screening, and pluggable correction algorithms. It is designed for low-power CubeSat constraints and modeled around practical 437 MHz UHF links.

This is already implemented and tested. The repository documents 273 passing C++ tests, Python integration tests, 94.3% RMSE improvement in a 30-day correction scenario, 85.6% improvement under 10% packet loss, validated dual-PHY selection, and full relay recovery under corruption, reordering, and duplicate replay.

The impact is mission resilience. SISP can extend useful satellite life, reduce replacement launches, improve data continuity, and lower the environmental footprint of constellation operations. Our next step is hardware-in-the-loop validation with COTS radios and a mission partner.

## The Ask

For a hackathon or competition:

- Support to package the demo, dashboards, and protocol documentation into a polished technical showcase.
- Access to mentors in spacecraft communications, flight software, and mission assurance.
- Opportunity to present to smallsat operators or university CubeSat teams.

For a pilot partner:

- A flatsat or ground-test environment with representative telemetry and radio hardware.
- Engineering collaboration to adapt SISP to mission-specific sensors and operational constraints.
- Joint validation of correction, relay, and borrow scenarios.

For investors or grant reviewers:

- Funding for hardware-in-the-loop validation, SDR/COTS radio testing, CI hardening, and a flight demonstration proposal.
- Support to convert the validated prototype into a deployable SDK and mission-assurance toolkit.

## Risks and Mitigations

| Risk | Why It Matters | Mitigation |
|---|---|---|
| Not flight-qualified yet | Space software requires high assurance | Position current work as validated prototype; next step is HIL and flatsat |
| Energy assumptions vary by scenario | Pitch must be credible | Use transparent calculators and conservative headline numbers |
| UHF coordination constraints | Spectrum access depends on mission context | Keep PHY profile configurable and support mission-specific bands |
| Security and spoofing | Malicious frames could affect trust and correction | Add authentication, replay protection, and signed health beacons |
| Bad neighbors bias correction | Faulty readings can degrade estimates | Use DEGR weighting, SVD anomaly gating, NIS gates, and failure isolation |
| Scaling to dense constellations | Broadcast storms and contention | Bound neighbor count, add scheduling, and prioritize correction windows |

## What Makes SISP Defensible

SISP's defensibility is not one algorithm. It is the integration of several hard pieces:

- A service-level protocol for correction, relay, and sensor borrowing.
- Deterministic embedded-state-machine implementation.
- Continuous trust scoring rather than binary health labels.
- Anomaly detection integrated into the correction path.
- Physical-layer and energy modeling tied to concrete frame behavior.
- Extensive automated validation.
- A sustainability and mission-value dashboard that translates engineering performance into business and policy impact.

## Success Metrics

### Technical Metrics

- Correction RMSE improvement versus raw degraded sensor output.
- Relay completion rate under packet loss.
- Time to complete correction cycle.
- Energy per correction event.
- Energy per MiB relayed.
- Failure isolation correctness.
- State-machine coverage.
- BER/PER validation against theory.

### Business Metrics

- Mission life extension.
- Replacement satellites avoided.
- Launch mass avoided.
- Launch cost avoided.
- Data latency reduction.
- Sensor-years recovered.
- Partner missions engaged.

### Sustainability Metrics

- Replacement launches avoided.
- CO2 avoided.
- Satellite mass not launched.
- Reduction in premature mission disposal.

## Source Documentation

This pitch document is based on the existing project documentation:

- [README.md](../README.md)
- [README_00_OVERVIEW.md](README_00_OVERVIEW.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [SISP_KPI_SNAPSHOT.md](SISP_KPI_SNAPSHOT.md)
- [SISP_RESEARCH_PAPER.md](SISP_RESEARCH_PAPER.md)
- [README_03_CORRECTION_ALGORITHMS.md](README_03_CORRECTION_ALGORITHMS.md)
- [README_04_SIGNAL_PHYSICS.md](README_04_SIGNAL_PHYSICS.md)
- [README_05_ENERGY_STUDY.md](README_05_ENERGY_STUDY.md)
- [README_06_TEST_RESULTS.md](README_06_TEST_RESULTS.md)

## Closing Statement

SISP gives small satellites a cooperative survival layer. It transforms a constellation from a group of isolated spacecraft into a resilient network where satellites can share sensing, communication, and trust. The current prototype shows that this can be done with compact frames, low-power links, deterministic software, and measurable correction quality. With hardware validation and a mission partner, SISP can become a practical autonomy layer for the next generation of CubeSat constellations.
