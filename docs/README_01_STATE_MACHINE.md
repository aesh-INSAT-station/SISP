# State Machine Architecture

**Source files:**
- `c++ implemnetation/include/sisp_state_machine.hpp` — State/Event enums, Context struct, StateMachine class
- `c++ implemnetation/src/sisp_state_machine.cpp` — Transition table, action functions
- `c++ implemnetation/include/sisp_protocol.hpp` — Frame format, ServiceCode, PhyProfile

---

## Design Philosophy

The state machine is a **static, pre-allocated 21×24 transition table** (`g_trans[STATE_COUNT][EVT_COUNT]`). It is initialized exactly once at first dispatch and then treated as read-only. This means:

- **No heap allocation** during operation — suitable for RTOS targets with no dynamic memory.
- **O(1) dispatch** — look up `g_trans[state][event]`, call the action, update state. No dynamic dispatch.
- **Deterministic timing** — action functions are short, bounded, and have no blocking calls.

---

## States (21 total)

```
IDLE (0)                 — quiescent, ready for any event

── Correction requester ──────────────────────────────────────
CORR_WAIT_RSP (1)        — broadcast REQ sent, waiting for first RSP
CORR_COLLECTING (2)      — collecting RSPs from neighbours
CORR_COMPUTING (3)       — running correction filter (triggered by timer)
CORR_DONE (4)            — correction result available

── Correction responder ──────────────────────────────────────
CORR_RESPONDING (5)      — reading local sensor, will send RSP

── Relay sender ──────────────────────────────────────────────
RELAY_WAIT_ACCEPT (6)    — broadcast RELAY_REQ sent, waiting for ACCEPT
RELAY_SENDING (7)        — fragmenting and sending DOWNLINK_DATA
RELAY_WAIT_ACK (8)       — all frags sent, waiting for DOWNLINK_ACK
RELAY_DONE (9)           — relay complete

── Relay provider ────────────────────────────────────────────
RELAY_RECEIVING (10)     — received RELAY_ACCEPT, waiting for frags
RELAY_STORING (11)       — assembling fragments
RELAY_DOWNLINKING (12)   — forwarding assembled payload to ground

── Borrow requester ──────────────────────────────────────────
BORROW_WAIT_ACCEPT (13)  — broadcast BORROW_REQ sent
BORROW_RECEIVING (14)    — accepted, waiting for sensor data
BORROW_DONE (15)         — borrow complete

── Borrow provider ───────────────────────────────────────────
BORROW_SAMPLING (16)     — reading requested sensor
BORROW_SENDING (17)      — streaming data to requester

── Error / Failure ───────────────────────────────────────────
TIMEOUT (18)
ERROR (19)
CRITICAL_FAIL (20)       — satellite declared failed, DEGR=15
```

---

## Events (24 total)

| Code | Name | Source |
|---|---|---|
| 0 | `RX_CORRECTION_REQ` | Packet RX |
| 1 | `RX_CORRECTION_RSP` | Packet RX |
| 2 | `RX_RELAY_REQ` | Packet RX |
| 3 | `RX_RELAY_ACCEPT` | Packet RX |
| 4 | `RX_RELAY_REJECT` | Packet RX |
| 5 | `RX_DOWNLINK_DATA` | Packet RX |
| 6 | `RX_DOWNLINK_ACK` | Packet RX |
| 7 | `RX_STATUS_BROADCAST` | Packet RX |
| 8 | `RX_HEARTBEAT` | Packet RX |
| 9 | `RX_HEARTBEAT_ACK` | Packet RX |
| 10 | `RX_BORROW_REQ` | Packet RX |
| 11 | `RX_FAILURE` | Packet RX |
| **12** | **`FAULT_DETECTED`** | Internal (sensor layer) |
| **13** | **`TIMER_EXPIRED`** | Internal (RTOS tick) |
| **14** | **`ENERGY_LOW`** | Internal (power monitor) |
| 15 | `GS_VISIBLE` | Internal (orbit predictor) |
| 16 | `GS_LOST` | Internal |
| 17 | `ALL_FRAGS_SENT` | Internal |
| 18 | `ALL_FRAGS_RCVD` | Internal |
| 19 | `SENSOR_READ_DONE` | Internal |
| 20 | `CORRECTION_DONE` | Internal |
| **21** | **`CRITICAL_FAILURE`** | Internal (fault monitor) |
| 22 | `RESET` | External (ground command) |
| 23 | `RX_BORROW_DECISION` | Packet RX |

> **Warning:** Always use the exact integer codes above in Python harnesses. Common bug: using 10/11 for FAULT_DETECTED/ENERGY_LOW instead of 12/14.

---

## Key Transition Flows

### Correction (happy path)
```
IDLE → [FAULT_DETECTED=12]
  action: send CORRECTION_REQ (broadcast), timer = now + 5000 ms
  → CORR_WAIT_RSP

CORR_WAIT_RSP → [RX_CORRECTION_RSP]
  action: buffer reading + DEGR weight, rsp_count++
  → CORR_COLLECTING

CORR_COLLECTING → [TIMER_EXPIRED=13]
  action: run correction filter on buffered readings
  → CORR_COMPUTING

CORR_COMPUTING → [CORRECTION_DONE=20]
  action: (filter result available in ctx.corrected_value)
  → IDLE
```

### Failure isolation (NO cascade)
```
ANY_STATE → [RX_FAILURE=11]
  action: record ctx.known_failed[sender]=1, clear trust
  → SAME STATE  ← critical: no state change

ANY_STATE → [CRITICAL_FAILURE=21]
  action: ctx.current_degr = 15, broadcast FAILURE frame
  → CRITICAL_FAIL  ← only self-failure escalates
```

### Dual-PHY selection
```cpp
PhyProfile select_tx_phy(ctx, pkt, dst) {
    bool bulk = (pkt.svc == DOWNLINK_DATA || pkt.svc == DOWNLINK_ACK);
    if (!bulk || dst == BROADCAST) return CONTROL_437_NARROW;
    if (local supports BULK && active_bulk_phy == BULK && peer supports BULK)
        return BULK_437_WIDE;
    return CONTROL_437_NARROW;
}
```

PHY profile is stored in frame byte 8 by the encoder. Python can decode: `frame[8] & 0xFF` → 0 = CTRL_NARROW, 1 = BULK_WIDE.

---

## Context Structure (2 KB per satellite)

```cpp
struct Context {
    State    state;
    uint8_t  self_id, peer_id, seq, out_seq, current_degr;
    uint32_t timer_deadline_ms;
    uint8_t  retry_count, max_retries;         // default max=3

    // Neighbour tables (256 entries each)
    uint8_t  neighbour_degr[256];
    uint8_t  peer_friendly[256];
    uint8_t  peer_phy_cap_mask[256];           // for PHY negotiation

    // Correction buffer
    float    rsp_readings[8][3];               // up to 8 neighbours × (x,y,z)
    float    rsp_weights[8];
    uint8_t  rsp_count;
    float    corrected_value[3];

    // Relay buffer (3232 bytes)
    uint8_t  relay_tx_storage[RELAY_BUFFER_CAPACITY];
    uint8_t  relay_rx_storage[RELAY_BUFFER_CAPACITY];

    PhyProfile current_phy, active_bulk_phy, last_tx_phy;
    CorrectionFilter* correction_filter;       // pluggable, null = weighted average
};
```

---

## Python Simulation API

```python
import ctypes
lib = ctypes.CDLL("c++ implemnetation/build/bin/Release/sisp.dll")

ctx = lib.sim_create_context(sat_id)          # allocate context
lib.sim_inject_event(ctx, 12)                  # FAULT_DETECTED
lib.sim_inject_packet(ctx, buf, length)        # deliver a received frame
lib.sim_advance_time(ctx, ms)                  # advance timer (triggers TIMER_EXPIRED)
state = lib.sim_get_state(ctx)                 # read current state
lib.sim_destroy_context(ctx)                   # free

# Register TX callback to intercept all outgoing frames
TX_CB = ctypes.CFUNCTYPE(None, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16)
lib.sim_register_tx_callback(TX_CB(my_callback))
```

---

## Test Coverage

- **38 state machine unit tests** in `tests/test_state_machine.cpp`
- **34 Level-2 matrix tests** in `tests/test_comprehensive_matrix.cpp` (SM-01 through SM-12)
- **10 Python integration scenarios** in `all_tests/`

All 273 C++ tests pass. State machine is production-ready.
