"""BPSK/AWGN sanity check.

Runs a Monte‑Carlo simulation of coherent BPSK over AWGN and compares the
measured BER to the theoretical BER:

    BER = 0.5 * erfc(sqrt(Eb/N0))

This is useful to validate Eb/N0↔noise variance conversions used elsewhere.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Result:
    ebn0_db: float
    ber_theory: float
    ber_sim: float
    errors: int
    bits: int


def ber_bpsk_theory(ebn0_db: float) -> float:
    ebn0_lin = 10 ** (ebn0_db / 10.0)
    return 0.5 * math.erfc(math.sqrt(ebn0_lin))


def ber_bpsk_sim(ebn0_db: float, n_bits: int, rng: np.random.Generator) -> tuple[float, int]:
    # BPSK symbols: 0 -> +1, 1 -> -1
    bits = rng.integers(0, 2, size=n_bits, dtype=np.int8)
    symbols = 1.0 - 2.0 * bits

    # With Eb=1 and coherent demod, AWGN variance per real dimension is:
    #   sigma^2 = N0/2 = 1 / (2 * Eb/N0)
    ebn0_lin = 10 ** (ebn0_db / 10.0)
    sigma = math.sqrt(1.0 / (2.0 * ebn0_lin))
    noise = rng.normal(0.0, sigma, size=n_bits)

    rx = symbols + noise
    bits_hat = (rx < 0.0).astype(np.int8)

    errors = int(np.count_nonzero(bits_hat != bits))
    return errors / n_bits, errors


def run(ebn0_values_db: list[float], n_bits: int, seed: int) -> list[Result]:
    rng = np.random.default_rng(seed)
    results: list[Result] = []
    for ebn0_db in ebn0_values_db:
        ber_sim, errors = ber_bpsk_sim(ebn0_db, n_bits=n_bits, rng=rng)
        results.append(
            Result(
                ebn0_db=float(ebn0_db),
                ber_theory=ber_bpsk_theory(ebn0_db),
                ber_sim=ber_sim,
                errors=errors,
                bits=n_bits,
            )
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ebn0-db",
        type=float,
        nargs="*",
        default=[0, 2, 4, 6, 8, 10],
        help="Eb/N0 values (dB) to test",
    )
    parser.add_argument("--bits", type=int, default=2_000_000, help="bits per point")
    parser.add_argument("--seed", type=int, default=0, help="random seed")
    args = parser.parse_args()

    results = run(list(args.ebn0_db), n_bits=int(args.bits), seed=int(args.seed))

    header = f"{'Eb/N0(dB)':>8}  {'BER_theory':>12}  {'BER_sim':>12}  {'errors':>8}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(f"{r.ebn0_db:8.2f}  {r.ber_theory:12.4e}  {r.ber_sim:12.4e}  {r.errors:8d}")


if __name__ == "__main__":
    main()
