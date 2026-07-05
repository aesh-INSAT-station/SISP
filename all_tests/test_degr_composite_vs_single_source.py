#!/usr/bin/env python3
import math
import os
import random

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


SAT_COUNT = 5
DAYS = 30
DRIFT_SAT_INDEX = 2
DETECT_THRESHOLD = 8.0
TRUE_READING = np.array([42.0, -17.5, 9.25], dtype=float)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def residual_to_degr(residual, scale):
    return 15.0 * clamp(residual / max(1e-6, scale), 0.0, 1.0)


def generate_satellite_history(days=DAYS, seed=20260613):
    rng = random.Random(seed)
    history = np.zeros((days, SAT_COUNT, 3), dtype=float)
    for day in range(days):
        for sat in range(SAT_COUNT):
            noise = np.array([rng.gauss(0.0, 0.8) for _ in range(3)])
            drift = np.zeros(3, dtype=float)
            if sat == DRIFT_SAT_INDEX:
                drift_mag = max(0, day - 5) * 0.75
                drift = np.array([drift_mag, -0.45 * drift_mag, 0.25 * drift_mag])
            history[day, sat] = TRUE_READING + noise + drift
    return history


def kalman_residual_degr(history):
    estimates = history[0].copy()
    degr = np.zeros((history.shape[0], SAT_COUNT), dtype=float)
    alpha = 0.22
    for day in range(history.shape[0]):
        for sat in range(SAT_COUNT):
            residual = float(np.linalg.norm(history[day, sat] - estimates[sat]))
            degr[day, sat] = residual_to_degr(residual, scale=9.0)
            estimates[sat] = (1.0 - alpha) * estimates[sat] + alpha * history[day, sat]
    return degr


def svd_residual_degr(history):
    degr = np.zeros((history.shape[0], SAT_COUNT), dtype=float)
    for day in range(history.shape[0]):
        window = history[max(0, day - 6) : day + 1].reshape(-1, 3)
        center = window.mean(axis=0)
        centered = window - center
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        basis = vt[:1].T
        for sat in range(SAT_COUNT):
            point = history[day, sat] - center
            reconstructed = basis @ (basis.T @ point)
            residual = float(np.linalg.norm(point - reconstructed))
            degr[day, sat] = residual_to_degr(residual, scale=8.0)
    return degr


def composite_degr(kalman_degr, svd_degr):
    age_degr = np.zeros_like(kalman_degr)
    for sat in range(SAT_COUNT):
        days_since_low_residual = 0
        for day in range(kalman_degr.shape[0]):
            if max(kalman_degr[day, sat], svd_degr[day, sat]) < 3.0:
                days_since_low_residual = 0
            else:
                days_since_low_residual += 1
            age_degr[day, sat] = residual_to_degr(days_since_low_residual, scale=12.0)

    return np.clip((0.70 * kalman_degr) + (0.20 * svd_degr) + (0.10 * age_degr), 0.0, 15.0)


def first_detection_day(series, threshold=DETECT_THRESHOLD):
    hits = np.where(series >= threshold)[0]
    return int(hits[0]) if len(hits) else None


def false_alarm_count(degr_matrix, threshold=DETECT_THRESHOLD):
    healthy = np.delete(degr_matrix, DRIFT_SAT_INDEX, axis=1)
    return int(np.sum(healthy >= threshold))


def steady_state_error(degr_matrix):
    target = np.zeros_like(degr_matrix[-7:])
    target[:, DRIFT_SAT_INDEX] = 15.0
    return float(np.mean(np.abs(degr_matrix[-7:] - target)))


def summarize_variant(name, degr_matrix):
    return {
        "name": name,
        "time_to_detect": first_detection_day(degr_matrix[:, DRIFT_SAT_INDEX]),
        "false_alarm_count": false_alarm_count(degr_matrix),
        "steady_state_error": steady_state_error(degr_matrix),
    }


def plot_variants(variants, out_path):
    days = np.arange(DAYS)
    fig, axes = plt.subplots(len(variants), 1, figsize=(10, 8), sharex=True)
    for ax, (name, degr_matrix) in zip(axes, variants):
        for sat in range(SAT_COUNT):
            label = f"sat{sat + 1}"
            linewidth = 2.2 if sat == DRIFT_SAT_INDEX else 1.2
            ax.plot(days, degr_matrix[:, sat], label=label, linewidth=linewidth)
        ax.axhline(DETECT_THRESHOLD, color="black", linestyle="--", linewidth=1.0)
        ax.set_ylabel(name)
        ax.set_ylim(0, 15.5)
        ax.grid(True, alpha=0.25)
    axes[-1].set_xlabel("day")
    axes[0].legend(ncol=5, loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def run_degr_validation():
    history = generate_satellite_history()
    kalman_only = kalman_residual_degr(history)
    svd_only = svd_residual_degr(history)
    composite = composite_degr(kalman_only, svd_only)

    variants = [
        ("Kalman residual", kalman_only),
        ("SVD residual", svd_only),
        ("Composite", composite),
    ]
    out_path = os.path.join(os.path.dirname(__file__), "degr_composite_vs_single_source.png")
    plot_variants(variants, out_path)

    report = [summarize_variant(name, degr) for name, degr in variants]
    print("\n--- DEGR composite vs single-source validation ---")
    print(f"plot={out_path}")
    print("variant           time_to_detect  false_alarm_count  steady_state_error")
    print("----------------  --------------  -----------------  ------------------")
    for row in report:
        detect = row["time_to_detect"] if row["time_to_detect"] is not None else "-"
        print(
            f"{row['name']:<16}  {str(detect):>14}  "
            f"{row['false_alarm_count']:>17}  {row['steady_state_error']:>18.3f}"
        )
    return report


def test_degr_composite_vs_single_source():
    report = run_degr_validation()
    composite = next(row for row in report if row["name"] == "Composite")
    assert composite["time_to_detect"] is not None
    assert composite["time_to_detect"] <= 24
    assert composite["false_alarm_count"] <= 8


if __name__ == "__main__":
    run_degr_validation()
