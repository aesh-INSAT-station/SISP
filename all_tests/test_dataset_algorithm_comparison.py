#!/usr/bin/env python3
"""Dataset-backed correction-algorithm comparison for demo/paper logs.

The OPSSAT feature table is not raw sensor telemetry, so this harness treats
selected numeric segment features as repeatable sensor vectors. The purpose is
to exercise the C++ correction engine on real channel/statistical structure
instead of only synthetic Gaussian samples.
"""

import csv
import ctypes
import math
import os
from statistics import median
from typing import Dict, List, Tuple


BASE_DIR = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DATASET_PATH = os.path.join(ROOT, "dataset.csv")
DLL_PATH = os.path.join(ROOT, "c++ implemnetation", "build", "bin", "Release", "sisp.dll")

if not os.path.exists(DLL_PATH):
    raise FileNotFoundError(f"sisp.dll not found at {DLL_PATH}. Run all_tests/run_cpp_tests.ps1 first.")
if not os.path.exists(DATASET_PATH):
    raise FileNotFoundError(f"dataset.csv not found at {DATASET_PATH}.")


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


Vector = Tuple[float, float, float]


def as_float(row: Dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return 0.0


def feature_vector(row: Dict[str, str]) -> Vector:
    # Scale tiny engineering features into a numerically useful vector range.
    return (
        as_float(row, "mean") * 1.0e6,
        as_float(row, "std") * 1.0e6,
        as_float(row, "diff_var") * 1.0e10,
    )


def vec_err(v: Vector, truth: Vector) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(v, truth)))


def row_degr(row: Dict[str, str], v: Vector, truth: Vector, scale: float) -> int:
    anomaly = int(as_float(row, "anomaly") > 0.5)
    distance_part = min(10, int(round(10.0 * vec_err(v, truth) / max(scale, 1e-6))))
    anomaly_part = 5 if anomaly else 0
    return max(0, min(15, distance_part + anomaly_part))


def load_dataset() -> Tuple[List[Dict[str, str]], Vector, float]:
    with open(DATASET_PATH, "r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) < 30:
        raise RuntimeError("dataset.csv has too few rows for the comparison harness.")

    nominal = [feature_vector(r) for r in rows if int(as_float(r, "anomaly") > 0.5) == 0]
    if not nominal:
        nominal = [feature_vector(r) for r in rows]

    truth = tuple(median([v[i] for v in nominal]) for i in range(3))
    distances = sorted(vec_err(v, truth) for v in nominal)
    scale = distances[max(0, int(0.75 * (len(distances) - 1)))]
    return rows, truth, max(scale, 1e-3)


def set_algorithm(ctx, algorithm: str) -> None:
    if algorithm == "raw_cpp_default":
        lib.sim_clear_correction_filter(ctx)
    elif algorithm == "weighted_median":
        lib.sim_use_weighted_median_filter(ctx)
    elif algorithm == "kalman":
        lib.sim_use_kalman_filter(ctx, ctypes.c_float(0.02), ctypes.c_float(0.8))
    elif algorithm == "hybrid":
        lib.sim_use_hybrid_filter(ctx, ctypes.c_float(0.02), ctypes.c_float(0.8))
    else:
        raise ValueError(algorithm)


def run_algorithm(algorithm: str, rows: List[Dict[str, str]], truth: Vector, scale: float, rounds: int = 120) -> Dict[str, float]:
    ctx = lib.sim_create_context(1)
    if not ctx:
        raise RuntimeError("Failed to create C++ simulation context.")

    try:
        set_algorithm(ctx, algorithm)
        raw_acc = 0.0
        corr_acc = 0.0
        raw_ss_acc = 0.0
        corr_ss_acc = 0.0
        ss_count = 0
        seq2 = 1
        seq3 = 1
        ts = 100

        usable_rounds = min(rounds, max(1, len(rows) // 2))
        for idx in range(usable_rounds):
            row2 = rows[(2 * idx) % len(rows)]
            row3 = rows[(2 * idx + 1) % len(rows)]
            v2 = feature_vector(row2)
            v3 = feature_vector(row3)
            raw = tuple((a + b) * 0.5 for a, b in zip(v2, v3))

            d2 = row_degr(row2, v2, truth, scale)
            d3 = row_degr(row3, v3, truth, scale)

            lib.sim_inject_event(ctx, EVT_FAULT_DETECTED)
            lib.sim_inject_correction_rsp(ctx, 2, seq2, d2, SENSOR_MAGNETOMETER, v2[0], v2[1], v2[2], ts)
            lib.sim_inject_correction_rsp(ctx, 3, seq3, d3, SENSOR_MAGNETOMETER, v3[0], v3[1], v3[2], ts + 1)
            lib.sim_advance_time(ctx, 5100)

            out = (ctypes.c_float * 3)()
            lib.sim_get_corrected(ctx, out)
            corr = (float(out[0]), float(out[1]), float(out[2]))

            raw_err = vec_err(raw, truth)
            corr_err = vec_err(corr, truth)
            raw_acc += raw_err
            corr_acc += corr_err
            if idx >= usable_rounds // 3:
                raw_ss_acc += raw_err
                corr_ss_acc += corr_err
                ss_count += 1

            lib.sim_inject_event(ctx, EVT_CORRECTION_DONE)
            seq2 = (seq2 + 1) & 0xFF
            seq3 = (seq3 + 1) & 0xFF
            ts += 100

        return {
            "rounds": float(usable_rounds),
            "avg_raw": raw_acc / usable_rounds,
            "avg_corr": corr_acc / usable_rounds,
            "avg_raw_ss": raw_ss_acc / max(1, ss_count),
            "avg_corr_ss": corr_ss_acc / max(1, ss_count),
        }
    finally:
        lib.sim_destroy_context(ctx)


def main() -> None:
    rows, truth, scale = load_dataset()
    channels = sorted({r.get("channel", "?") for r in rows})
    anomaly_count = sum(1 for r in rows if int(as_float(r, "anomaly") > 0.5))

    print("=== Dataset-backed correction algorithm comparison ===")
    print(f"Dataset: {DATASET_PATH}")
    print(f"Rows={len(rows)} channels={len(channels)} anomalies={anomaly_count}")
    print(f"Feature vector = [mean*1e6, std*1e6, diff_var*1e10]")
    print(f"Nominal median truth = ({truth[0]:.6f}, {truth[1]:.6f}, {truth[2]:.6f}) scale={scale:.6f}")
    print()
    print("algorithm         raw(avg) corr(avg) raw(ss)  corr(ss) gain(ss)")
    print("---------------- --------- --------- -------- -------- --------")

    results = []
    for algorithm in ["raw_cpp_default", "weighted_median", "kalman", "hybrid"]:
        stats = run_algorithm(algorithm, rows, truth, scale)
        gain_ss = stats["avg_raw_ss"] - stats["avg_corr_ss"]
        results.append((algorithm, gain_ss, stats))
        print(
            f"{algorithm:<16} {stats['avg_raw']:9.4f} {stats['avg_corr']:9.4f} "
            f"{stats['avg_raw_ss']:8.4f} {stats['avg_corr_ss']:8.4f} {gain_ss:8.4f}"
        )

    best = min(results, key=lambda item: item[2]["avg_corr_ss"])
    print()
    print(f"Best steady-state corrected error: {best[0]} ({best[2]['avg_corr_ss']:.4f})")

    if not all(math.isfinite(item[2]["avg_corr_ss"]) for item in results):
        raise AssertionError("Non-finite corrected error in dataset comparison.")


if __name__ == "__main__":
    main()
