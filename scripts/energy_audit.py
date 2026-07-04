"""Reproducible SISP link-energy audit.

The values printed here are the canonical numbers used in the paper and
energy-study docs. They are intentionally first-order DC energy numbers:
radio TX/RX power multiplied by on-air frame time.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass


C_KM_S = 299_792.458


@dataclass(frozen=True)
class EnergyAssumptions:
    tx_power_w: float = 10.0
    rx_power_w: float = 2.5
    frame_bytes: int = 64
    conv_rate: float = 0.5
    rs_data_symbols: int = 223
    rs_total_symbols: int = 255
    control_bps: float = 9_600.0
    bulk_bps: float = 19_200.0
    useful_payload_bytes: int = 45
    compression_ratio: float = 3.0
    relay_per: float = 0.001
    range_km: float = 1000.0

    @property
    def frame_bits(self) -> int:
        return self.frame_bytes * 8

    @property
    def coding_expansion(self) -> float:
        rs_rate = self.rs_data_symbols / self.rs_total_symbols
        return 1.0 / (self.conv_rate * rs_rate)

    @property
    def air_bits_per_frame(self) -> float:
        return self.frame_bits * self.coding_expansion

    @property
    def control_frame_s(self) -> float:
        return self.air_bits_per_frame / self.control_bps

    @property
    def bulk_frame_s(self) -> float:
        return self.air_bits_per_frame / self.bulk_bps

    @property
    def propagation_s(self) -> float:
        return self.range_km / C_KM_S


@dataclass(frozen=True)
class CorrectionEnergy:
    neighbours: int
    frame_time_s: float
    event_time_s: float
    requester_tx_j: float
    neighbours_rx_j: float
    neighbours_tx_j: float
    requester_rx_j: float

    @property
    def requester_total_j(self) -> float:
        return self.requester_tx_j + self.requester_rx_j

    @property
    def network_total_j(self) -> float:
        return (
            self.requester_tx_j
            + self.neighbours_rx_j
            + self.neighbours_tx_j
            + self.requester_rx_j
        )


@dataclass(frozen=True)
class RelayEnergy:
    raw_bytes: int
    effective_bytes: float
    frames: int
    expected_tx_frames: float
    time_s: float
    tx_j: float
    rx_j: float

    @property
    def total_j(self) -> float:
        return self.tx_j + self.rx_j


def correction_energy(a: EnergyAssumptions, neighbours: int) -> CorrectionEnergy:
    t = a.control_frame_s
    return CorrectionEnergy(
        neighbours=neighbours,
        frame_time_s=t,
        event_time_s=(1 + neighbours) * t + 2.0 * a.propagation_s,
        requester_tx_j=a.tx_power_w * t,
        neighbours_rx_j=neighbours * a.rx_power_w * t,
        neighbours_tx_j=neighbours * a.tx_power_w * t,
        requester_rx_j=neighbours * a.rx_power_w * t,
    )


def relay_energy(a: EnergyAssumptions, mib: float) -> RelayEnergy:
    raw_bytes = int(round(mib * 1024 * 1024))
    effective_bytes = raw_bytes / a.compression_ratio
    frames = math.ceil(effective_bytes / a.useful_payload_bytes)
    expected_tx_frames = frames / (1.0 - a.relay_per)
    time_s = expected_tx_frames * a.bulk_frame_s
    return RelayEnergy(
        raw_bytes=raw_bytes,
        effective_bytes=effective_bytes,
        frames=frames,
        expected_tx_frames=expected_tx_frames,
        time_s=time_s,
        tx_j=time_s * a.tx_power_w,
        rx_j=time_s * a.rx_power_w,
    )


def fmt_j_wh(joules: float) -> str:
    return f"{joules:.1f} J = {joules / 3600.0:.4f} Wh"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--neighbours", type=int, default=8)
    parser.add_argument("--corrections-per-day", type=int, default=24)
    parser.add_argument("--heartbeats-per-hour", type=int, default=12)
    parser.add_argument("--relay-mib", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    a = EnergyAssumptions()
    corr = correction_energy(a, args.neighbours)
    relay_1 = relay_energy(a, args.relay_mib)
    relay_10 = relay_energy(a, 10.0)

    hb_frames_per_day = args.heartbeats_per_hour * 24
    hb_tx_day_j = hb_frames_per_day * a.tx_power_w * a.control_frame_s
    hb_rx_day_j = hb_frames_per_day * args.neighbours * a.rx_power_w * a.control_frame_s

    print("# SISP Energy Audit")
    print()
    print("## Assumptions")
    print(f"- Physical frame: {a.frame_bytes} bytes = {a.frame_bits} bits")
    print(f"- Conv+RS expansion: {a.coding_expansion:.6f}x")
    print(f"- Air bits per frame: {a.air_bits_per_frame:.1f} bits")
    print(f"- Control PHY: {a.control_bps:,.0f} bps, frame time {a.control_frame_s * 1000:.2f} ms")
    print(f"- Bulk PHY: {a.bulk_bps:,.0f} bps, frame time {a.bulk_frame_s * 1000:.2f} ms")
    print(f"- TX/RX DC power: {a.tx_power_w:g} W / {a.rx_power_w:g} W")
    print(f"- Relay payload: {a.useful_payload_bytes} useful bytes per frame, compression {a.compression_ratio:g}x, PER {a.relay_per:.3%}")
    print()
    print(f"## Correction Event (N={args.neighbours})")
    print(f"- On-air time: {corr.event_time_s * 1000:.1f} ms including 2x propagation at {a.range_km:g} km")
    print(f"- Requester TX: {corr.requester_tx_j:.3f} J")
    print(f"- Requester RX: {corr.requester_rx_j:.3f} J")
    print(f"- Neighbours RX total: {corr.neighbours_rx_j:.3f} J")
    print(f"- Neighbours TX total: {corr.neighbours_tx_j:.3f} J")
    print(f"- Requester battery per event: {corr.requester_total_j:.3f} J")
    print(f"- Network total per event: {corr.network_total_j:.3f} J")
    print(f"- Requester daily @ {args.corrections_per_day}/day: {fmt_j_wh(corr.requester_total_j * args.corrections_per_day)}")
    print(f"- Network daily @ {args.corrections_per_day}/day: {fmt_j_wh(corr.network_total_j * args.corrections_per_day)}")
    print()
    print("## Heartbeat Maintenance")
    print(f"- Assumed heartbeat cadence: {args.heartbeats_per_hour}/hour = {hb_frames_per_day}/day")
    print(f"- Own heartbeat TX: {fmt_j_wh(hb_tx_day_j)}")
    print(f"- RX of {args.neighbours} neighbours' heartbeats: {fmt_j_wh(hb_rx_day_j)}")
    print(f"- Own heartbeat TX+RX participation: {fmt_j_wh(hb_tx_day_j + hb_rx_day_j)}")
    print()
    print(f"## Relay Dump ({args.relay_mib:g} MiB)")
    print(f"- Effective bytes after compression: {relay_1.effective_bytes:,.0f}")
    print(f"- Frames: {relay_1.frames:,}; expected TX frames with ARQ: {relay_1.expected_tx_frames:,.1f}")
    print(f"- Time: {relay_1.time_s:.1f} s = {relay_1.time_s / 60.0:.2f} min")
    print(f"- Sender TX: {fmt_j_wh(relay_1.tx_j)}")
    print(f"- Receiver RX: {fmt_j_wh(relay_1.rx_j)}")
    print(f"- Link total: {fmt_j_wh(relay_1.total_j)}")
    print()
    print("## Relay Dump (10 MiB Reference)")
    print(f"- Frames: {relay_10.frames:,}; expected TX frames with ARQ: {relay_10.expected_tx_frames:,.1f}")
    print(f"- Time: {relay_10.time_s / 60.0:.2f} min")
    print(f"- Link total: {relay_10.total_j / 3600.0:.3f} Wh")


if __name__ == "__main__":
    main()
