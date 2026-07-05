#!/usr/bin/env python3
import csv
import ctypes
import math
import os
import random

from test_noise_weighting_and_algorithms import (
    EVT_CORRECTION_DONE,
    EVT_FAULT_DETECTED,
    SENSOR_MAGNETOMETER,
    clamp,
    degr_from_error,
    dist_vec,
    lib,
    mean_vec,
    pre_fuse_measurement,
)


BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, "..", "data", "raw", "segments.csv")

ALGORITHMS = [
    "weighted_median",
    "kalman",
    "nis_gated_kalman",
    "hybrid",
    "diwkcf",
    "ransac_kalman",
    "gossip_kalman",
]
ctypes_float_array_3 = ctypes.c_float * 3


def vec_err_to_truth(v, truth):
    return math.sqrt((v[0] - truth[0]) ** 2 + (v[1] - truth[1]) ** 2 + (v[2] - truth[2]) ** 2)


def zscore(values):
    mean = sum(values) / max(1, len(values))
    var = sum((v - mean) ** 2 for v in values) / max(1, len(values))
    std = math.sqrt(max(1e-18, var))
    return [(v - mean) / std for v in values]


def rolling_mean(values, window=12):
    out = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start : i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def first_diff(values):
    out = [0.0]
    for i in range(1, len(values)):
        out.append(values[i] - values[i - 1])
    return out


def load_truth_vectors(rounds=180, channel="CADC0873"):
    values = []
    with open(DATA_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["channel"] != channel:
                continue
            values.append(float(row["value"]))
            if len(values) >= rounds:
                break

    if len(values) < rounds:
        raise RuntimeError(f"Not enough data for channel {channel}: got {len(values)}, need {rounds}")

    zv = zscore(values)
    zr = zscore(rolling_mean(values))
    zd = zscore(first_diff(values))

    truth = []
    for x, y, z in zip(zv, zr, zd):
        truth.append((42.0 + 8.0 * x, -17.5 + 6.0 * y, 9.25 + 4.0 * z))
    return truth


def fault_phase(round_index):
    if 35 <= round_index < 65:
        return "burst_storm"
    if 70 <= round_index < 115:
        return "drift_and_stuck"
    if 120 <= round_index < 145:
        return "dropout_and_random"
    if 145 <= round_index < 170:
        return "recovery"
    return "nominal"


def generate_large_constellation_rounds(truth, sat_count, seed):
    rng = random.Random(seed)
    rounds = []
    per_sat_sigma = [1.4 + 0.35 * (i % 4) for i in range(sat_count)]
    stuck_value = None

    for r, gt in enumerate(truth, start=1):
        phase = fault_phase(r)
        readings = []
        sigmas = []
        events = []

        if r == 70:
            stuck_value = gt

        for sat in range(sat_count):
            if phase == "dropout_and_random" and rng.random() < (0.10 + 0.02 * sat):
                events.append((sat + 2, "dropout"))
                continue

            sigma = per_sat_sigma[sat]
            x = gt[0] + rng.gauss(0.0, sigma)
            y = gt[1] + rng.gauss(0.0, sigma)
            z = gt[2] + rng.gauss(0.0, sigma)

            if phase == "burst_storm" and rng.random() < 0.22:
                spike = 14.0 + 3.0 * (sat % 3)
                x += rng.choice((-1.0, 1.0)) * abs(rng.gauss(spike, 4.0))
                y += rng.choice((-1.0, 1.0)) * abs(rng.gauss(spike * 0.7, 3.0))
                z += rng.choice((-1.0, 1.0)) * abs(rng.gauss(spike * 0.5, 2.0))
                sigma *= 3.5
                events.append((sat + 2, "spike"))

            if phase in ("drift_and_stuck", "recovery") and sat == 2:
                if phase == "drift_and_stuck":
                    drift_mag = min(28.0, 0.85 * (r - 70))
                else:
                    drift_mag = max(0.0, 28.0 - 1.4 * (r - 145))
                x += drift_mag
                y -= 0.55 * drift_mag
                z += 0.25 * drift_mag
                sigma *= 4.0
                events.append((sat + 2, "recovering_drift" if phase == "recovery" else "drift"))

            if phase == "drift_and_stuck" and sat == 4 and stuck_value is not None:
                x, y, z = stuck_value
                sigma *= 5.0
                events.append((sat + 2, "stuck"))

            if phase == "dropout_and_random" and rng.random() < 0.12:
                x += rng.gauss(0.0, 26.0)
                y += rng.gauss(0.0, 26.0)
                z += rng.gauss(0.0, 26.0)
                sigma *= 5.0
                events.append((sat + 2, "random_fault"))

            readings.append((x, y, z))
            sigmas.append(sigma)

        rounds.append(
            {
                "truth": gt,
                "readings": readings,
                "sigmas": sigmas,
                "phase": phase,
                "events": events,
            }
        )

    return rounds


def configure_algorithm(ctx, algorithm):
    if algorithm == "weighted_median":
        lib.sim_use_weighted_median_filter(ctx)
    elif algorithm in ("kalman", "nis_gated_kalman", "diwkcf", "ransac_kalman", "gossip_kalman"):
        lib.sim_use_kalman_filter(ctx, 0.03, 0.9)
    elif algorithm == "hybrid":
        lib.sim_use_hybrid_filter(ctx, 0.03, 0.9)
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")


def run_dynamic_case(algorithm, rounds_data, threshold=4.0, degr_policy=None):
    ctx = lib.sim_create_context(1)
    if not ctx:
        raise RuntimeError("Failed to create requester context")

    try:
        configure_algorithm(ctx, algorithm)
        seqs = [1] * 8
        ts = 100
        pred = None
        nis_ema = [1.0] * 8
        chi2_3d_base = 11.345

        raw_errors = []
        corrected_errors = []
        phase_errors = {}
        recovery_round = None
        first_converge = None

        for r, item in enumerate(rounds_data, start=1):
            lib.sim_inject_event(ctx, EVT_FAULT_DETECTED)
            truth = item["truth"]
            readings = list(item["readings"])[:8]
            sigmas = list(item["sigmas"])[:8]
            if not readings:
                readings = [pred if pred is not None else truth]
                sigmas = [30.0]

            raw = mean_vec(readings)
            if degr_policy is None:
                degrs = [
                    degr_from_error(vec_err_to_truth(reading, truth), sigma, "inverse_error")
                    for reading, sigma in zip(readings, sigmas)
                ]
            else:
                degrs = [
                    degr_policy(vec_err_to_truth(reading, truth), sigma)
                    for reading, sigma in zip(readings, sigmas)
                ]

            if algorithm == "nis_gated_kalman" and pred is not None:
                for i, reading in enumerate(readings):
                    innovation = dist_vec(reading, pred)
                    nis = (innovation * innovation) / max(1e-6, sigmas[i] * sigmas[i])
                    threshold_i = chi2_3d_base * clamp(nis_ema[i], 0.7, 3.0)
                    if nis > threshold_i:
                        degrs[i] = 15
                    nis_ema[i] = 0.9 * nis_ema[i] + 0.1 * nis

            if algorithm in ("diwkcf", "ransac_kalman", "gossip_kalman"):
                fused = pre_fuse_measurement(algorithm, readings, degrs, sigmas, r)
                lib.sim_inject_correction_rsp(
                    ctx, 2, seqs[0], 0, SENSOR_MAGNETOMETER,
                    fused[0], fused[1], fused[2], ts
                )
            else:
                for i, (reading, degr) in enumerate(zip(readings, degrs)):
                    lib.sim_inject_correction_rsp(
                        ctx, 2 + i, seqs[i], degr, SENSOR_MAGNETOMETER,
                        reading[0], reading[1], reading[2], ts + i
                    )

            lib.sim_advance_time(ctx, 5100)

            corrected = (ctypes_float_array_3)()
            lib.sim_get_corrected(ctx, corrected)
            corr = (float(corrected[0]), float(corrected[1]), float(corrected[2]))
            pred = corr
            lib.sim_inject_event(ctx, EVT_CORRECTION_DONE)

            raw_err = vec_err_to_truth(raw, truth)
            corr_err = vec_err_to_truth(corr, truth)
            raw_errors.append(raw_err)
            corrected_errors.append(corr_err)
            phase_errors.setdefault(item["phase"], []).append(corr_err)

            if first_converge is None and corr_err < threshold:
                first_converge = r
            if r >= 145 and recovery_round is None and corr_err < threshold:
                recovery_round = r - 145

            for i in range(len(seqs)):
                seqs[i] = (seqs[i] + 1) & 0xFF
            ts += 100

        tail = max(1, len(rounds_data) // 3)
        return {
            "avg_raw": sum(raw_errors) / len(raw_errors),
            "avg_corr": sum(corrected_errors) / len(corrected_errors),
            "steady_raw": sum(raw_errors[-tail:]) / tail,
            "steady_corr": sum(corrected_errors[-tail:]) / tail,
            "gain": (sum(raw_errors[-tail:]) / tail) - (sum(corrected_errors[-tail:]) / tail),
            "p95_corr": sorted(corrected_errors)[int(0.95 * (len(corrected_errors) - 1))],
            "max_corr": max(corrected_errors),
            "first_converge": first_converge,
            "recovery_round": recovery_round,
            "phase_errors": {
                phase: sum(vals) / len(vals)
                for phase, vals in phase_errors.items()
            },
        }
    finally:
        lib.sim_destroy_context(ctx)


def format_cell(stats):
    rec = stats["recovery_round"] if stats["recovery_round"] is not None else "-"
    return f"{stats['steady_corr']:.2f}/{stats['gain']:+.2f}/{stats['p95_corr']:.2f}/{rec}"


def run_large_constellation_matrix(rounds=180):
    truth = load_truth_vectors(rounds=rounds)
    rows = []
    for sat_count in (3, 5, 8):
        scenario_rounds = generate_large_constellation_rounds(
            truth, sat_count=sat_count, seed=91300 + sat_count
        )
        results = {
            algorithm: run_dynamic_case(algorithm, scenario_rounds)
            for algorithm in ALGORITHMS
        }
        rows.append((sat_count, results))
    return rows


def print_large_constellation_report(rows):
    print("\n=== Large-constellation data-driven recovery benchmark ===")
    print("Data source: data/raw/segments.csv channel CADC0873")
    print("Fault phases: nominal, burst storm, drift+stuck, dropout+random, recovery")
    print("Cell format: steady_corr/gain/p95_corr/recovery_round_after_fault_end")
    print("| Satellites | " + " | ".join(ALGORITHMS) + " |")
    print("|---|" + "|".join("---" for _ in ALGORITHMS) + "|")
    for sat_count, results in rows:
        cells = [format_cell(results[algorithm]) for algorithm in ALGORITHMS]
        print(f"| {sat_count} | " + " | ".join(cells) + " |")

    print("\nPhase-level corrected error by best steady-state algorithm:")
    for sat_count, results in rows:
        best_algo = min(results, key=lambda name: results[name]["steady_corr"])
        phase_errors = results[best_algo]["phase_errors"]
        phases = ", ".join(f"{phase}={phase_errors[phase]:.2f}" for phase in sorted(phase_errors))
        print(f"{sat_count} satellites: {best_algo}: {phases}")


def test_large_constellation_data_recovery():
    rows = run_large_constellation_matrix(rounds=180)
    for sat_count, results in rows:
        best = min(results.values(), key=lambda row: row["steady_corr"])
        assert best["gain"] > 0.0, f"{sat_count} satellites should improve over raw"
        assert best["recovery_round"] is not None, f"{sat_count} satellites should recover after fault phase"
        assert best["recovery_round"] <= 20, f"{sat_count} satellites recovery is too slow"


if __name__ == "__main__":
    print_large_constellation_report(run_large_constellation_matrix(rounds=180))
