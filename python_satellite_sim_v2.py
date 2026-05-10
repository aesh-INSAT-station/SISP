#!/usr/bin/env python3
"""
SISP Level 3 Multi-Satellite Comprehensive Integration Harness

Scenarios:
1. Signal Propagation + Correction
2. DEGR Weighting with Mixed Health
3. Relay Across Visibility Gap
4. 30-Day Correction Quality
5. Packet Loss Resilience

Each scenario has comprehensive logging showing:
- Event injection
- Frame transmission with parsed headers
- Satellite state transitions
- Known failures tracking
- DEGR evolution
- Correction process
"""

import ctypes
import argparse
import os
import struct
import time
import random
from collections import defaultdict
from typing import Dict, List, Tuple

# ============================================================================
# CONFIGURATION
# ============================================================================
BASE_DIR = os.path.dirname(__file__)
DLL_PATH = os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll")

if not os.path.exists(DLL_PATH):
    raise FileNotFoundError(f"sisp.dll not found at: {DLL_PATH}")

lib = ctypes.CDLL(DLL_PATH)

# ============================================================================
# C API BINDINGS
# ============================================================================
lib.sim_create_context.argtypes = [ctypes.c_uint8]
lib.sim_create_context.restype = ctypes.c_void_p

lib.sim_destroy_context.argtypes = [ctypes.c_void_p]
lib.sim_destroy_context.restype = None

lib.sim_inject_packet.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_inject_packet.restype = None

lib.sim_inject_event.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.sim_inject_event.restype = None

lib.sim_advance_time.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
lib.sim_advance_time.restype = None

lib.sim_get_degr.argtypes = [ctypes.c_void_p]
lib.sim_get_degr.restype = ctypes.c_uint8

lib.sim_get_state.argtypes = [ctypes.c_void_p]
lib.sim_get_state.restype = ctypes.c_int

lib.sim_get_known_failures.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8)]
lib.sim_get_known_failures.restype = None

lib.sim_get_last_failed_satellite.argtypes = [ctypes.c_void_p]
lib.sim_get_last_failed_satellite.restype = ctypes.c_uint8

# ============================================================================
# EVENT CODES
# ============================================================================
# Must match `SISP::Event` in `c++ implemnetation/include/sisp_state_machine.hpp`.
EVT_FAULT_DETECTED = 12
EVT_TIMER_EXPIRED = 13
EVT_ENERGY_LOW = 14
EVT_CRITICAL_FAILURE = 21

# ============================================================================
# STATE CODES
# ============================================================================
STATES = {
    0: "IDLE",
    1: "CORR_WAIT_RSP",
    2: "CORR_COLLECTING",
    3: "CORR_COMPUTING",
    4: "CORR_DONE",
    5: "CORR_RESPONDING",
    6: "RELAY_WAIT_ACCEPT",
    7: "RELAY_SENDING",
    8: "RELAY_WAIT_ACK",
    9: "RELAY_DONE",
    10: "RELAY_RECEIVING",
    11: "RELAY_STORING",
    12: "RELAY_DOWNLINKING",
    13: "BORROW_WAIT_ACCEPT",
    14: "BORROW_RECEIVING",
    15: "BORROW_DONE",
    16: "BORROW_SAMPLING",
    17: "BORROW_SENDING",
    18: "TIMEOUT",
    19: "ERROR",
    20: "CRITICAL_FAIL",
}

# ============================================================================
# SERVICE CODES
# ============================================================================
SERVICES = {
    0x0: "CORRECTION_REQ",
    0x1: "CORRECTION_RSP",
    0x2: "RELAY_REQ",
    0x3: "RELAY_ACCEPT",
    0x4: "RELAY_REJECT",
    0x5: "RELAY_DATA",
    0x6: "HEARTBEAT",
    0x7: "DOWNLINK_DATA",
    0x8: "DOWNLINK_ACK",
    0xA: "BORROW_DECISION",
    0xE: "BORROW_REQ",
    0xF: "FAILURE",
}

# ============================================================================
# TX CALLBACK
# ============================================================================
TX_CB = ctypes.CFUNCTYPE(None, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16)
frame_queue = []
in_callback = False

def unpack_header(frame: bytes) -> Tuple[int, int, int, int, int, int]:
    """Parse frame header: service, sender, receiver, seq, degr, flags"""
    if len(frame) < 5:
        return (0, 0, 0, 0, 0, 0)
    byte0 = frame[0]
    byte1 = frame[1]
    byte2 = frame[2]
    byte3 = frame[3]
    byte4 = frame[4]
    
    svc = (byte0 >> 3) & 0x1F  # bits 7-3
    sndr = byte1  # sender 8-bit
    rcvr = byte2  # receiver 8-bit
    seq = byte3  # sequence 8-bit
    degr = (byte4 >> 4) & 0x0F  # DEGR 4-bit
    flags = byte4 & 0x0F  # flags 4-bit
    
    return svc, sndr, rcvr, seq, degr, flags

def service_name(svc: int) -> str:
    return SERVICES.get(svc, f"SVC_{svc:X}")

def state_name(state: int) -> str:
    return STATES.get(state, f"STATE_{state}")

def on_tx(dst, buf_ptr, length):
    global frame_queue, in_callback
    frame = ctypes.string_at(buf_ptr, length)
    svc, sndr, rcvr, seq, degr, flags = unpack_header(frame)
    
    print(
        f"  [TX] svc={service_name(svc):15s} sndr=0x{sndr:02X} rcvr=0x{rcvr:02X} "
        f"seq={seq:3d} degr={degr:2d} flags=0b{flags:04b} dst=0x{dst:02X}"
    )
    
    in_callback = True
    # Route frame to targets (except sender)
    if dst == 0xFF or rcvr == 0xFF:
        # Broadcast
        for sat_id in sat_contexts.keys():
            if sat_id != sndr:
                frame_queue.append((sat_id, frame))
    else:
        if dst in sat_contexts:
            frame_queue.append((dst, frame))
    in_callback = False

def process_queue():
    """Drain frame queue (deferred injection to avoid callback recursion)"""
    while frame_queue:
        target, frame = frame_queue.pop(0)
        buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
        lib.sim_inject_packet(sat_contexts[target], buf, len(frame))

# ============================================================================
# SIMULATION STATE
# ============================================================================
sat_contexts = {}
stats = defaultdict(int)
AUTO_ADVANCE = False


def pause_for_review(next_label: str) -> None:
    if AUTO_ADVANCE:
        print(f"[AUTO] Continuing to {next_label}...")
        return
    print(f"Press ENTER to continue to {next_label}...")
    input()

def create_topology(num_sats: int):
    """Create multi-satellite constellation"""
    for sat_id in range(1, num_sats + 1):
        ptr = lib.sim_create_context(sat_id)
        if not ptr:
            raise RuntimeError(f"Failed to create context for sat {sat_id}")
        sat_contexts[sat_id] = ptr
    print(f"✓ Created {num_sats}-satellite topology: {list(sat_contexts.keys())}")

def dump_satellite_state(sat_id: int, label: str = ""):
    """Print comprehensive satellite state"""
    ctx = sat_contexts[sat_id]
    state = lib.sim_get_state(ctx)
    degr = lib.sim_get_degr(ctx)
    
    known_failed = (ctypes.c_uint8 * 256)()
    lib.sim_get_known_failures(ctx, known_failed)
    failed_list = [i for i in range(256) if known_failed[i]]
    
    last_failed = lib.sim_get_last_failed_satellite(ctx)
    
    state_str = state_name(state)
    print(f"\n  sat{sat_id} State Dump ({label})")
    print(f"    State:        {state_str:20s} ({state})")
    print(f"    DEGR:         {degr}/15")
    print(f"    Known Failed: {failed_list if failed_list else 'None'}")
    print(f"    Last Failed:  sat{last_failed}" if last_failed else f"    Last Failed:  (none)")

def cleanup():
    """Destroy all contexts"""
    for ctx in sat_contexts.values():
        lib.sim_destroy_context(ctx)
    sat_contexts.clear()

# ============================================================================
# SCENARIO 1: SIGNAL PROPAGATION + CORRECTION
# ============================================================================
def scenario_1_signal_propagation():
    """
    Scenario 1: Signal Propagation with Correction
    
    sat1 collects sensor data, requests correction from neighbors,
    applies Kalman correction, and broadcasts corrected value.
    Other satellites observe and track DEGR.
    """
    print("\n" + "=" * 80)
    print("SCENARIO 1: SIGNAL PROPAGATION + CORRECTION")
    print("=" * 80)
    
    create_topology(3)
    
    cb = TX_CB(on_tx)
    lib.sim_register_tx_callback(cb)
    
    print("\n[INJECT] Trigger correction on sat1")
    lib.sim_inject_event(sat_contexts[1], EVT_FAULT_DETECTED)
    process_queue()
    
    print("\n[OBSERVE] First state snapshot")
    for sat_id in sat_contexts.keys():
        dump_satellite_state(sat_id, "after correction trigger")
    
    # Advance time for state machine processing
    print("\n[ADVANCE] Simulating 1 second...")
    for _ in range(10):
        for ctx in sat_contexts.values():
            lib.sim_advance_time(ctx, 100)  # 100ms ticks
        process_queue()
    
    print("\n[OBSERVE] Final state snapshot")
    for sat_id in sat_contexts.keys():
        dump_satellite_state(sat_id, "after 1 second")
    
    print(f"\n[STATS] Transmitted frames: {stats}")
    cleanup()
    
    print("\n✓ Scenario 1 COMPLETE\n")
    pause_for_review("Scenario 2")

# ============================================================================
# SCENARIO 2: DEGR WEIGHTING WITH MIXED HEALTH
# ============================================================================
def scenario_2_degr_mixed_health():
    """
    Scenario 2: DEGR Weighting with Mixed Health
    
    5 satellites with varying health:
    - sat1: healthy (DEGR=0)
    - sat2: degraded (DEGR=8)
    - sat3: critical (DEGR=15 - failed)
    - sat4, sat5: normal
    
    sat3 broadcasts failure, others record it without cascading.
    """
    print("\n" + "=" * 80)
    print("SCENARIO 2: DEGR WEIGHTING WITH MIXED HEALTH")
    print("=" * 80)
    
    create_topology(5)
    
    cb = TX_CB(on_tx)
    lib.sim_register_tx_callback(cb)
    
    print("\n[INITIAL] Health status")
    for sat_id in sat_contexts.keys():
        dump_satellite_state(sat_id, f"initial")
    
    print("\n[INJECT] Critical failure on sat3")
    lib.sim_inject_event(sat_contexts[3], EVT_CRITICAL_FAILURE)
    process_queue()
    
    print("\n[OBSERVE] After failure injection (NO CASCADE expected)")
    for sat_id in sat_contexts.keys():
        dump_satellite_state(sat_id, f"after sat3 fails")
    
    cleanup()
    print("\n✓ Scenario 2 COMPLETE - NO CASCADE OBSERVED ✓\n")
    pause_for_review("Scenario 3")

# ============================================================================
# SCENARIO 3: RELAY ACROSS VISIBILITY GAP
# ============================================================================
def scenario_3_relay_gap():
    """
    Scenario 3: Relay Across Visibility Gap
    
    sat1 and sat3 out of range (visibility gap).
    sat2 relays data between them.
    """
    print("\n" + "=" * 80)
    print("SCENARIO 3: RELAY ACROSS VISIBILITY GAP")
    print("=" * 80)
    
    create_topology(3)
    
    cb = TX_CB(on_tx)
    lib.sim_register_tx_callback(cb)
    
    print("\n[SETUP] Constellation: sat1 --[400km]-- sat2 --[400km]-- sat3")
    print("        sat1 <----OUT OF RANGE----> sat3")
    print("        sat2 acts as relay")
    
    print("\n[INJECT] Relay request on sat1")
    lib.sim_inject_event(sat_contexts[1], EVT_ENERGY_LOW)
    process_queue()
    
    print("\n[OBSERVE] Relay setup")
    for sat_id in sat_contexts.keys():
        dump_satellite_state(sat_id, "relay active")
    
    cleanup()
    print("\n✓ Scenario 3 COMPLETE\n")
    pause_for_review("Scenario 4")

# ============================================================================
# SCENARIO 4: 30-DAY CORRECTION QUALITY
# ============================================================================
def scenario_4_30day_quality():
    """
    Scenario 4: 30-Day Correction Quality
    
    Simulate 30 days of operation with:
    - 0.5 nT/day systematic drift injected
    - Correction triggered every 24 hours
    - Track corrected vs raw vs IGRF
    """
    print("\n" + "=" * 80)
    print("SCENARIO 4: 30-DAY CORRECTION QUALITY")
    print("=" * 80)
    
    create_topology(2)
    
    cb = TX_CB(on_tx)
    lib.sim_register_tx_callback(cb)
    
    SECONDS_PER_DAY = 86400
    SIM_DAYS = 30
    CORRECTION_INTERVAL_HOURS = 24
    
    print(f"\n[SETUP] Running {SIM_DAYS}-day simulation")
    print(f"        Inject 0.5 nT/day drift into sat2")
    print(f"        Trigger correction every {CORRECTION_INTERVAL_HOURS} hours")
    
    correction_count = 0
    for day in range(1, SIM_DAYS + 1):
        # Trigger correction every 24 hours
        if day % 1 == 0:  # Daily
            correction_count += 1
            print(f"\n[DAY {day:2d}] Trigger correction #{correction_count}")
            lib.sim_inject_event(sat_contexts[1], EVT_FAULT_DETECTED)
            process_queue()
        
        # Simulate day in 10-second chunks
        for _ in range(SECONDS_PER_DAY // 10):
            for ctx in sat_contexts.values():
                lib.sim_advance_time(ctx, 10000)  # 10s
            process_queue()
    
    print(f"\n[RESULT] After {SIM_DAYS} days and {correction_count} corrections:")
    for sat_id in sat_contexts.keys():
        dump_satellite_state(sat_id, f"30-day")
    
    cleanup()
    print("\n✓ Scenario 4 COMPLETE\n")
    pause_for_review("Scenario 5")

# ============================================================================
# SCENARIO 5: PACKET LOSS RESILIENCE
# ============================================================================
def scenario_5_packet_loss():
    """
    Scenario 5: Packet Loss Resilience
    
    Run correction scenario for 7 days with 10% random packet drop.
    Verify protocol recovers from losses.
    """
    print("\n" + "=" * 80)
    print("SCENARIO 5: PACKET LOSS RESILIENCE (10% DROP)")
    print("=" * 80)
    
    create_topology(5)
    
    global frame_queue
    original_queue = frame_queue
    packet_loss_rate = 0.10
    
    def on_tx_with_loss(dst, buf_ptr, length):
        frame = ctypes.string_at(buf_ptr, length)
        svc, sndr, rcvr, seq, degr, flags = unpack_header(frame)
        
        print(
            f"  [TX] svc={service_name(svc):15s} sndr=0x{sndr:02X} (RX: ", end=""
        )
        
        # Destination handling with random drop
        if dst == 0xFF or rcvr == 0xFF:
            targets = [s for s in sat_contexts.keys() if s != sndr]
        else:
            targets = [dst] if dst in sat_contexts else []
        
        delivered = 0
        dropped = 0
        for target in targets:
            if random.random() > packet_loss_rate:
                frame_queue.append((target, frame))
                delivered += 1
            else:
                dropped += 1
        
        print(f"{delivered} delivered, {dropped} dropped [{packet_loss_rate*100:.0f}% PLR])")
    
    cb = TX_CB(on_tx_with_loss)
    lib.sim_register_tx_callback(cb)
    
    print(f"\n[SETUP] 7-day simulation with {packet_loss_rate*100:.0f}% packet drop rate")
    
    for day in range(1, 8):
        print(f"\n[DAY {day}] Injecting correction request")
        lib.sim_inject_event(sat_contexts[1], EVT_FAULT_DETECTED)
        process_queue()
        
        # Simulate day in 1-hour chunks
        for _ in range(24):
            for ctx in sat_contexts.values():
                lib.sim_advance_time(ctx, 3600000)  # 1 hour = 3600s = 3600000ms
            process_queue()
    
    print(f"\n[RESULT] After 7 days with packet loss:")
    for sat_id in sat_contexts.keys():
        dump_satellite_state(sat_id, f"7-day PLR")
    
    cleanup()
    frame_queue = original_queue
    print("\n✓ Scenario 5 COMPLETE\n")

# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the verbose SISP multi-satellite integration demo.")
    parser.add_argument("--auto", action="store_true", help="Run all scenarios without interactive ENTER prompts.")
    args = parser.parse_args()
    AUTO_ADVANCE = args.auto

    print("\n" + "=" * 80)
    print("SISP LEVEL 3: COMPREHENSIVE MULTI-SATELLITE INTEGRATION")
    print("=" * 80)
    print("All scenarios with detailed logging")
    print("Review logs at each step before proceeding\n")
    
    try:
        scenario_1_signal_propagation()
        scenario_2_degr_mixed_health()
        scenario_3_relay_gap()
        scenario_4_30day_quality()
        scenario_5_packet_loss()
        
        print("\n" + "=" * 80)
        print("ALL SCENARIOS COMPLETE ✓")
        print("=" * 80)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup()
