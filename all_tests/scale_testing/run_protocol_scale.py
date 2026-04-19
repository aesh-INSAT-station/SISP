#!/usr/bin/env python3
import argparse
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "Scripts" / "python.exe"

TESTS = {
    "correction": ROOT / "all_tests" / "test_noise_weighting_and_algorithms.py",
    "integration": ROOT / "all_tests" / "test_integration_matrix_it02_it03_it05_it06.py",
    "relay": ROOT / "all_tests" / "test_relay_text_resilience.py",
    "full": ROOT / "all_tests" / "test_full_message_propagation_sensor_correction.py",
    "borrow": ROOT / "all_tests" / "test_borrow_addressing_flow.py",
}

TIERS = {
    "quick": ["integration", "relay", "full"],
    "medium": ["integration", "relay", "full", "borrow"],
    "heavy": ["correction", "integration", "relay", "full", "borrow"],
}


def run_one(label: str, script: Path) -> tuple[bool, float, str]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        [str(PY), str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    dt = time.perf_counter() - t0
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, dt, out


def main() -> int:
    parser = argparse.ArgumentParser(description="Scale-testing runner for full SISP protocol test set")
    parser.add_argument("--tier", choices=TIERS.keys(), default="medium")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    if not PY.exists():
        print(f"Python environment not found at: {PY}")
        return 2

    selected = TIERS[args.tier]
    print(f"Scale tier: {args.tier} | repeats: {args.repeats}")

    durations = {k: [] for k in selected}

    for i in range(1, args.repeats + 1):
        print(f"\n=== Iteration {i}/{args.repeats} ===")
        for key in selected:
            ok, dt, out = run_one(key, TESTS[key])
            durations[key].append(dt)
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {key:12s} {dt:7.3f}s")
            if not ok:
                print("--- output start ---")
                print(out[-4000:])
                print("--- output end ---")
                if args.fail_fast:
                    return 1

    print("\n=== Summary ===")
    total = 0.0
    for key in selected:
        vals = durations[key]
        mean = statistics.mean(vals)
        p95 = max(vals) if len(vals) < 20 else statistics.quantiles(vals, n=20)[18]
        total += sum(vals)
        print(f"{key:12s} mean={mean:7.3f}s p95={p95:7.3f}s runs={len(vals)}")
    print(f"Total wall-clock (sum): {total:7.3f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
