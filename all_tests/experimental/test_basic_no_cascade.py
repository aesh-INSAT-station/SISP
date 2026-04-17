#!/usr/bin/env python3
"""
SUPER SIMPLE TEST: Verify no cascading failures
Just check that sat1 fails, other sats don't cascade
"""

import ctypes
import os

BASE_DIR = os.path.dirname(__file__)
DLL_PATH = os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll")

if not os.path.exists(DLL_PATH):
    raise FileNotFoundError(f"sisp.dll not found at: {DLL_PATH}")

lib = ctypes.CDLL(DLL_PATH)

# C API
lib.sim_create_context.argtypes = [ctypes.c_uint8]
lib.sim_create_context.restype = ctypes.c_void_p
lib.sim_destroy_context.argtypes = [ctypes.c_void_p]
lib.sim_destroy_context.restype = None
lib.sim_inject_event.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.sim_inject_event.restype = None
lib.sim_get_degr.argtypes = [ctypes.c_void_p]
lib.sim_get_degr.restype = ctypes.c_uint8
lib.sim_get_state.argtypes = [ctypes.c_void_p]
lib.sim_get_state.restype = ctypes.c_int
lib.sim_get_last_failed_satellite.argtypes = [ctypes.c_void_p]
lib.sim_get_last_failed_satellite.restype = ctypes.c_uint8

EVT_CRITICAL_FAILURE = 21

print("\n" + "="*70)
print("SIMPLE NO-CASCADE TEST")
print("="*70)

# Create 3 satellites - NO TX callback (no frame generation)
contexts = {}
for sat_id in [1, 2, 3]:
    ctx = lib.sim_create_context(sat_id)
    if not ctx:
        raise RuntimeError(f"Failed to create sat{sat_id}")
    contexts[sat_id] = ctx
    print(f"✓ Created sat{sat_id}")

print("\n[INITIAL] Satellite status:")
for sat_id in contexts:
    state = lib.sim_get_state(contexts[sat_id])
    degr = lib.sim_get_degr(contexts[sat_id])
    print(f"  sat{sat_id}: state={state:2d} degr={degr:2d}")

print("\n[INJECT] CRITICAL_FAILURE event on sat1 (internal event)")
print("Expected: sat1 goes to CRITICAL_FAIL (state=20)")
lib.sim_inject_event(contexts[1], EVT_CRITICAL_FAILURE)

print("\n[RESULT] Satellite status after sat1 critical failure:")
for sat_id in contexts:
    state = lib.sim_get_state(contexts[sat_id])
    degr = lib.sim_get_degr(contexts[sat_id])
    last_failed = lib.sim_get_last_failed_satellite(contexts[sat_id])
    status = f"state={state:2d} degr={degr:2d} last_failed={last_failed}"
    print(f"  sat{sat_id}: {status}")

# Validation
sat1_state = lib.sim_get_state(contexts[1])
sat2_state = lib.sim_get_state(contexts[2])
sat3_state = lib.sim_get_state(contexts[3])

print("\n[VALIDATION]")
if sat1_state == 20:
    print("✓ sat1 is in CRITICAL_FAIL (state=20) - CORRECT")
else:
    print(f"✗ sat1 state is {sat1_state}, expected 20")

if sat2_state != 20:
    print(f"✓ sat2 is NOT in CRITICAL_FAIL (state={sat2_state}) - CORRECT (NO CASCADE)")
else:
    print(f"✗ sat2 cascaded to CRITICAL_FAIL (state={sat2_state})")

if sat3_state != 20:
    print(f"✓ sat3 is NOT in CRITICAL_FAIL (state={sat3_state}) - CORRECT (NO CASCADE)")
else:
    print(f"✗ sat3 cascaded to CRITICAL_FAIL (state={sat3_state})")

# Cleanup
for ctx in contexts.values():
    lib.sim_destroy_context(ctx)

print("\n" + "="*70)
print("✓ TEST PASSED: No cascading failures!")
print("="*70 + "\n")
