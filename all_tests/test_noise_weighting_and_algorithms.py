#!/usr/bin/env python3
import ctypes
import math
import os
import random
import time

BASE_DIR = os.path.dirname(__file__)
DLL_CANDIDATES = [
    os.path.join(BASE_DIR, "..", "c++ implemnetation", "build", "bin", "Release", "sisp.dll"),
    os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll"),
]
DLL_PATH = next((p for p in DLL_CANDIDATES if os.path.exists(p)), None)
if DLL_PATH is None:
    raise FileNotFoundError("sisp.dll not found in expected build locations.")

lib = ctypes.CDLL(DLL_PATH)

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

lib.sim_clear_correction_filter.argtypes = [ctypes.c_void_p]
lib.sim_clear_correction_filter.restype = None
lib.sim_use_weighted_median_filter.argtypes = [ctypes.c_void_p]
lib.sim_use_weighted_median_filter.restype = None
lib.sim_use_kalman_filter.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float]
lib.sim_use_kalman_filter.restype = None
lib.sim_use_hybrid_filter.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float]
lib.sim_use_hybrid_filter.restype = None

lib.sim_inject_correction_rsp.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint8,
    ctypes.c_uint8,
    ctypes.c_uint8,
    ctypes.c_uint8,
    ctypes.c_float,
    ctypes.c_float,
    ctypes.c_float,
    ctypes.c_uint32,
]
lib.sim_inject_correction_rsp.restype = None

EVT_FAULT_DETECTED = 12
EVT_CORRECTION_DONE = 20
SENSOR_MAGNETOMETER = 0x01

TRUE_X, TRUE_Y, TRUE_Z = 42.0, -17.5, 9.25


def vec_err(x, y, z):
    return math.sqrt((x - TRUE_X) ** 2 + (y - TRUE_Y) ** 2 + (z - TRUE_Z) ** 2)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def degr_from_error(err_mag, sigma, mode):
    # Normalize by 3*sigma so most gaussian samples are in-range [0, 1].
    denom = max(1e-6, 3.0 * sigma)
    e = clamp(err_mag / denom, 0.0, 1.0)

    if mode == "inverse_error":
        target_weight = 0.05 + 0.95 * (1.0 - e)
    elif mode == "proportional_error":
        target_weight = 0.05 + 0.95 * e
    else:
        target_weight = 0.5

    degr = int(round((1.0 - target_weight) * 15.0))
    return int(clamp(degr, 0, 15))


def generate_measurements(rounds, sigma, seed):
    rng = random.Random(seed)
    data = []
    for _ in range(rounds):
        m2 = (
            TRUE_X + rng.gauss(0.0, sigma),
            TRUE_Y + rng.gauss(0.0, sigma),
            TRUE_Z + rng.gauss(0.0, sigma),
        )
        m3 = (
            TRUE_X + rng.gauss(0.0, sigma),
            TRUE_Y + rng.gauss(0.0, sigma),
            TRUE_Z + rng.gauss(0.0, sigma),
        )
        data.append((m2, m3))
    return data


def generate_asymmetric_measurements(rounds, healthy_sigma, broken_sigma, seed):
    rng = random.Random(seed)
    data = []
    for _ in range(rounds):
        healthy = (
            TRUE_X + rng.gauss(0.0, healthy_sigma),
            TRUE_Y + rng.gauss(0.0, healthy_sigma),
            TRUE_Z + rng.gauss(0.0, healthy_sigma),
        )
        broken = (
            TRUE_X + rng.gauss(0.0, broken_sigma),
            TRUE_Y + rng.gauss(0.0, broken_sigma),
            TRUE_Z + rng.gauss(0.0, broken_sigma),
        )
        data.append((healthy, broken))
    return data


def run_case(algorithm, sigma2, sigma3, rounds, weight_mode, measurements):
    sat1 = lib.sim_create_context(1)
    if not sat1:
        raise RuntimeError("Failed to create requester context")

    try:
        if algorithm == "raw":
            lib.sim_clear_correction_filter(sat1)
        elif algorithm == "weighted_median":
            lib.sim_use_weighted_median_filter(sat1)
        elif algorithm == "kalman":
            lib.sim_use_kalman_filter(sat1, ctypes.c_float(0.02), ctypes.c_float(0.8))
        elif algorithm == "hybrid":
            lib.sim_use_hybrid_filter(sat1, ctypes.c_float(0.02), ctypes.c_float(0.8))
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

        seq2, seq3 = 1, 1
        ts = 100

        raw_acc = 0.0
        corr_acc = 0.0
        raw_ss_acc = 0.0
        corr_ss_acc = 0.0
        ss_count = 0

        for r in range(1, rounds + 1):
            lib.sim_inject_event(sat1, EVT_FAULT_DETECTED)

            (m2x, m2y, m2z), (m3x, m3y, m3z) = measurements[r - 1]
            raw_x = 0.5 * (m2x + m3x)
            raw_y = 0.5 * (m2y + m3y)
            raw_z = 0.5 * (m2z + m3z)

            err2 = vec_err(m2x, m2y, m2z)
            err3 = vec_err(m3x, m3y, m3z)

            d2 = degr_from_error(err2, sigma2, weight_mode)
            d3 = degr_from_error(err3, sigma3, weight_mode)

            lib.sim_inject_correction_rsp(sat1, 2, seq2, d2, SENSOR_MAGNETOMETER, m2x, m2y, m2z, ts)
            lib.sim_inject_correction_rsp(sat1, 3, seq3, d3, SENSOR_MAGNETOMETER, m3x, m3y, m3z, ts + 1)

            lib.sim_advance_time(sat1, 5100)

            corrected = (ctypes.c_float * 3)()
            lib.sim_get_corrected(sat1, corrected)
            cx, cy, cz = float(corrected[0]), float(corrected[1]), float(corrected[2])

            lib.sim_inject_event(sat1, EVT_CORRECTION_DONE)

            raw_err = vec_err(raw_x, raw_y, raw_z)
            corr_err = vec_err(cx, cy, cz)
            raw_acc += raw_err
            corr_acc += corr_err

            if r > rounds // 3:
                raw_ss_acc += raw_err
                corr_ss_acc += corr_err
                ss_count += 1

            seq2 = (seq2 + 1) & 0xFF
            seq3 = (seq3 + 1) & 0xFF
            ts += 100

        avg_raw = raw_acc / rounds
        avg_corr = corr_acc / rounds
        avg_raw_ss = raw_ss_acc / max(1, ss_count)
        avg_corr_ss = corr_ss_acc / max(1, ss_count)

        return {
            "avg_raw": avg_raw,
            "avg_corr": avg_corr,
            "avg_raw_ss": avg_raw_ss,
            "avg_corr_ss": avg_corr_ss,
            "ss_gain": avg_raw_ss - avg_corr_ss,
        }
    finally:
        lib.sim_destroy_context(sat1)


def print_table(title, rows):
    print(f"\n{title}")
    print("sigma  algo             raw(avg)  corr(avg) raw(ss)  corr(ss) gain(ss)")
    print("-----  ---------------  --------  --------- -------  -------- -------")
    for row in rows:
        print(
            f"{row['sigma']:>5.1f}  {row['algo']:<15}  "
            f"{row['avg_raw']:>8.3f}  {row['avg_corr']:>9.3f} "
            f"{row['avg_raw_ss']:>7.3f}  {row['avg_corr_ss']:>8.3f} {row['ss_gain']:>7.3f}"
        )


def run_kalman_degr_sensitivity(rounds=120, healthy_sigma=2.0, broken_sigma=50.0):
    measurements = generate_asymmetric_measurements(rounds, healthy_sigma, broken_sigma, seed=240516)

    inv = run_case("kalman", healthy_sigma, broken_sigma, rounds, "inverse_error", measurements)
    neutral = run_case("kalman", healthy_sigma, broken_sigma, rounds, "neutral", measurements)
    prop = run_case("kalman", healthy_sigma, broken_sigma, rounds, "proportional_error", measurements)

    print("\n--- Kalman sensitivity to DEGR mapping (healthy vs very noisy responder) ---")
    print("mode                corr(ss)  raw(ss)  gain(ss)")
    print("------------------  --------  -------  --------")
    print(f"inverse_error       {inv['avg_corr_ss']:8.3f}  {inv['avg_raw_ss']:7.3f}  {inv['ss_gain']:8.3f}")
    print(f"neutral             {neutral['avg_corr_ss']:8.3f}  {neutral['avg_raw_ss']:7.3f}  {neutral['ss_gain']:8.3f}")
    print(f"proportional_error  {prop['avg_corr_ss']:8.3f}  {prop['avg_raw_ss']:7.3f}  {prop['ss_gain']:8.3f}")

    if not (inv["avg_corr_ss"] < neutral["avg_corr_ss"] and inv["avg_corr_ss"] < prop["avg_corr_ss"]):
        raise AssertionError(
            "Kalman/DEGR sensitivity failed: inverse-error weighting should outperform neutral and proportional-error weighting"
        )


def benchmark_runtime_budget(rounds=400, sigma=30.0):
    measurements = generate_measurements(rounds, sigma, seed=9090)
    start = time.perf_counter()
    stats = run_case("kalman", sigma, sigma, rounds, "inverse_error", measurements)
    elapsed_s = time.perf_counter() - start
    ms_per_round = (elapsed_s * 1000.0) / max(1, rounds)

    print("\n--- Runtime budget check (Python harness upper-bound) ---")
    print(
        f"rounds={rounds} sigma={sigma:.1f} elapsed={elapsed_s:.3f}s "
        f"avg={ms_per_round:.3f} ms/round corrected_ss={stats['avg_corr_ss']:.3f}"
    )

    # Loose guardrail: includes Python+ctypes overhead, so C++ embedded runtime is expected to be lower.
    if ms_per_round > 50.0:
        raise AssertionError(f"Runtime budget exceeded: {ms_per_round:.3f} ms/round")


def main():
    sigmas = [2.0, 5.0, 8.0, 12.0, 16.0, 20.0, 30.0, 40.0, 60.0]
    algorithms = ["raw", "weighted_median", "kalman", "hybrid"]
    rounds = 90

    print("=== Noise/Weight/Algorithm Comparison (C++ correction engine) ===")
    print("DEGR model: inverse_error (higher gaussian error -> higher DEGR / lower trust)")
    print("Includes very large-error regimes to validate correction robustness under strong sensor faults")
    print(f"Rounds per case: {rounds}")

    rows = []
    for sigma in sigmas:
        measurements = generate_measurements(rounds, sigma, seed=1337 + int(100 * sigma))
        for algo in algorithms:
            stats = run_case(algo, sigma, sigma, rounds, "inverse_error", measurements)
            rows.append(
                {
                    "sigma": sigma,
                    "algo": algo,
                    "avg_raw": stats["avg_raw"],
                    "avg_corr": stats["avg_corr"],
                    "avg_raw_ss": stats["avg_raw_ss"],
                    "avg_corr_ss": stats["avg_corr_ss"],
                    "ss_gain": stats["ss_gain"],
                }
            )
    print_table("--- balanced responders, inverse-error DEGR ---", rows)

    broken_rows = []
    healthy_sigma = 2.0
    broken_sigmas = [5.0, 10.0, 20.0, 40.0, 60.0, 90.0]
    for broken_sigma in broken_sigmas:
        measurements = generate_asymmetric_measurements(rounds, healthy_sigma, broken_sigma, seed=777 + int(10 * broken_sigma))
        for algo in algorithms:
            stats = run_case(algo, healthy_sigma, broken_sigma, rounds, "inverse_error", measurements)
            broken_rows.append(
                {
                    "sigma": broken_sigma,
                    "algo": algo,
                    "avg_raw": stats["avg_raw"],
                    "avg_corr": stats["avg_corr"],
                    "avg_raw_ss": stats["avg_raw_ss"],
                    "avg_corr_ss": stats["avg_corr_ss"],
                    "ss_gain": stats["ss_gain"],
                }
            )
    print_table("--- one healthy responder + one broken responder, inverse-error DEGR ---", broken_rows)

    run_kalman_degr_sensitivity(rounds=140, healthy_sigma=2.0, broken_sigma=50.0)
    benchmark_runtime_budget(rounds=500, sigma=30.0)


if __name__ == "__main__":
    main()
