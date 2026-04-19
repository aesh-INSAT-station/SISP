# SISP Signal Testing and Simulation Roadmap

## Purpose
This document consolidates the physical-layer model from mathsignal.txt into an actionable testing roadmap for simulation Module M3 and protocol validation.

## 1) Signal and channel model to implement

### 1.1 Transmit waveform
- Modulation: BPSK
- Carrier: 26 GHz (Ka band)
- Bit rate: 100 kbps baseline
- Symbol model:
  - passband: s(t) = sqrt(2*Ptx) * b(t) * cos(2*pi*fc*t + phi0)
  - baseband equivalent: s_tilde(t) = sqrt(Ptx) * b(t) * exp(j*phi0)

### 1.2 Path loss
- Friis equation with distance d and frequency fc
- Baseline reference: 1000 km at 26 GHz gives approximately 144.8 dB free-space loss
- Validation rule: doubling distance adds ~6 dB loss

### 1.3 Doppler
- Use delta_f(t) = (fc/c) * d_dot(t) where d_dot is range rate from orbit propagator
- Baseline sanity: 1 km/s relative radial speed at 26 GHz gives ~86.7 kHz
- Include optional pre-compensation and residual Doppler mode

### 1.4 Thermal noise
- AWGN with N = k*Tsys*B
- Baseline: Tsys ~ 280 K, B = 100 kHz
- N0 = k*Tsys and N in dBm must be logged per run

## 2) Link budget and SNR checks

### 2.1 Per-link calculation
Compute and log:
- Ptx, Gtx, Grx, Lfs, pointing loss, N
- SNR in dB
- Eb/N0 in dB

### 2.2 Baseline acceptance
For baseline settings in mathsignal.txt:
- SNR and Eb/N0 should be near +17.3 dB at 1000 km with B=Rb=100 kHz
- At 1 MHz bandwidth, SNR should drop by ~10 dB

## 3) BER and coding simulation stack

### 3.1 Uncoded BPSK
- BER = Q(sqrt(2*Eb/N0))
- Generate BER vs Eb/N0 curve from 0 to 14 dB

### 3.2 Inner convolutional coding
- Rate 1/2, K=7 (133/171 octal)
- Soft-decision Viterbi decoding
- Compare coding gain to uncoded curve

### 3.3 Outer RS coding
- RS(255,223), t=16 symbols
- Estimate residual block error from byte error probability

### 3.4 Concatenated performance target
- Minimum viable Eb/N0 around 4.5 dB for correction-sized messages
- Track gap vs uncoded threshold (~8 dB) as coding gain indicator

## 4) PER testing by message type

### 4.1 Message classes
- Header only
- CORRECTION_REQ / CORRECTION_RSP
- RELAY_REQ
- BORROW_DATA

### 4.2 PER computation
- PER(L, pb) = 1 - (1 - pb)^L
- For small pb, verify PER ~ L*pb approximation

### 4.3 Expected behavior
- Large payload messages (e.g., borrow data) should degrade earlier with distance than correction messages
- This justifies relay usage for large payload transport

## 5) Required simulation outputs (M3)

### Plot 1: BER vs Eb/N0
Curves:
- uncoded BPSK
- convolutional coded
- concatenated conv+RS

### Plot 2: SNR vs distance
Curves:
- Ka baseline
- optional UHF comparison

### Plot 3: PER vs distance by message type
Curves:
- correction-size packet
- relay-size packet
- borrow-data packet

## 6) Protocol-level integration with physical layer

### 6.1 Connect to existing protocol tests
Use these tests to map signal quality into protocol outcomes:
- all_tests/test_noise_weighting_and_algorithms.py
- all_tests/test_relay_text_resilience.py
- all_tests/test_full_message_propagation_sensor_correction.py
- all_tests/test_integration_matrix_it02_it03_it05_it06.py

### 6.2 End-to-end KPI set
Track per scenario:
- BER and PER
- correction steady-state error (raw vs corrected)
- relay completion ratio
- message latency and retry counts
- failure/cascade safety invariants

## 7) Implementation roadmap

### Phase A: Analytical baselines
- Implement closed-form BER/PER and link-budget calculators
- Verify numeric points from mathsignal.txt

### Phase B: Monte Carlo channel layer
- Build stochastic channel model with path loss, Doppler, AWGN
- Add coding chain toggles (uncoded / conv / conv+RS)

### Phase C: Protocol coupling
- Drive protocol tests with channel-derived packet corruption/loss probabilities
- Report protocol KPI degradation as a function of Eb/N0 and distance

### Phase D: Scale campaign
- Use all_tests/scale_testing/run_protocol_scale.py for repeatability tiers
- Add constellation-size parameterization in python_satellite_sim_v2.py for explicit N-satellite scaling

## 8) Suggested acceptance thresholds
- BER/PER curves numerically consistent with analytical references
- correction messages maintain PER < 1e-4 at target viable Eb/N0
- relay completion ratio remains above target under configured loss profile
- no unwanted failure cascades in stress scenarios

## 9) Immediate next actions
1. Add CSV export for BER/PER/SNR curves
2. Add a script that sweeps distance and bandwidth automatically
3. Link curve outputs into protocol scale reports for one unified benchmark package
