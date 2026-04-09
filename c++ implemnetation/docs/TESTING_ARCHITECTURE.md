# SISP Protocol Testing Architecture

## Overview

The SISP protocol is tested at multiple architectural levels, with a clear separation between **transport/protocol logic** and **correction algorithms**.

### Testing Layers

```
┌─────────────────────────────────────────────────────────┐
│         Protocol Simulation Tests (Level 3)             │
│  Multi-node scenarios, state transitions, relay paths   │
└─────────────────────────────────────────────────────────┘
                            ▲
                            │
┌─────────────────────────────────────────────────────────┐
│         State Machine + Codec Tests (Level 2)           │
│  Frame encode/decode, payload serialization, transitions│
└─────────────────────────────────────────────────────────┘
                            ▲
                            │
┌─────────────────────────────────────────────────────────┐
│         Unit Tests + DEGR Tests (Level 1)              │
│  Encoder/decoder basics, DEGR scoring, component logic  │
└─────────────────────────────────────────────────────────┘
```

---

## Level 1: Unit & Component Tests

**Files:** `test_encode_decode.cpp`, `test_degr.cpp`, `test_payload_codec.cpp`

**Coverage:**
- Packet header encode/decode
- CRC-8/MAXIM checksum validation
- All typed payload serialization (CorrectionRsp, RelayReq, etc.)
- DEGR scoring logic (k-score, SVD residual, age, orbit error)
- Individual component correctness

**Key Invariant:** Each protocol data type roundtrips correctly through binary encoding.

---

## Level 2: State Machine & Frame Pipeline Tests

**Files:** `test_state_machine.cpp`, `test_frame_pipeline.cpp`

**Coverage:**
- State machine transitions (IDLE → CORR_WAIT_RSP → CORR_COLLECTING → CORR_COMPUTING → IDLE, etc.)
- 512-bit fixed frame encode/decode (TCP-like and UDP-like modes)
- Transport metadata preservation (session IDs, ACK sequences, relay parameters)
- Event dispatching and timer management
- Multithreaded producer/consumer frame pipeline

**Key Invariant:** State transitions follow the defined state diagram; frames encode/decode without loss of information.

---

## Level 3: Protocol Simulation Tests

**File:** `test_protocol_simulation.cpp`

**Scenarios:**

### 1. **Single-Node Correction Flow**
   - Node detects fault → enters CORR_WAIT_RSP
   - Collects responses from neighbors (with weights based on peer DEGR)
   - Timer fires → CORR_COMPUTING state
   - Calls pluggable correction filter
   - Verifies corrected value is computed
   
   **Validates:** Protocol doesn't care which correction algorithm is used; only that inputs are collected and output is ready.

### 2. **Multi-Node Relay Exchange**
   - Requester (energy-low) → RELAY_WAIT_ACCEPT
   - Provider receives relay request
   - Provider transitions to RELAY_RECEIVING
   - Request metadata (fragment count, window) is stored
   
   **Validates:** Relay negotiation works across node boundaries.

### 3. **Heartbeat Broadcast**
   - Announcer broadcasts heartbeat to multiple listeners
   - Each listener receives independently
   - Heartbeat payload (energy, DEGR, uptime) is parsed correctly
   
   **Validates:** Broadcast delivery and stateless reception works.

### 4. **Pluggable Correction Algorithms**
   - Node1 configured with WeightedMedianFilter
   - Node2 configured with KalmanFilter
   - Both independently process correction workflow
   
   **Validates:** Protocol layer is agnostic to correction implementation; algorithms can be swapped at runtime via `StateMachine::set_correction_filter()`.

### 5. **Error Handling**
   - Corrupted packet (checksum mismatch) is rejected
   - Invalid payloads do not corrupt state
   
   **Validates:** Protocol is robust to malformed inputs.

### 6. **State Recovery (RESET)**
   - Node in CORR_WAIT_RSP receives RESET event
   - Immediately returns to IDLE
   - Response collection state is cleared
   
   **Validates:** RESET works from any state and cleanly reinitializes context.

---

## Correction Module Architecture

The correction logic is **completely decoupled** from the protocol layer.

### Base Class

```cpp
class CorrectionFilter {
public:
    virtual bool apply(const CorrectionInput& input, CorrectionOutput& output) = 0;
};
```

### Provided Implementations

1. **`WeightedMedianFilter`**
   - Per-axis weighted median computation
   - Robust outlier rejection
   - Real-time capable

2. **`KalmanFilter`**
   - Lightweight 1D Kalman per axis
   - Temporal smoothing
   - Configurable process/measurement noise

3. **`HybridFilter`**
   - Weighted median + Kalman smoothing
   - Combines robustness with smoothing
   - Production-ready

### Integration

The state machine simply invokes the filter when needed:

```cpp
StateMachine::set_correction_filter(ctx, &my_filter);
// Later, during correction computation:
ctx.correction_filter->apply(weighted_readings, output);
```

**Protocol responsibility ends:** Provide collected readings with weights.  
**Filter responsibility begins:** Compute corrected value.

---

## Test Execution

```bash
cd c++ implemnetation/build
cmake --build . --config Release --target test_runner
./Release/test_runner.exe
```

**Expected Output:**
```
===== SISP Protocol Unit Tests =====
--- Encoder/Decoder Tests ---
Encode/Decode: 58/58
--- Payload Codec Tests ---
Payload Codec: 65/65
--- 512-bit Frame Pipeline Tests ---
Frame Pipeline: 21/21
--- State Machine Tests ---
State Machine: 25/25
--- DEGR Computation Tests ---
DEGR Computation: 20/20
--- Protocol Simulation Tests ---
Protocol Simulation: 23/23

===== Summary =====
Executed tests: 212
Failed groups: 0
```

---

## Adding New Correction Algorithms

To plug in a new correction algorithm at test or runtime:

1. **Inherit from `CorrectionFilter`:**
   ```cpp
   class MyFilter : public CorrectionFilter {
   public:
       bool apply(const CorrectionInput& input, CorrectionOutput& output) override {
           // Your algorithm here
       }
   };
   ```

2. **Register with state machine:**
   ```cpp
   MyFilter my_filter;
   StateMachine::set_correction_filter(ctx, &my_filter);
   ```

3. **Run tests:**
   - The protocol layer tests remain unchanged
   - Your filter will be invoked during CORR_COMPUTING state
   - State machine continues to IDLE on CORRECTION_DONE event

---

## Data Flow: Request → Response → Correction

```
┌─ Requester Node ──────────────────────────────────────────────────┐
│                                                                    │
│  FAULT_DETECTED                                                   │
│       ↓                                                            │
│  Send CORRECTION_REQ (broadcast)                                  │
│       ↓                                                            │
│  State: CORR_WAIT_RSP                                            │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

              ↓ Network ↓

┌─ Provider Nodes (0x10, 0x11, ...) ────────────────────────────────┐
│                                                                    │
│  RX_CORRECTION_REQ                                                │
│       ↓                                                            │
│  Read sensor (SENSOR_READ_DONE event)                             │
│       ↓                                                            │
│  Send CORRECTION_RSP with reading + DEGR weight                  │
│       ↓                                                            │
│  State: stays IDLE (unsolicited service)                         │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

              ↓ Network ↓

┌─ Requester Node ──────────────────────────────────────────────────┐
│                                                                    │
│  RX_CORRECTION_RSP (from 0x10)                                    │
│       ↓                                                            │
│  Collect: readings[0] = (100, 200, 300)                          │
│           weight[0] = 1.0 - (DEGR[0] / 15.0)                     │
│       ↓                                                            │
│  State: CORR_COLLECTING                                          │
│                                                                    │
│  RX_CORRECTION_RSP (from 0x11)                                    │
│       ↓                                                            │
│  Collect: readings[1] = (110, 210, 310)                          │
│           weight[1] = 1.0 - (DEGR[1] / 15.0)                     │
│       ↓                                                            │
│  State: CORR_COLLECTING (no change)                              │
│                                                                    │
│  TIMER_EXPIRED (5s collection window)                             │
│       ↓                                                            │
│  State: CORR_COMPUTING                                           │
│                                                                    │
│  action_run_kalman():                                             │
│    CorrectionInput {readings[0..1], weight[0..1], count=2}       │
│       ↓                                                            │
│    correction_filter->apply(input, output)                        │
│       ↓                                                            │
│    ctx.corrected_value = output.corrected;  // (x, y, z)         │
│       ↓                                                            │
│  CORRECTION_DONE (internal event)                                 │
│       ↓                                                            │
│  State: IDLE                                                      │
│                                                                    │
│  corrected_value is ready for next phase (e.g., consensus)       │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## Protocol Invariants

1. **No correction algorithm dependency:** The protocol layer never calls a specific filter; it only dispatches an abstract interface.
2. **Weight preservation:** DEGR from peer headers is converted to filter weight without loss.
3. **State isolation:** Each node's context is independent; multinode scenarios work correctly.
4. **Deterministic output:** Given the same inputs, the same correction algorithm produces the same output.
5. **Error robustness:** Malformed packets, timeouts, and missing responses do not corrupt protocol state.

---

## Future Extensions

- **Security/Encryption:** Add security prefix validation (currently placeholder).
- **Relay Fragment Accumulation:** Implement proper reassembly buffer management.
- **Borrow Service Completion:** Implement sensor borrowing state machine transitions.
- **Neighbor Table:** Populate actual neighbor DEGR scores instead of placeholder zeros.
- **Different Kernels:** Test with different RTOS platforms (RTEMS, VxWorks, FreeRTOS).
