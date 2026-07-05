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


def generate_burst_outlier_measurements(rounds, base_sigma, outlier_sigma, outlier_prob, seed):
    rng = random.Random(seed)
    data = []
    for _ in range(rounds):
        m2 = [
            TRUE_X + rng.gauss(0.0, base_sigma),
            TRUE_Y + rng.gauss(0.0, base_sigma),
            TRUE_Z + rng.gauss(0.0, base_sigma),
        ]
        m3 = [
            TRUE_X + rng.gauss(0.0, base_sigma),
            TRUE_Y + rng.gauss(0.0, base_sigma),
            TRUE_Z + rng.gauss(0.0, base_sigma),
        ]

        # Inject sparse large outliers independently per responder.
        if rng.random() < outlier_prob:
            m2[0] += rng.gauss(0.0, outlier_sigma)
            m2[1] += rng.gauss(0.0, outlier_sigma)
            m2[2] += rng.gauss(0.0, outlier_sigma)
        if rng.random() < outlier_prob:
            m3[0] += rng.gauss(0.0, outlier_sigma)
            m3[1] += rng.gauss(0.0, outlier_sigma)
            m3[2] += rng.gauss(0.0, outlier_sigma)

        data.append((tuple(m2), tuple(m3)))
    return data


def generate_persistent_biased_measurements(rounds, healthy_sigma, noisy_sigma, bias_xyz, seed):
    rng = random.Random(seed)
    bx, by, bz = bias_xyz
    data = []
    for _ in range(rounds):
        healthy = (
            TRUE_X + rng.gauss(0.0, healthy_sigma),
            TRUE_Y + rng.gauss(0.0, healthy_sigma),
            TRUE_Z + rng.gauss(0.0, healthy_sigma),
        )
        biased = (
            TRUE_X + bx + rng.gauss(0.0, noisy_sigma),
            TRUE_Y + by + rng.gauss(0.0, noisy_sigma),
            TRUE_Z + bz + rng.gauss(0.0, noisy_sigma),
        )
        data.append((healthy, biased))
    return data


def generate_mixed_outlier_measurements(rounds, base_sigma, outlier_sigma, outlier_prob, seed):
    rng = random.Random(seed)
    data = []
    for _ in range(rounds):
        m2 = [
            TRUE_X + rng.gauss(0.0, base_sigma),
            TRUE_Y + rng.gauss(0.0, base_sigma),
            TRUE_Z + rng.gauss(0.0, base_sigma),
        ]
        m3 = [
            TRUE_X + rng.gauss(0.0, base_sigma),
            TRUE_Y + rng.gauss(0.0, base_sigma),
            TRUE_Z + rng.gauss(0.0, base_sigma),
        ]

        # m2 gets rare huge spikes; m3 gets moderate drift-like bursts.
        if rng.random() < outlier_prob:
            sign = -1.0 if rng.random() < 0.5 else 1.0
            m2[0] += sign * abs(rng.gauss(0.0, outlier_sigma))
            m2[1] -= sign * abs(rng.gauss(0.0, outlier_sigma * 0.8))
            m2[2] += sign * abs(rng.gauss(0.0, outlier_sigma * 0.6))

        if rng.random() < (outlier_prob * 1.5):
            m3[0] += rng.gauss(0.0, outlier_sigma * 0.35)
            m3[1] += rng.gauss(0.0, outlier_sigma * 0.35)
            m3[2] += rng.gauss(0.0, outlier_sigma * 0.35)

        data.append((tuple(m2), tuple(m3)))
    return data


def generate_mixed_spike_drift_measurements(rounds, base_sigma, spike_sigma, spike_prob, drift_per_round, seed):
    rng = random.Random(seed)
    data = []
    for r in range(rounds):
        drift = drift_per_round * r
        m2 = [
            TRUE_X + rng.gauss(0.0, base_sigma),
            TRUE_Y + rng.gauss(0.0, base_sigma),
            TRUE_Z + rng.gauss(0.0, base_sigma),
        ]
        m3 = [
            TRUE_X + drift + rng.gauss(0.0, base_sigma),
            TRUE_Y - 0.6 * drift + rng.gauss(0.0, base_sigma),
            TRUE_Z + 0.3 * drift + rng.gauss(0.0, base_sigma),
        ]

        if rng.random() < spike_prob:
            m2[0] += rng.choice((-1.0, 1.0)) * abs(rng.gauss(0.0, spike_sigma))
            m2[1] += rng.choice((-1.0, 1.0)) * abs(rng.gauss(0.0, spike_sigma))
            m2[2] += rng.choice((-1.0, 1.0)) * abs(rng.gauss(0.0, spike_sigma))

        data.append((tuple(m2), tuple(m3)))
    return data


def innovation_norm(mx, my, mz, px, py, pz):
    dx = mx - px
    dy = my - py
    dz = mz - pz
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def nis_3d(mx, my, mz, px, py, pz, sigma):
    # NIS approximation with isotropic innovation covariance S = sigma^2 * I.
    # For 3 DoF, this is distributed approximately as chi-square(3) when model assumptions hold.
    s2 = max(1e-6, sigma * sigma)
    dx = mx - px
    dy = my - py
    dz = mz - pz
    return (dx * dx + dy * dy + dz * dz) / s2


def mean_vec(readings):
    n = max(1, len(readings))
    return (
        sum(v[0] for v in readings) / n,
        sum(v[1] for v in readings) / n,
        sum(v[2] for v in readings) / n,
    )


def weighted_mean_vec(readings, weights):
    total_w = sum(max(0.0, w) for w in weights)
    if total_w <= 0.0:
        return mean_vec(readings)
    return (
        sum(v[0] * max(0.0, w) for v, w in zip(readings, weights)) / total_w,
        sum(v[1] * max(0.0, w) for v, w in zip(readings, weights)) / total_w,
        sum(v[2] * max(0.0, w) for v, w in zip(readings, weights)) / total_w,
    )


def dist_vec(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def pre_fuse_measurement(algorithm, readings, degrs, sigmas, round_index):
    if algorithm == "diwkcf":
        info_weights = []
        for degr in degrs:
            sigma_i = 1.0 + float(degr)
            info_weights.append(1.0 / max(1e-6, sigma_i * sigma_i))
        return weighted_mean_vec(readings, info_weights)

    if algorithm == "ransac_kalman":
        if len(readings) <= 1:
            return readings[0]

        rng = random.Random(880301 + round_index)
        sigma = max(1e-6, sum(sigmas) / max(1, len(sigmas)))
        threshold = 2.0 * sigma
        best_inliers = list(readings)
        best_score = (-1, float("inf"))

        for _ in range(10):
            if len(readings) >= 3:
                sample = rng.sample(readings, 3)
            else:
                sample = [readings[rng.randrange(len(readings))] for _ in range(3)]
            center = mean_vec(sample)
            inliers = [v for v in readings if dist_vec(v, center) <= threshold]
            if not inliers:
                inliers = [min(readings, key=lambda v: dist_vec(v, center))]
            spread = sum(dist_vec(v, center) for v in inliers) / max(1, len(inliers))
            score = (len(inliers), -spread)
            if score > best_score:
                best_score = score
                best_inliers = inliers

        return mean_vec(best_inliers)

    if algorithm == "gossip_kalman":
        rng = random.Random(440917 + round_index)
        values = [tuple(v) for v in readings]
        weights = [max(0.05, 1.0 - float(d) / 15.0) for d in degrs]

        if len(values) <= 1:
            return values[0]

        for _ in range(5):
            for i in range(len(values)):
                choices = [j for j in range(len(values)) if j != i]
                j = rng.choice(choices)
                vi, vj = values[i], values[j]
                values[i] = (
                    0.5 * (vi[0] + vj[0]),
                    0.5 * (vi[1] + vj[1]),
                    0.5 * (vi[2] + vj[2]),
                )
                weights[i] = 0.5 * (weights[i] + weights[j])

        return weighted_mean_vec(values, weights)

    raise ValueError(f"Unknown pre-fusion algorithm: {algorithm}")


def run_case(algorithm, sigma2, sigma3, rounds, weight_mode, measurements):
    sat1 = lib.sim_create_context(1)
    if not sat1:
        raise RuntimeError("Failed to create requester context")

    try:
        if algorithm == "raw":
            lib.sim_clear_correction_filter(sat1)
        elif algorithm == "weighted_median":
            lib.sim_use_weighted_median_filter(sat1)
        elif algorithm in ("kalman", "nis_gated_kalman", "diwkcf", "ransac_kalman", "gossip_kalman"):
            lib.sim_use_kalman_filter(sat1, ctypes.c_float(0.02), ctypes.c_float(0.8))
        elif algorithm == "hybrid":
            lib.sim_use_hybrid_filter(sat1, ctypes.c_float(0.02), ctypes.c_float(0.8))
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

        seqs = [1] * 8
        ts = 100

        raw_acc = 0.0
        corr_acc = 0.0
        raw_ss_acc = 0.0
        corr_ss_acc = 0.0
        ss_count = 0
        pred = None
        nis_ema_2 = 1.0
        nis_ema_3 = 1.0
        converge_round = None
        # chi-square threshold for 3 DoF at ~99% confidence.
        chi2_3d_base = 11.345

        for r in range(1, rounds + 1):
            lib.sim_inject_event(sat1, EVT_FAULT_DETECTED)

            readings = [tuple(v) for v in measurements[r - 1]]
            sigmas = [sigma2, sigma3]
            if len(readings) > len(sigmas):
                sigmas.extend([sigmas[-1]] * (len(readings) - len(sigmas)))
            sigmas = sigmas[:len(readings)]

            raw_x, raw_y, raw_z = mean_vec(readings)

            degrs = [
                degr_from_error(vec_err(x, y, z), sigma, weight_mode)
                for (x, y, z), sigma in zip(readings, sigmas)
            ]

            if algorithm == "nis_gated_kalman" and pred is not None:
                px, py, pz = pred
                (m2x, m2y, m2z) = readings[0]
                (m3x, m3y, m3z) = readings[1] if len(readings) > 1 else readings[0]
                nis2 = nis_3d(m2x, m2y, m2z, px, py, pz, sigma2)
                nis3 = nis_3d(m3x, m3y, m3z, px, py, pz, sigma3)

                # Adaptive gate: if recent NIS is generally high, loosen threshold; if low, tighten.
                adapt2 = clamp(nis_ema_2, 0.7, 3.0)
                adapt3 = clamp(nis_ema_3, 0.7, 3.0)
                thr2 = chi2_3d_base * adapt2
                thr3 = chi2_3d_base * adapt3

                if nis2 > thr2:
                    degrs[0] = 15
                if nis3 > thr3:
                    if len(degrs) > 1:
                        degrs[1] = 15

                nis_ema_2 = (0.9 * nis_ema_2) + (0.1 * nis2)
                nis_ema_3 = (0.9 * nis_ema_3) + (0.1 * nis3)

            if algorithm in ("diwkcf", "ransac_kalman", "gossip_kalman"):
                fused = pre_fuse_measurement(algorithm, readings, degrs, sigmas, r)
                lib.sim_inject_correction_rsp(
                    sat1, 2, seqs[0], 0, SENSOR_MAGNETOMETER,
                    fused[0], fused[1], fused[2], ts
                )
            else:
                for idx, ((mx, my, mz), degr) in enumerate(zip(readings, degrs)):
                    sender = 2 + idx
                    lib.sim_inject_correction_rsp(
                        sat1, sender, seqs[idx], degr, SENSOR_MAGNETOMETER,
                        mx, my, mz, ts + idx
                    )

            lib.sim_advance_time(sat1, 5100)

            corrected = (ctypes.c_float * 3)()
            lib.sim_get_corrected(sat1, corrected)
            cx, cy, cz = float(corrected[0]), float(corrected[1]), float(corrected[2])
            pred = (cx, cy, cz)

            lib.sim_inject_event(sat1, EVT_CORRECTION_DONE)

            raw_err = vec_err(raw_x, raw_y, raw_z)
            corr_err = vec_err(cx, cy, cz)
            if converge_round is None and corr_err < 2.0:
                converge_round = r
            raw_acc += raw_err
            corr_acc += corr_err

            if r > rounds // 3:
                raw_ss_acc += raw_err
                corr_ss_acc += corr_err
                ss_count += 1

            for idx in range(len(seqs)):
                seqs[idx] = (seqs[idx] + 1) & 0xFF
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
            "raw_error": avg_raw_ss,
            "corrected_error": avg_corr_ss,
            "gain": avg_raw_ss - avg_corr_ss,
            "converge_round": converge_round,
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


def print_outlier_table(title, rows):
    print(f"\n{title}")
    print("scenario                      algo             raw(ss)  corr(ss) gain(ss)")
    print("----------------------------  ---------------  -------  -------- --------")
    for row in rows:
        print(
            f"{row['scenario']:<28}  {row['algo']:<15}  "
            f"{row['avg_raw_ss']:>7.3f}  {row['avg_corr_ss']:>8.3f} {row['ss_gain']:>8.3f}"
        )


def format_metric_cell(stats):
    conv = stats["converge_round"] if stats["converge_round"] is not None else "-"
    return f"{stats['corrected_error']:.2f}/{stats['raw_error']:.2f}/{stats['gain']:+.2f}/{conv}"


def print_full_comparison_table(rows):
    columns = [
        ("weighted_median", "WeightedMedian"),
        ("kalman", "Kalman"),
        ("nis_gated_kalman", "NIS-Kalman"),
        ("hybrid", "Hybrid"),
        ("diwkcf", "DIWKCF"),
        ("ransac_kalman", "RANSAC-Kalman"),
        ("gossip_kalman", "Gossip-Kalman"),
    ]
    print("\n--- Full algorithm comparison ---")
    print("Cell format: corrected_error/raw_error/gain/converge_round")
    print("| Scenario | " + " | ".join(label for _, label in columns) + " |")
    print("|---|" + "|".join("---" for _ in columns) + "|")
    for row in rows:
        cells = [format_metric_cell(row["results"][algo]) for algo, _ in columns]
        print(f"| {row['scenario']} | " + " | ".join(cells) + " |")


def build_requested_comparison_scenarios(rounds):
    return [
        {
            "name": "Gaussian sigma=2",
            "sigma2": 2.0,
            "sigma3": 2.0,
            "measurements": generate_measurements(rounds, 2.0, seed=260602),
        },
        {
            "name": "Gaussian sigma=20",
            "sigma2": 20.0,
            "sigma3": 20.0,
            "measurements": generate_measurements(rounds, 20.0, seed=260620),
        },
        {
            "name": "Gaussian sigma=60",
            "sigma2": 60.0,
            "sigma3": 60.0,
            "measurements": generate_measurements(rounds, 60.0, seed=260660),
        },
        {
            "name": "Burst outlier 5pct 5x",
            "sigma2": 8.0,
            "sigma3": 8.0,
            "measurements": generate_burst_outlier_measurements(
                rounds=rounds,
                base_sigma=8.0,
                outlier_sigma=40.0,
                outlier_prob=0.05,
                seed=260705,
            ),
        },
        {
            "name": "Burst outlier 15pct 5x",
            "sigma2": 8.0,
            "sigma3": 8.0,
            "measurements": generate_burst_outlier_measurements(
                rounds=rounds,
                base_sigma=8.0,
                outlier_sigma=40.0,
                outlier_prob=0.15,
                seed=260715,
            ),
        },
        {
            "name": "Persistent bias sat3 +40",
            "sigma2": 2.0,
            "sigma3": 2.0,
            "measurements": generate_persistent_biased_measurements(
                rounds=rounds,
                healthy_sigma=2.0,
                noisy_sigma=2.0,
                bias_xyz=(40.0, 40.0, 40.0),
                seed=260740,
            ),
        },
        {
            "name": "Mixed spike plus drift",
            "sigma2": 10.0,
            "sigma3": 10.0,
            "measurements": generate_mixed_spike_drift_measurements(
                rounds=rounds,
                base_sigma=10.0,
                spike_sigma=50.0,
                spike_prob=0.10,
                drift_per_round=0.35,
                seed=260799,
            ),
        },
    ]


def run_requested_full_comparison(rounds=110):
    algorithms = [
        "weighted_median",
        "kalman",
        "nis_gated_kalman",
        "hybrid",
        "diwkcf",
        "ransac_kalman",
        "gossip_kalman",
    ]
    rows = []
    for scenario in build_requested_comparison_scenarios(rounds):
        results = {}
        for algo in algorithms:
            results[algo] = run_case(
                algo,
                scenario["sigma2"],
                scenario["sigma3"],
                rounds,
                "inverse_error",
                scenario["measurements"],
            )
        rows.append({"scenario": scenario["name"], "results": results})
    print_full_comparison_table(rows)


def run_outlier_scenario_matrix(rounds=110):
    algorithms = ["raw", "weighted_median", "kalman", "nis_gated_kalman", "hybrid", "diwkcf", "ransac_kalman", "gossip_kalman"]
    scenarios = [
        {
            "name": "burst_5pct_heavy",
            "sigma2": 8.0,
            "sigma3": 8.0,
            "measurements": generate_burst_outlier_measurements(
                rounds=rounds,
                base_sigma=8.0,
                outlier_sigma=75.0,
                outlier_prob=0.05,
                seed=20260418,
            ),
        },
        {
            "name": "burst_15pct_moderate",
            "sigma2": 10.0,
            "sigma3": 10.0,
            "measurements": generate_burst_outlier_measurements(
                rounds=rounds,
                base_sigma=10.0,
                outlier_sigma=45.0,
                outlier_prob=0.15,
                seed=20260419,
            ),
        },
        {
            "name": "persistent_bias_peer3",
            "sigma2": 2.0,
            "sigma3": 30.0,
            "measurements": generate_persistent_biased_measurements(
                rounds=rounds,
                healthy_sigma=2.0,
                noisy_sigma=30.0,
                bias_xyz=(35.0, -20.0, 12.0),
                seed=20260420,
            ),
        },
        {
            "name": "mixed_spike_plus_drift",
            "sigma2": 12.0,
            "sigma3": 12.0,
            "measurements": generate_mixed_outlier_measurements(
                rounds=rounds,
                base_sigma=12.0,
                outlier_sigma=70.0,
                outlier_prob=0.10,
                seed=20260421,
            ),
        },
    ]

    rows = []
    for scenario in scenarios:
        for algo in algorithms:
            stats = run_case(
                algo,
                scenario["sigma2"],
                scenario["sigma3"],
                rounds,
                "inverse_error",
                scenario["measurements"],
            )
            rows.append(
                {
                    "scenario": scenario["name"],
                    "algo": algo,
                    "avg_raw_ss": stats["avg_raw_ss"],
                    "avg_corr_ss": stats["avg_corr_ss"],
                    "ss_gain": stats["ss_gain"],
                }
            )

    print_outlier_table("--- outlier stress scenarios (inverse-error DEGR) ---", rows)


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
    algorithms = ["raw", "weighted_median", "kalman", "nis_gated_kalman", "hybrid", "diwkcf", "ransac_kalman", "gossip_kalman"]
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

    run_outlier_scenario_matrix(rounds=110)
    run_requested_full_comparison(rounds=110)

    run_kalman_degr_sensitivity(rounds=140, healthy_sigma=2.0, broken_sigma=50.0)
    benchmark_runtime_budget(rounds=500, sigma=30.0)


if __name__ == "__main__":
    main()
