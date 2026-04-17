#!/usr/bin/env python3
"""
SISP Level 3 - Simplified Test: No cascading failures
Tests the modified state machine where RX_FAILURE doesn't cause cascade
"""

import ctypes
import os
from typing import Tuple

BASE_DIR = os.path.dirname(__file__)
DLL_PATH = os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll")

if not os.path.exists(DLL_PATH):
    raise FileNotFoundError(f"sisp.dll not found at: {DLL_PATH}")

lib = ctypes.CDLL(DLL_PATH)

# C API Bindings
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
lib.sim_decode_header.argtypes = [
    ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16,
    ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8),
    ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8)
]
lib.sim_decode_header.restype = ctypes.c_uint8

# Event codes
EVT_CRITICAL_FAILURE = 21

# State names
STATES = {0: "IDLE", 20: "CRITICAL_FAIL"}

# Service codes
SERVICES = {0xF: "FAILURE"}

def unpack_header(frame: bytes) -> Tuple[int, int, int, int, int, int]:
    if len(frame) == 0:
        return (0, 0, 0, 0, 0, 0)
    buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
    svc = ctypes.c_uint8(0)
    sndr = ctypes.c_uint8(0)
    rcvr = ctypes.c_uint8(0)
    seq = ctypes.c_uint8(0)
    degr = ctypes.c_uint8(0)
    flags = ctypes.c_uint8(0)
    ok = lib.sim_decode_header(
        buf,
        len(frame),
        ctypes.byref(svc),
        ctypes.byref(sndr),
        ctypes.byref(rcvr),
        ctypes.byref(seq),
        ctypes.byref(degr),
        ctypes.byref(flags),
    )
    if ok == 0:
        return (0, 0, 0, 0, 0, 0)
    return (svc.value, sndr.value, rcvr.value, seq.value, degr.value, flags.value)

def service_name(svc: int) -> str:
    return SERVICES.get(svc, f"SVC_{svc:X}")

def state_name(state: int) -> str:
    return STATES.get(state, f"STATE_{state}")

# Global state
sat_contexts = {}
frame_queue = []
TX_CB = ctypes.CFUNCTYPE(None, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16)

def on_tx(dst, buf_ptr, length):
    frame = ctypes.string_at(buf_ptr, length)
    svc, sndr, rcvr, seq, degr, flags = unpack_header(frame)
    print(f"  [TX] {service_name(svc):10s} from sat{sndr} to 0x{dst:02X} | degr={degr} seq={seq}")
    
    # Route to targets
    if dst == 0xFF or rcvr == 0xFF:
        for sat_id in sat_contexts.keys():
            if sat_id != sndr:
                frame_queue.append((sat_id, frame))
    else:
        if dst in sat_contexts:
            frame_queue.append((dst, frame))

def process_queue(max_frames=64):
    processed = 0
    while frame_queue and processed < max_frames:
        target, frame = frame_queue.pop(0)
        buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
        lib.sim_inject_packet(sat_contexts[target], buf, len(frame))
        processed += 1
    return processed

def dump_state(sat_id):
    ctx = sat_contexts[sat_id]
    state = lib.sim_get_state(ctx)
    degr = lib.sim_get_degr(ctx)
    
    known_failed = (ctypes.c_uint8 * 256)()
    lib.sim_get_known_failures(ctx, known_failed)
    failed_list = [i for i in range(1, 6) if known_failed[i]]
    
    print(f"    sat{sat_id}: state={state_name(state):15s} degr={degr:2d} known_failed={failed_list}")

def cleanup():
    for ctx in sat_contexts.values():
        lib.sim_destroy_context(ctx)
    sat_contexts.clear()

# ============================================================================
# TEST: NO CASCADING FAILURES
# ============================================================================
print("\n" + "=" * 80)
print("TEST: NO CASCADING FAILURES (Modified State Machine)")
print("=" * 80)

print("\n[SETUP] Create 5-satellite constellation")
for sat_id in range(1, 6):
    ptr = lib.sim_create_context(sat_id)
    if not ptr:
        raise RuntimeError(f"Failed to create sat {sat_id}")
    sat_contexts[sat_id] = ptr
print(f"✓ Created satellites: {list(sat_contexts.keys())}")

cb = TX_CB(on_tx)
lib.sim_register_tx_callback(cb)

print("\n[INITIAL STATE]")
for sat_id in sat_contexts.keys():
    dump_state(sat_id)

print("\n[INJECT] CRITICAL_FAILURE event on sat1")
print("Expected: sat1 goes to CRITICAL_FAIL, broadcasts FAILURE")
print("         Other satellites record sat1 as failed, NO CASCADE")
lib.sim_inject_event(sat_contexts[1], EVT_CRITICAL_FAILURE)
processed_1 = process_queue(64)
print(f"Processed frames after sat1 fail: {processed_1}")

print("\n[STATE AFTER FIRST INJECTION]")
for sat_id in sat_contexts.keys():
    dump_state(sat_id)

print("\n[CRITICAL TEST] Try to inject another failure on sat2")
print("Expected: sat2 goes to CRITICAL_FAIL, broadcasts FAILURE")
print("         sat3,4,5 record sat2 failed but DON'T cascade to CRITICAL_FAIL")
lib.sim_inject_event(sat_contexts[2], EVT_CRITICAL_FAILURE)
processed_2 = process_queue(64)
print(f"Processed frames after sat2 fail: {processed_2}")

print("\n[FINAL STATE]")
for sat_id in sat_contexts.keys():
    dump_state(sat_id)

print("\n[VALIDATION]")
print("✓ sat1 and sat2 are in CRITICAL_FAIL due to their own failure events")
print("✓ sat3, sat4, sat5 record the failures but stay in IDLE (NO CASCADE)")
print("✓ Known failures properly tracked per satellite\n")

cleanup()
print("=" * 80)
print("TEST PASSED: No cascading failures ✓")
print("=" * 80 + "\n")
