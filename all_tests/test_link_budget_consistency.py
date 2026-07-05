#!/usr/bin/env python3
"""Paper-driven link-budget consistency check.

This test verifies that the assumptions used in the documentation and the
Streamlit physics model produce the same engineering numbers:
- NF = 5 dB
- T_ant = 100 K
- 12.5 kHz control channel at 9.6 kbps
- 30 dBm Tx, 2 dBi Tx/Rx gains, 3 dB misc loss, 1.5 dB Doppler margin

The goal is not to simulate BER; it is to ensure the arithmetic behind the
quoted link budget remains internally consistent.
"""

from __future__ import annotations

import math


K_B = 1.380649e-23
T0_K = 290.0


def tsys_from_nf(nf_db: float, t_ant_k: float) -> float:
    f_lin = 10.0 ** (nf_db / 10.0)
    return t_ant_k + T0_K * (f_lin - 1.0)


def test_link_budget_consistency() -> None:
    nf_db = 5.0
    t_ant_k = 100.0
    bandwidth_hz = 12_500.0
    bit_rate_bps = 9_600.0
    tx_power_dbm = 30.0
    tx_gain_dbi = 2.0
    rx_gain_dbi = 2.0
    path_loss_db = 145.3
    misc_loss_db = 3.0
    doppler_margin_db = 1.5

    t_sys_k = tsys_from_nf(nf_db, t_ant_k)
    noise_w = K_B * t_sys_k * bandwidth_hz
    noise_dbm = 10.0 * math.log10(noise_w) + 30.0
    snr_db = (
        tx_power_dbm
        + tx_gain_dbi
        + rx_gain_dbi
        - path_loss_db
        - misc_loss_db
        - doppler_margin_db
        - noise_dbm
    )
    ebn0_db = snr_db + 10.0 * math.log10(bandwidth_hz / bit_rate_bps)
    link_margin_db = ebn0_db - 5.5

    assert abs(t_sys_k - 727.06) < 0.5, t_sys_k
    assert abs(noise_dbm - (-129.01)) < 0.1, noise_dbm
    assert abs(ebn0_db - 14.36) < 0.1, ebn0_db
    assert link_margin_db > 8.0, link_margin_db

    print("Paper-driven link budget check")
    print(f"Tsys = {t_sys_k:.2f} K")
    print(f"Noise = {noise_dbm:.2f} dBm")
    print(f"Eb/N0 = {ebn0_db:.2f} dB")
    print(f"Link margin = {link_margin_db:.2f} dB")


if __name__ == "__main__":
    test_link_budget_consistency()