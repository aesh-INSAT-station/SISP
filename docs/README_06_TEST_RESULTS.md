# Test Results — Extracted Logs and Metrics

All logs are in `logs/`. This file summarizes the best results from each test category.

---

## C++ Test Suite — 273/273 PASS

**Run:** `c++ implemnetation/build/Release/test_runner.exe`  
**Log:** `logs/cpp_tests_20260510_200408.log`

| Group | Tests | Pass | Key coverage |
|---|---|---|---|
| Encoder / Decoder | 70 | **70** | All 16 SVC codes, checksum detection, payload round-trip, float/timestamp fidelity |
| Payload Codec | 65 | **65** | All 13 service payload types (CorrectionReq/Rsp, RelayReq/Decision, DownlinkData/Ack, Status, Heartbeat, Failure, BorrowReq/Decision) |
| 512-bit Frame Pipeline | 21 | **21** | TCP-mode, UDP-relay-mode, multithread pipeline, heartbeat/status state updates |
| State Machine | 38 | **38** | IDLE transitions, RSP collection, timer handling, DEGR weighting, relay paths, out-of-order fragment recovery |
| DEGR Computation | 20 | **20** | k-factor, SVD residual, age, orbit error; clamping at 0 and 15 |
| Protocol Simulation | 25 | **25** | Single-node correction, relay handshake, heartbeat listeners, filter plugins, error frames |
| Level 2 State Machine | 34 | **34** | SM-01 through SM-12 (full matrix: correction, relay, borrow, failure, reset) |
| **TOTAL** | **273** | **273** | |

### Notable C++ Results

**Failure isolation (SM-07):**
```
PASS: SM-07: Any state + CRITICAL_FAILURE → CRITICAL_FAIL (self)
PASS: sat3,4,5 record sat2 failed but DON'T cascade to CRITICAL_FAIL
```

**Out-of-order fragment recovery (SM-06):**
```
PASS: Fragment bitmask tracks all required fragments despite out-of-order delivery
PASS: Recovered message length matches full multi-fragment payload
PASS: Recovered message bytes match expected payload after sequencing recovery
```

**DEGR weighting (SM-03):**
```
PASS: SM-03: Healthy DEGR=0 has higher weight than DEGR=14
PASS: SM-03: Poor health weight is very low (clamped at 0.05)
PASS: SM-03: Corrected value dominated by healthy satellite
```

---

## Python Test Suite — All Pass

**Run:** `PYTHONIOENCODING=utf-8 python all_tests/<test>.py`  
**Log:** `logs/python_tests_20260510_195920.log`

---

### Monte Carlo BER Validation (`validate_bpsk_awgn.py`)

500,000-bit BPSK AWGN simulation:

| Eb/N0 (dB) | Theory | Simulation | Error |
|---|---|---|---|
| 0 | 7.865×10⁻² | 7.897×10⁻² | 0.4% |
| 2 | 3.751×10⁻² | 3.707×10⁻² | 1.2% |
| 4 | 1.250×10⁻² | 1.247×10⁻² | 0.2% |
| 6 | 2.388×10⁻³ | 2.448×10⁻³ | 2.5% |
| 8 | 1.909×10⁻⁴ | 1.820×10⁻⁴ | 4.7% |
| 10 | 3.872×10⁻⁶ | 0 | — |

**Verdict:** BER implementation validated. All values within expected Monte Carlo variance.

---

### Dual-PHY 437 MHz (`test_dual_phy_437.py`) — 8/8 PASS

```
PASS  CORRECTION frames captured
PASS  All CORRECTION frames use PHY=CTRL_NARROW (0x00)
PASS  FAILURE frames captured
PASS  All FAILURE frames use PHY=CTRL_NARROW (0x00)
PASS  Relay REQ/ACCEPT/REJECT use CTRL_NARROW
PASS  DOWNLINK_DATA frames present
PASS  All frames have valid PHY profile (0 or 1)
PASS  No control-service frame uses PHY=BULK_WIDE
```

Frame-level result:
```
svc=CORRECTION_REQ  sndr=1 rcvr=255 phy=CTRL_NARROW
svc=CORRECTION_RSP  sndr=2 rcvr=1   phy=CTRL_NARROW
svc=RELAY_REQ       sndr=1 rcvr=255 phy=CTRL_NARROW
svc=RELAY_ACCEPT    sndr=2 rcvr=1   phy=CTRL_NARROW
svc=DOWNLINK_DATA   sndr=1 rcvr=2   phy=BULK_WIDE     ← correct upgrade
```

---

### No-Cascade Failures (`test_no_cascade.py`) — PASS

```
sat1: state=CRITICAL_FAIL   degr=15 known_failed=[2]
sat2: state=CRITICAL_FAIL   degr=15 known_failed=[1]
sat3: state=IDLE            degr= 0 known_failed=[1, 2]
sat4: state=IDLE            degr= 0 known_failed=[1, 2]
sat5: state=IDLE            degr= 0 known_failed=[1, 2]

TEST PASSED: No cascading failures
```

---

### Borrow Addressing Flow (`test_borrow_addressing_flow.py`) — PASS

Two cases tested (multiple answers, and second answer dropped):

```
BORROW_REQ uses broadcast target 0xFF
BORROW_DECISION uses unicast target sat1
DOWNLINK_DATA comes from accepted sat2 to sat1

Case 1: Borrower receives sat2 payload (first responder)
Case 2: sat3 answer dropped at network — sat2 still wins

PASS: both cases verify unicast addressing after acceptance
```

---

### Relay Text Resilience (`test_relay_text_resilience.py`) — PASS

Multi-fragment relay with controlled failures:

```
Injection plan:
  Step 1: Corrupted mid fragment idx=1 (checksum drop)
  Step 2: Valid tail fragment idx=2 (out-of-order)
  Step 3: Valid head fragment idx=0
  Step 4: Valid mid fragment idx=1 (retry)
  Step 5: Duplicate replay mid idx=1 (dropped by replay protection)

Recovered text length: 109/109 bytes
PASS: Multi-fragment text relinked after checksum drop, out-of-order, and duplicate replay
```

---

### Kalman Correction Quality (`test_kalman_gaussian_3sat.py`)

Ground truth: $(42.000,\; -17.500,\; 9.250)$

**Profile: Nominal noise (σ=2.0, 20 rounds)**

| Metric | Value |
|---|---|
| Avg raw error | 2.511 |
| Avg corrected error | 1.464 |
| Steady-state raw error | 2.502 |
| **Steady-state corrected** | **1.304** |
| **Improvement** | **47.9%** |

**Profile: Large fault (σ=25.0, 30 rounds)**

| Metric | Value |
|---|---|
| Avg raw error | 25.93 |
| Avg corrected error | 9.41 |
| Steady-state raw error | 22.71 |
| **Steady-state corrected** | **8.47** |
| **Improvement** | **62.7%** |

---

### Algorithm Comparison Benchmark (`test_noise_weighting_and_algorithms.py`)

90 rounds, 4 responders, inverse-error DEGR, steady-state metrics:

#### Balanced neighbourhood (all sensors similar quality)

| σ | Algorithm | Raw err | Corr err | Gain |
|---|---|---|---|---|
| 2 | Kalman | 2.194 | 1.079 | **1.12** |
| 2 | Hybrid | 2.194 | 1.032 | **1.16** |
| 2 | Weighted Median | 2.194 | 2.338 | −0.14 |
| 20 | Kalman | 21.73 | 9.40 | **12.3** |
| 20 | Hybrid | 21.73 | 9.58 | **12.2** |
| 20 | Weighted Median | 21.73 | 21.18 | 0.54 |
| 60 | Kalman | 66.47 | 33.6 | **32.8** |
| 60 | Hybrid | 66.47 | 40.0 | 26.5 |
| 60 | Weighted Median | 66.47 | 78.8 | **−12.3** |

#### One healthy + one broken responder

| σ | Algorithm | Gain |
|---|---|---|
| 5 | Kalman | 2.27 |
| 5 | Hybrid | **2.83** |
| 40 | Kalman | **15.0** |
| 40 | Hybrid | 14.1 |
| 60 | Kalman | 27.3 |
| 60 | Hybrid | **28.7** |

#### Outlier stress scenarios

| Scenario | Best algorithm | Gain |
|---|---|---|
| Burst 5% heavy | NIS-Gated Kalman | **9.63** |
| Burst 15% moderate | NIS-Gated Kalman | **13.26** |
| Persistent bias (peer 3) | Hybrid | **21.33** |
| Mixed spike+drift | Hybrid | **13.89** |

#### DEGR model sensitivity (σ=40, mixed quality)

| DEGR model | Corrected error | Gain |
|---|---|---|
| inverse_error | **19.06** | **22.54** |
| neutral | 22.47 | 19.14 |
| proportional_error | 27.85 | 13.75 |

**Recommended:** inverse_error + Hybrid filter.

---

### Integration Matrix (`test_integration_matrix_it02_it03_it05_it06.py`) — ALL PASS

**IT-02: DEGR weighting with mixed health**
```
bad_weight=0.067, dist_to_healthy=1.146, dist_to_bad=51.568
PASS: degraded satellite contributes 14.6× less than healthy peer
```

**IT-03: Relay across visibility gap**
```
PASS: sat2 relay path established through sat4 with payload buffered
```

**IT-05: 30-day correction quality**

| | RMSE |
|---|---|
| Raw (no correction) | 8.909 |
| Kalman corrected | **0.504** |
| **Improvement** | **94.3%** |

**IT-06: Packet loss resilience (10% drop, 7 days, 5 satellites)**

| | RMSE |
|---|---|
| Raw | 8.290 |
| Corrected | **1.197** |
| **Improvement** | **85.6%** |
| Completion | 7/7 days |

---

## Runtime Performance

From `test_noise_weighting_and_algorithms.py` runtime budget check:

```
rounds=500  sigma=30.0  elapsed=0.004s  avg=0.009 ms/round  corrected_ss=15.638
```

The correction layer processes 500 rounds in 4 ms on a laptop CPU — suitable for RTOS targets running at 100 Hz.

---

## Summary: Best Results Across All Tests

| Claim | Evidence | Value |
|---|---|---|
| C++ correctness | 273/273 unit tests | **100% pass** |
| BER accuracy | Monte Carlo 500k bits | <5% relative error |
| 30-day RMSE improvement | IT-05 | **94.3%** |
| Packet-loss resilience | IT-06 (10% PLR) | **85.6% improvement** |
| Dual-PHY correctness | test_dual_phy_437 | **8/8 assertions** |
| Algorithm speed | 500 rounds | **0.009 ms/round** |
| Failure isolation | test_no_cascade | **0 cascades** |
| Multi-fragment relay | test_relay_text_resilience | **109/109 bytes** |
