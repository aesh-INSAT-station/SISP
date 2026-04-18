# State Machine Complete Explanation

## Scope
This document explains the full SISP state machine as implemented in c++ implemnetation/src/sisp_state_machine.cpp and defined in c++ implemnetation/include/sisp_state_machine.hpp.

## Core model
- Dispatch table: g_trans[state][event]
- Transition tuple: next_state plus action function
- Default: unresolved transitions are null action with IDLE target, but null action means no transition is taken

## Global behavior
- RESET is defined as an escape path back to IDLE from every state
- CRITICAL_FAILURE transitions any state to CRITICAL_FAIL and broadcasts failure
- RX_FAILURE records foreign failures without forcing cascade

## Service domains and states

### A) Correction domain
States:
- IDLE
- CORR_WAIT_RSP
- CORR_COLLECTING
- CORR_COMPUTING
- CORR_RESPONDING

Flow:
1. FAULT_DETECTED in IDLE sends CORRECTION_REQ and enters CORR_WAIT_RSP
2. RX_CORRECTION_RSP collects responses in CORR_COLLECTING
3. TIMER_EXPIRED enters CORR_COMPUTING and runs correction filter
4. CORRECTION_DONE returns to IDLE

Responder side:
- RX_CORRECTION_REQ in IDLE enters CORR_RESPONDING and prepares response
- SENSOR_READ_DONE sends CORRECTION_RSP and returns to IDLE

Important details:
- correction timeout is absolute: now plus 5000 ms
- response uses own_reading in context
- peer DEGR maps to response weight with floor at 0.05

### B) Relay domain
States:
- RELAY_WAIT_ACCEPT
- RELAY_SENDING
- RELAY_WAIT_ACK
- RELAY_RECEIVING
- RELAY_STORING
- RELAY_DOWNLINKING
- RELAY_DONE

Requester flow:
1. ENERGY_LOW or GS_LOST sends RELAY_REQ and enters RELAY_WAIT_ACCEPT
2. RX_RELAY_ACCEPT enters RELAY_WAIT_ACK and action_send_frag transmits fragments
3. RX_DOWNLINK_ACK enters RELAY_DONE
4. TIMER_EXPIRED retries RELAY_REQ with retry budget

Receiver flow:
1. RX_RELAY_REQ enters RELAY_RECEIVING and sends RELAY_ACCEPT
2. RX_DOWNLINK_DATA enters RELAY_STORING and stores fragments
3. ALL_FRAGS_RCVD enters RELAY_DOWNLINKING
4. SENSOR_READ_DONE sends ACK and returns to IDLE

Important details:
- relay timeout is absolute: now plus 10000 ms
- RX_RELAY_REJECT path is no-op to IDLE, no reject echo loop
- fragment sending loops until frag_sent reaches frag_total
- fragment reassembly tracks mask and assembled length

### C) Borrow domain
States:
- BORROW_WAIT_ACCEPT
- BORROW_RECEIVING
- BORROW_DONE
- BORROW_SAMPLING
- BORROW_SENDING

Requester flow:
1. GS_VISIBLE sends BORROW_REQ and enters BORROW_WAIT_ACCEPT
2. RX_BORROW_DECISION enters BORROW_RECEIVING
3. RX_DOWNLINK_DATA stored while receiving
4. ALL_FRAGS_RCVD enters BORROW_DONE

Provider flow:
1. RX_BORROW_REQ enters BORROW_SAMPLING and sends BORROW_DECISION
2. SENSOR_READ_DONE enters BORROW_SENDING and sends borrowed data fragments
3. ALL_FRAGS_SENT enters BORROW_DONE

Important details:
- borrow timeout is absolute: now plus 15000 ms
- retry budget applies similarly to relay

### D) Failure handling
- CRITICAL_FAILURE: local node transitions to CRITICAL_FAIL and broadcasts FAILURE with DEGR 15
- RX_FAILURE: receiver records failed satellite in known_failed and stays in current state

This avoids cascading critical-state transitions while preserving network awareness.

## Timing semantics
Tick function checks absolute deadline:
- if timer_deadline_ms > 0 and now_ms >= timer_deadline_ms
- clear deadline
- dispatch TIMER_EXPIRED

This requires action functions to store absolute deadlines, not relative constants.

## Data paths and context fields
- correction: rsp_readings, rsp_weights, rsp_timestamps_ms, corrected_value, correction_filter
- relay: relay_buf, relay_buf_len, relay_rx_storage, frag_total, frag_sent, frag_rcvd_mask
- borrow: borrow_sensor, borrow_duration_s, last_borrow_decision
- health and trust: current_degr, neighbour_degr, known_failed, last_failed_satellite_id

## What to validate after changes
- no-cascade failure behavior
- relay multi-fragment send and reassembly with out-of-order delivery
- correction output non-zero when responses exist
- retry limits and timeout transitions
- state reset from non-IDLE paths

## Large-scale testing guide

### Objective
Stress protocol behavior across many satellites, long durations, and noisy links while tracking correctness and performance.

### Recommended dimensions
- constellation size: 10, 25, 50, 100 satellites
- simulation length: 1 day, 7 days, 30 days equivalent ticks
- packet loss: 0, 5, 10, 20 percent
- outlier profiles: burst, persistent bias, mixed spike plus drift
- topology: full mesh, ring, clustered relay hubs

### Baseline commands
- Python algorithm and outlier benchmark:
  c:/Users/HP/aesh/SISP/.venv/Scripts/python.exe all_tests/test_noise_weighting_and_algorithms.py
- Relay resilience:
  c:/Users/HP/aesh/SISP/.venv/Scripts/python.exe all_tests/test_relay_text_resilience.py
- Full propagation plus correction:
  c:/Users/HP/aesh/SISP/.venv/Scripts/python.exe all_tests/test_full_message_propagation_sensor_correction.py
- Multi-satellite harness:
  c:/Users/HP/aesh/SISP/.venv/Scripts/python.exe python_satellite_sim_v2.py

### Scale test phases
1. Correctness phase
- verify protocol invariants under low load
- assert no cascade and valid terminal states

2. Throughput phase
- increase nodes and events per tick
- measure queue depth, dropped frames, completion ratio

3. Resilience phase
- inject loss, corruption, and outliers
- compare corrected error and relay completion rate

4. Longevity phase
- run long horizon with periodic faults
- check for drift, deadlock, and retry storms

### Metrics to record
- correction RMSE and steady-state error per algorithm
- relay completion ratio and mean completion latency
- retransmission count and timeout frequency
- state occupancy distribution over time
- dropped frame count and duplicate suppression count

### Pass criteria template
- correction error gain over raw remains positive in all target scenarios
- relay completion ratio above threshold under target packet loss
- no uncontrolled cascade to CRITICAL_FAIL
- no unbounded queue growth or deadlock states
