#!/usr/bin/env python3
import ctypes
import os
import random
import math

BASE_DIR = os.path.dirname(__file__)
DLL_CANDIDATES = [
    os.path.join(BASE_DIR, "..", "c++ implemnetation", "build", "bin", "Release", "sisp.dll"),
    os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll"),
]
DLL_PATH = next((p for p in DLL_CANDIDATES if os.path.exists(p)), None)
if DLL_PATH is None:
    raise FileNotFoundError("sisp.dll not found in expected build locations.")

lib = ctypes.CDLL(DLL_PATH)

# Core APIs
lib.sim_create_context.argtypes = [ctypes.c_uint8]
lib.sim_create_context.restype = ctypes.c_void_p
lib.sim_destroy_context.argtypes = [ctypes.c_void_p]
lib.sim_destroy_context.restype = None
lib.sim_inject_event.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.sim_inject_event.restype = None
lib.sim_advance_time.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
lib.sim_advance_time.restype = None
lib.sim_get_corrected.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float)]
lib.sim_get_corrected.restype = None
lib.sim_get_state.argtypes = [ctypes.c_void_p]
lib.sim_get_state.restype = ctypes.c_int

# New C bridge helpers
lib.sim_use_kalman_filter.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float]
lib.sim_use_kalman_filter.restype = None
lib.sim_inject_correction_rsp.argtypes = [
    ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8,
    ctypes.c_uint8, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_uint32
]
lib.sim_inject_correction_rsp.restype = None

# Events / enums
EVT_FAULT_DETECTED = 12
EVT_CORRECTION_DONE = 20
SENSOR_MAGNETOMETER = 0x01

# Ground truth (target original vector we want to recover)
TRUE_X, TRUE_Y, TRUE_Z = 42.0, -17.5, 9.25

# Satellite contexts: sat1 is requester, sat2/sat3 are responders
sat1 = lib.sim_create_context(1)
sat2 = lib.sim_create_context(2)
sat3 = lib.sim_create_context(3)


def run_profile(profile_name: str, sigma: float, rounds: int, seed: int):
    random.seed(seed)

    raw_err_acc = 0.0
    corrected_err_acc = 0.0
    raw_err_ss_acc = 0.0
    corrected_err_ss_acc = 0.0
    ss_count = 0

    seq2 = 1
    seq3 = 1
    ts = 100

    print(f"\n--- Profile: {profile_name} | sigma={sigma:.1f} | rounds={rounds} ---")

    for r in range(1, rounds + 1):
        lib.sim_inject_event(sat1, EVT_FAULT_DETECTED)

        m2x = TRUE_X + random.gauss(0.0, sigma)
        m2y = TRUE_Y + random.gauss(0.0, sigma)
        m2z = TRUE_Z + random.gauss(0.0, sigma)

        m3x = TRUE_X + random.gauss(0.0, sigma)
        m3y = TRUE_Y + random.gauss(0.0, sigma)
        m3z = TRUE_Z + random.gauss(0.0, sigma)

        raw_x = (m2x + m3x) * 0.5
        raw_y = (m2y + m3y) * 0.5
        raw_z = (m2z + m3z) * 0.5

        # Keep neighbour DEGR dynamic with error so filtering trust adapts in large-fault profiles.
        e2 = math.sqrt((m2x - TRUE_X) ** 2 + (m2y - TRUE_Y) ** 2 + (m2z - TRUE_Z) ** 2)
        e3 = math.sqrt((m3x - TRUE_X) ** 2 + (m3y - TRUE_Y) ** 2 + (m3z - TRUE_Z) ** 2)
        d2 = int(max(0, min(15, round((e2 / max(1e-6, 3.0 * sigma)) * 15.0))))
        d3 = int(max(0, min(15, round((e3 / max(1e-6, 3.0 * sigma)) * 15.0))))

        lib.sim_inject_correction_rsp(sat1, 2, seq2, d2, SENSOR_MAGNETOMETER, m2x, m2y, m2z, ts)
        lib.sim_inject_correction_rsp(sat1, 3, seq3, d3, SENSOR_MAGNETOMETER, m3x, m3y, m3z, ts + 1)

        lib.sim_advance_time(sat1, 5100)

        corrected = (ctypes.c_float * 3)()
        lib.sim_get_corrected(sat1, corrected)
        cx, cy, cz = float(corrected[0]), float(corrected[1]), float(corrected[2])

        lib.sim_inject_event(sat1, EVT_CORRECTION_DONE)

        raw_err = math.sqrt((raw_x - TRUE_X) ** 2 + (raw_y - TRUE_Y) ** 2 + (raw_z - TRUE_Z) ** 2)
        corr_err = math.sqrt((cx - TRUE_X) ** 2 + (cy - TRUE_Y) ** 2 + (cz - TRUE_Z) ** 2)

        raw_err_acc += raw_err
        corrected_err_acc += corr_err

        if r >= 6:
            raw_err_ss_acc += raw_err
            corrected_err_ss_acc += corr_err
            ss_count += 1

        if r <= 5 or r in (rounds // 2, rounds):
            print(
                f"round={r:2d} raw=({raw_x:8.3f},{raw_y:8.3f},{raw_z:8.3f}) "
                f"corr=({cx:8.3f},{cy:8.3f},{cz:8.3f}) raw_err={raw_err:7.3f} corr_err={corr_err:7.3f}"
            )

        seq2 = (seq2 + 1) & 0xFF
        seq3 = (seq3 + 1) & 0xFF
        ts += 100

    avg_raw = raw_err_acc / rounds
    avg_corr = corrected_err_acc / rounds
    avg_raw_ss = raw_err_ss_acc / max(1, ss_count)
    avg_corr_ss = corrected_err_ss_acc / max(1, ss_count)

    print(f"{profile_name} avg raw error      : {avg_raw:.4f}")
    print(f"{profile_name} avg corrected error: {avg_corr:.4f}")
    print(f"{profile_name} steady-state raw   : {avg_raw_ss:.4f}")
    print(f"{profile_name} steady-state corr  : {avg_corr_ss:.4f}")

    return {
        "avg_raw": avg_raw,
        "avg_corr": avg_corr,
        "avg_raw_ss": avg_raw_ss,
        "avg_corr_ss": avg_corr_ss,
    }

try:
    # Enable Kalman on requester with explicit coefficients.
    # Lower q/r -> smoother, higher q/r -> more reactive.
    lib.sim_use_kalman_filter(sat1, ctypes.c_float(0.02), ctypes.c_float(0.8))

    random.seed(1337)

    print("\n=== Kalman 3-Satellite Gaussian Test (C++ engine via DLL) ===")
    print(f"Ground truth vector: ({TRUE_X:.3f}, {TRUE_Y:.3f}, {TRUE_Z:.3f})")
    print("Requester: sat1, Responders: sat2/sat3")
    print("Running two profiles: nominal noise and large sensor-fault noise")

    nominal = run_profile("nominal", sigma=2.0, rounds=20, seed=1337)
    large_fault = run_profile("large_fault", sigma=25.0, rounds=30, seed=7331)

    print("\n=== Summary ===")
    print(
        f"Nominal steady-state raw/corr : {nominal['avg_raw_ss']:.4f} / {nominal['avg_corr_ss']:.4f}"
    )
    print(
        f"Large-fault steady-state raw/corr : {large_fault['avg_raw_ss']:.4f} / {large_fault['avg_corr_ss']:.4f}"
    )
    if nominal["avg_corr_ss"] < nominal["avg_raw_ss"] and large_fault["avg_corr_ss"] < large_fault["avg_raw_ss"]:
        print("Result: Kalman correction improves both nominal and large-fault profiles.")
    else:
        print("Result: Improvement not consistent across profiles; retune process/measurement noise.")

finally:
    lib.sim_destroy_context(sat1)
    lib.sim_destroy_context(sat2)
    lib.sim_destroy_context(sat3)
