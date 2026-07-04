#!/usr/bin/env python3
import math
import random

from test_large_constellation_data_recovery import (
    ALGORITHMS,
    load_truth_vectors,
    run_dynamic_case,
)


def laplace(rng, scale):
    u = rng.random() - 0.5
    return -scale * math.copysign(math.log(1.0 - 2.0 * abs(u)), u)


def student_t(rng, df, scale):
    numerator = rng.gauss(0.0, 1.0)
    denominator = math.sqrt(sum(rng.gauss(0.0, 1.0) ** 2 for _ in range(df)) / df)
    return scale * numerator / max(1e-6, denominator)


def quantize(v, step):
    return round(v / step) * step


def noisy_axis(rng, base, sigma, noise_type, sat_index, round_index):
    if noise_type == "gaussian":
        return base + rng.gauss(0.0, sigma), sigma
    if noise_type == "laplace":
        return base + laplace(rng, sigma / math.sqrt(2.0)), sigma * 1.4
    if noise_type == "student_t_df3":
        return base + student_t(rng, 3, sigma), sigma * 2.0
    if noise_type == "salt_pepper":
        if rng.random() < 0.10:
            return base + rng.choice((-1.0, 1.0)) * rng.uniform(14.0, 35.0), sigma * 5.0
        return base + rng.gauss(0.0, sigma), sigma
    if noise_type == "quantized":
        return quantize(base + rng.gauss(0.0, sigma), step=1.5), sigma * 1.2
    if noise_type == "mixed_realistic":
        value = base + rng.gauss(0.0, sigma)
        eff_sigma = sigma
        if rng.random() < 0.08:
            value += laplace(rng, sigma * 5.0)
            eff_sigma *= 4.0
        if sat_index == 2 and round_index > 70:
            drift = min(22.0, 0.28 * (round_index - 70))
            value += drift
            eff_sigma *= 3.0
        if rng.random() < 0.04:
            value = quantize(value, step=2.0)
            eff_sigma *= 1.5
        return value, eff_sigma
    raise ValueError(f"Unknown noise type: {noise_type}")


def generate_noise_type_rounds(truth, sat_count, noise_type, seed):
    rng = random.Random(seed)
    rounds = []
    for r, gt in enumerate(truth, start=1):
        readings = []
        sigmas = []
        events = []
        for sat in range(sat_count):
            sigma = 1.2 + 0.25 * (sat % 5)
            if noise_type in ("dropout", "mixed_realistic") and rng.random() < (0.05 + 0.01 * sat):
                events.append((sat + 2, "dropout"))
                continue

            coords = []
            eff_sigmas = []
            axis_noise = "gaussian" if noise_type == "dropout" else noise_type
            for axis_value in gt:
                value, eff_sigma = noisy_axis(rng, axis_value, sigma, axis_noise, sat, r)
                coords.append(value)
                eff_sigmas.append(eff_sigma)

            readings.append(tuple(coords))
            sigmas.append(max(eff_sigmas))

        rounds.append(
            {
                "truth": gt,
                "readings": readings,
                "sigmas": sigmas,
                "phase": noise_type,
                "events": events,
            }
        )
    return rounds


def run_noise_type_matrix(rounds=180, sat_count=8):
    truth = load_truth_vectors(rounds=rounds)
    noise_types = [
        "gaussian",
        "laplace",
        "student_t_df3",
        "salt_pepper",
        "quantized",
        "dropout",
        "mixed_realistic",
    ]

    rows = []
    for noise_type in noise_types:
        rounds_data = generate_noise_type_rounds(
            truth,
            sat_count=sat_count,
            noise_type=noise_type,
            seed=52200 + len(noise_type),
        )
        results = {
            algorithm: run_dynamic_case(algorithm, rounds_data)
            for algorithm in ALGORITHMS
        }
        best_algorithm = min(results, key=lambda name: results[name]["steady_corr"])
        rows.append(
            {
                "noise_type": noise_type,
                "best_algorithm": best_algorithm,
                "best": results[best_algorithm],
                "results": results,
            }
        )
    return rows


def print_noise_type_matrix(rows):
    print("\n=== Noise-type robustness benchmark ===")
    print("Data source: data/raw/segments.csv channel CADC0873")
    print("Cell format: steady_corr/gain/p95_corr")
    print("| Noise type | Best | " + " | ".join(ALGORITHMS) + " |")
    print("|---|---|" + "|".join("---" for _ in ALGORITHMS) + "|")
    for row in rows:
        cells = [
            f"{row['results'][algorithm]['steady_corr']:.2f}/{row['results'][algorithm]['gain']:+.2f}/{row['results'][algorithm]['p95_corr']:.2f}"
            for algorithm in ALGORITHMS
        ]
        print(f"| {row['noise_type']} | {row['best_algorithm']} | " + " | ".join(cells) + " |")


def test_noise_type_robustness_has_positive_best_gain():
    rows = run_noise_type_matrix(rounds=180, sat_count=8)
    for row in rows:
        assert row["best"]["steady_corr"] < 1.6, row["noise_type"]
        if row["noise_type"] in ("laplace", "student_t_df3", "salt_pepper", "mixed_realistic"):
            assert row["best"]["gain"] > 0.0, row["noise_type"]


if __name__ == "__main__":
    print_noise_type_matrix(run_noise_type_matrix(rounds=180, sat_count=8))
