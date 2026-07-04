#!/usr/bin/env python3
import math

from test_large_constellation_data_recovery import (
    ALGORITHMS,
    generate_large_constellation_rounds,
    load_truth_vectors,
    run_dynamic_case,
)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def degr_from_target_weight(weight):
    return int(round(clamp(1.0 - weight, 0.0, 1.0) * 15.0))


def make_linear_policy(weight_floor=0.05, scale=3.0, exponent=1.0):
    def policy(err_mag, sigma):
        normalized = clamp(err_mag / max(1e-6, scale * sigma), 0.0, 1.0)
        shaped = normalized ** exponent
        weight = weight_floor + (1.0 - weight_floor) * (1.0 - shaped)
        return degr_from_target_weight(weight)

    return policy


def binary_threshold_policy(threshold_sigma=2.5, good_weight=1.0, bad_weight=0.05):
    def policy(err_mag, sigma):
        normalized = err_mag / max(1e-6, sigma)
        weight = bad_weight if normalized > threshold_sigma else good_weight
        return degr_from_target_weight(weight)

    return policy


POLICIES = [
    ("linear_floor_5pct", make_linear_policy(weight_floor=0.05, scale=3.0, exponent=1.0)),
    ("linear_floor_25pct", make_linear_policy(weight_floor=0.25, scale=3.0, exponent=1.0)),
    ("linear_floor_50pct", make_linear_policy(weight_floor=0.50, scale=3.0, exponent=1.0)),
    ("soft_sqrt_floor_5pct", make_linear_policy(weight_floor=0.05, scale=3.0, exponent=0.5)),
    ("aggressive_square_floor_5pct", make_linear_policy(weight_floor=0.05, scale=3.0, exponent=2.0)),
    ("wide_scale_floor_5pct", make_linear_policy(weight_floor=0.05, scale=5.0, exponent=1.0)),
    ("binary_2sigma_floor_5pct", binary_threshold_policy(threshold_sigma=2.0, bad_weight=0.05)),
    ("binary_3sigma_floor_5pct", binary_threshold_policy(threshold_sigma=3.0, bad_weight=0.05)),
]


def run_degr_policy_sweep(rounds=180, sat_count=8, algorithm_subset=None):
    truth = load_truth_vectors(rounds=rounds)
    rounds_data = generate_large_constellation_rounds(
        truth, sat_count=sat_count, seed=91300 + sat_count
    )
    algorithms = algorithm_subset or ["weighted_median", "kalman", "nis_gated_kalman", "hybrid"]

    rows = []
    for policy_name, policy in POLICIES:
        results = {}
        for algorithm in algorithms:
            results[algorithm] = run_dynamic_case(
                algorithm,
                rounds_data,
                degr_policy=policy,
            )
        best_algorithm = min(results, key=lambda name: results[name]["steady_corr"])
        rows.append(
            {
                "policy": policy_name,
                "best_algorithm": best_algorithm,
                "best": results[best_algorithm],
                "results": results,
            }
        )
    rows.sort(key=lambda row: row["best"]["steady_corr"])
    return rows


def print_degr_policy_sweep(rows):
    print("\n=== DEGR policy sweep on data-driven constellation benchmark ===")
    print("Cell metrics: best_algorithm steady_corr gain p95_corr recovery_round")
    print("policy                         best_algorithm    steady_corr  gain     p95_corr  recovery")
    print("-----------------------------  ----------------  -----------  -------  --------  --------")
    for row in rows:
        best = row["best"]
        recovery = best["recovery_round"] if best["recovery_round"] is not None else "-"
        print(
            f"{row['policy']:<29}  {row['best_algorithm']:<16}  "
            f"{best['steady_corr']:>11.3f}  {best['gain']:>+7.3f}  "
            f"{best['p95_corr']:>8.3f}  {str(recovery):>8}"
        )

    print("\nPer-policy algorithm detail: steady_corr/gain")
    algorithms = list(rows[0]["results"].keys()) if rows else []
    print("| Policy | " + " | ".join(algorithms) + " |")
    print("|---|" + "|".join("---" for _ in algorithms) + "|")
    for row in rows:
        cells = [
            f"{row['results'][algorithm]['steady_corr']:.2f}/{row['results'][algorithm]['gain']:+.2f}"
            for algorithm in algorithms
        ]
        print(f"| {row['policy']} | " + " | ".join(cells) + " |")


def test_degr_policy_sweep_best_policy_not_50pct_floor():
    rows = run_degr_policy_sweep(rounds=180, sat_count=8)
    best_policy = rows[0]["policy"]
    assert best_policy != "linear_floor_50pct"
    assert rows[0]["best"]["gain"] > 0.0


if __name__ == "__main__":
    print_degr_policy_sweep(run_degr_policy_sweep(rounds=180, sat_count=8))
