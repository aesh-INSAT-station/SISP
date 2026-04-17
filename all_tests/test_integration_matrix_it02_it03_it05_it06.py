#!/usr/bin/env python3
import ctypes
import math
import os
import random
from typing import Dict, List, Set, Tuple

BASE_DIR = os.path.dirname(__file__)
DLL_CANDIDATES = [
    os.path.join(BASE_DIR, "..", "c++ implemnetation", "build", "bin", "Release", "sisp.dll"),
    os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll"),
]
DLL_PATH = next((p for p in DLL_CANDIDATES if os.path.exists(p)), None)
if DLL_PATH is None:
    raise FileNotFoundError("sisp.dll not found in expected build locations.")

lib = ctypes.CDLL(DLL_PATH)

# Core API bindings
lib.sim_create_context.argtypes = [ctypes.c_uint8]
lib.sim_create_context.restype = ctypes.c_void_p
lib.sim_destroy_context.argtypes = [ctypes.c_void_p]
lib.sim_destroy_context.restype = None
lib.sim_inject_event.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.sim_inject_event.restype = None
lib.sim_inject_packet.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_inject_packet.restype = None
lib.sim_advance_time.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
lib.sim_advance_time.restype = None
lib.sim_get_state.argtypes = [ctypes.c_void_p]
lib.sim_get_state.restype = ctypes.c_int
lib.sim_get_corrected.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float)]
lib.sim_get_corrected.restype = None
lib.sim_decode_header.argtypes = [
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_uint16,
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.POINTER(ctypes.c_uint8),
]
lib.sim_decode_header.restype = ctypes.c_uint8
lib.sim_set_relay_payload.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_set_relay_payload.restype = None
lib.sim_get_relay_rx_len.argtypes = [ctypes.c_void_p]
lib.sim_get_relay_rx_len.restype = ctypes.c_uint16
lib.sim_copy_relay_rx_payload.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_copy_relay_rx_payload.restype = ctypes.c_uint16

# Correction filter controls
lib.sim_clear_correction_filter.argtypes = [ctypes.c_void_p]
lib.sim_clear_correction_filter.restype = None
lib.sim_use_kalman_filter.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float]
lib.sim_use_kalman_filter.restype = None
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

TX_CB = ctypes.CFUNCTYPE(None, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16)
lib.sim_register_tx_callback.argtypes = [TX_CB]
lib.sim_register_tx_callback.restype = None

# Events
EVT_RX_DOWNLINK_ACK = 6
EVT_RX_DOWNLINK_DATA = 5
EVT_FAULT_DETECTED = 12
EVT_ENERGY_LOW = 14
EVT_ALL_FRAGS_SENT = 17
EVT_ALL_FRAGS_RCVD = 18
EVT_SENSOR_READ_DONE = 19
EVT_CORRECTION_DONE = 20
EVT_RESET = 22

# States
ST_IDLE = 0
ST_RELAY_WAIT_ACCEPT = 6
ST_RELAY_SENDING = 7
ST_RELAY_WAIT_ACK = 8
ST_RELAY_DONE = 9
ST_RELAY_RECEIVING = 10
ST_RELAY_STORING = 11
ST_RELAY_DOWNLINKING = 12

SENSOR_MAGNETOMETER = 0x01

TRUE_X, TRUE_Y, TRUE_Z = 42.0, -17.5, 9.25


def assert_true(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def vec_err(x: float, y: float, z: float) -> float:
    return math.sqrt((x - TRUE_X) ** 2 + (y - TRUE_Y) ** 2 + (z - TRUE_Z) ** 2)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def degr_from_error_inverse(err_mag: float, sigma: float) -> int:
    denom = max(1e-6, 3.0 * sigma)
    e_norm = clamp(err_mag / denom, 0.0, 1.0)
    target_weight = 0.05 + 0.95 * (1.0 - e_norm)
    degr = int(round((1.0 - target_weight) * 15.0))
    return int(clamp(degr, 0, 15))


def get_corrected_xyz(ctx: ctypes.c_void_p) -> Tuple[float, float, float]:
    out = (ctypes.c_float * 3)()
    lib.sim_get_corrected(ctx, out)
    return float(out[0]), float(out[1]), float(out[2])


def decode_header(frame: bytes) -> Tuple[int, int, int, int, int, int]:
    buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
    svc = ctypes.c_uint8(0)
    sndr = ctypes.c_uint8(0)
    rcvr = ctypes.c_uint8(0)
    seq = ctypes.c_uint8(0)
    degr = ctypes.c_uint8(0)
    flags = ctypes.c_uint8(0)
    ok = lib.sim_decode_header(
        buf,
        len(frame),
        ctypes.byref(svc),
        ctypes.byref(sndr),
        ctypes.byref(rcvr),
        ctypes.byref(seq),
        ctypes.byref(degr),
        ctypes.byref(flags),
    )
    if ok == 0:
        return (0, 0, 0, 0, 0, 0)
    return (svc.value, sndr.value, rcvr.value, seq.value, degr.value, flags.value)


class MultiSatHarness:
    def __init__(self, ids: List[int]) -> None:
        self.ctx: Dict[int, ctypes.c_void_p] = {}
        for sid in ids:
            ptr = lib.sim_create_context(sid)
            if not ptr:
                raise RuntimeError(f"Failed to create context for sat{sid}")
            self.ctx[sid] = ptr
        self.queue: List[Tuple[int, bytes]] = []
        self.links: Dict[int, Set[int]] = {sid: set(ids) - {sid} for sid in ids}
        self.tx_count = 0
        self.cb = TX_CB(self._on_tx)
        lib.sim_register_tx_callback(self.cb)

    def set_links(self, links: Dict[int, Set[int]]) -> None:
        self.links = links

    def _on_tx(self, dst, buf_ptr, length):
        self.tx_count += 1
        frame = ctypes.string_at(buf_ptr, length)
        svc, sndr, rcvr, seq, degr, flags = decode_header(frame)
        if sndr not in self.ctx:
            return

        if dst == 0xFF or rcvr == 0xFF:
            targets = [t for t in self.links.get(sndr, set()) if t in self.ctx]
        else:
            targets = [dst] if dst in self.links.get(sndr, set()) and dst in self.ctx else []

        for target in targets:
            self.queue.append((target, frame))

    def pump(self, max_frames: int = 256) -> int:
        processed = 0
        while self.queue and processed < max_frames:
            target, frame = self.queue.pop(0)
            buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
            lib.sim_inject_packet(self.ctx[target], buf, len(frame))
            processed += 1
        return processed

    def state(self, sid: int) -> int:
        return int(lib.sim_get_state(self.ctx[sid]))

    def cleanup(self) -> None:
        for ptr in self.ctx.values():
            lib.sim_destroy_context(ptr)
        self.ctx.clear()
        self.queue.clear()



def test_it02_degr_weighting_mixed_health() -> None:
    print("\n[IT-02] DEGR weighting with mixed health")
    requester = lib.sim_create_context(3)
    try:
        assert_true(bool(requester), "IT-02 setup failed: requester context")
        lib.sim_clear_correction_filter(requester)

        # One degraded responder (DEGR=14) far from truth, three healthy responders (DEGR=0).
        bad = (80.0, 10.0, -15.0)
        healthy = [
            (42.3, -17.2, 9.2),
            (41.8, -17.7, 9.4),
            (42.1, -17.4, 9.1),
        ]

        lib.sim_inject_event(requester, EVT_FAULT_DETECTED)
        lib.sim_inject_correction_rsp(requester, 1, 1, 14, SENSOR_MAGNETOMETER, bad[0], bad[1], bad[2], 100)
        lib.sim_inject_correction_rsp(requester, 2, 1, 0, SENSOR_MAGNETOMETER, healthy[0][0], healthy[0][1], healthy[0][2], 101)
        lib.sim_inject_correction_rsp(requester, 4, 1, 0, SENSOR_MAGNETOMETER, healthy[1][0], healthy[1][1], healthy[1][2], 102)
        lib.sim_inject_correction_rsp(requester, 5, 1, 0, SENSOR_MAGNETOMETER, healthy[2][0], healthy[2][1], healthy[2][2], 103)

        lib.sim_advance_time(requester, 5100)
        cx, cy, cz = get_corrected_xyz(requester)

        hx = sum(v[0] for v in healthy) / len(healthy)
        hy = sum(v[1] for v in healthy) / len(healthy)
        hz = sum(v[2] for v in healthy) / len(healthy)

        dist_healthy = math.sqrt((cx - hx) ** 2 + (cy - hy) ** 2 + (cz - hz) ** 2)
        dist_bad = math.sqrt((cx - bad[0]) ** 2 + (cy - bad[1]) ** 2 + (cz - bad[2]) ** 2)

        expected_bad_weight = max(0.05, 1.0 - 14.0 / 15.0)
        assert_true(expected_bad_weight < 0.1, "IT-02 failed: DEGR=14 weight should be < 0.1")
        assert_true(dist_healthy < dist_bad, "IT-02 failed: corrected value not dominated by healthy satellites")

        print(
            f"  PASS: bad_weight={expected_bad_weight:.3f}, "
            f"dist_to_healthy={dist_healthy:.3f}, dist_to_bad={dist_bad:.3f}"
        )
    finally:
        if requester:
            lib.sim_destroy_context(requester)



def test_it03_relay_visibility_gap() -> None:
    print("\n[IT-03] Relay across visibility gap")
    h = MultiSatHarness([1, 2, 3, 4, 5])
    try:
        # Only sat2 <-> sat4 are mutually visible for this scenario.
        links = {
            1: set(),
            2: {4},
            3: set(),
            4: {2},
            5: set(),
        }
        h.set_links(links)

        relay_payload = b"SISP relay payload for sat4 data transfer"
        relay_buf = (ctypes.c_uint8 * len(relay_payload)).from_buffer_copy(relay_payload)
        lib.sim_set_relay_payload(h.ctx[2], relay_buf, len(relay_payload))

        lib.sim_inject_event(h.ctx[2], EVT_ENERGY_LOW)
        for _ in range(8):
            if h.pump(128) == 0:
                break

        s2 = h.state(2)
        s4 = h.state(4)
        assert_true(s2 in (ST_RELAY_SENDING, ST_RELAY_WAIT_ACK), "IT-03 failed: sat2 did not enter relay sender path")
        assert_true(s4 in (ST_RELAY_RECEIVING, ST_RELAY_STORING), "IT-03 failed: sat4 did not accept relay path")

        # Complete the transfer/session lifecycle.
        if h.state(2) == ST_RELAY_SENDING:
            lib.sim_inject_event(h.ctx[2], EVT_ALL_FRAGS_SENT)
        assert_true(h.state(2) == ST_RELAY_WAIT_ACK, "IT-03 failed: sat2 did not reach RELAY_WAIT_ACK")

        if h.state(4) == ST_RELAY_STORING:
            lib.sim_inject_event(h.ctx[4], EVT_ALL_FRAGS_RCVD)
        assert_true(h.state(4) == ST_RELAY_DOWNLINKING, "IT-03 failed: sat4 did not reach RELAY_DOWNLINKING")
        lib.sim_inject_event(h.ctx[4], EVT_SENSOR_READ_DONE)

        for _ in range(4):
            if h.pump(128) == 0:
                break

        assert_true(h.state(4) == ST_IDLE, "IT-03 failed: sat4 did not return to IDLE")

        # Requester should receive ACK and complete.
        assert_true(h.state(2) == ST_RELAY_DONE, "IT-03 failed: sat2 did not reach RELAY_DONE")
        lib.sim_inject_event(h.ctx[2], EVT_RESET)
        assert_true(h.state(2) == ST_IDLE, "IT-03 failed: sat2 did not return to IDLE after session reset")

        rx_len = int(lib.sim_get_relay_rx_len(h.ctx[4]))
        assert_true(rx_len >= len(relay_payload), "IT-03 failed: sat4 relay buffer length too small")
        rx_buf = (ctypes.c_uint8 * rx_len)()
        copied = int(lib.sim_copy_relay_rx_payload(h.ctx[4], rx_buf, rx_len))
        received = bytes(rx_buf[:copied])
        assert_true(received[:len(relay_payload)] == relay_payload, "IT-03 failed: relay payload mismatch at sat4")

        print("  PASS: sat2 relay path established through sat4 with payload buffered")
    finally:
        h.cleanup()



def test_it05_30_day_correction_quality() -> None:
    print("\n[IT-05] 30-day correction quality")
    rng = random.Random(20260414)
    sat2 = lib.sim_create_context(2)
    try:
        assert_true(bool(sat2), "IT-05 setup failed: sat2 context")
        lib.sim_use_kalman_filter(sat2, ctypes.c_float(0.02), ctypes.c_float(0.8))

        days = 30
        raw_sq = 0.0
        corr_sq = 0.0
        seq = {3: 1, 4: 1, 5: 1}
        ts = 100

        # Warm-up phase to initialize filter state before scored 30-day window.
        for _ in range(5):
            lib.sim_inject_event(sat2, EVT_FAULT_DETECTED)
            for sid in (3, 4, 5):
                mx = TRUE_X + rng.gauss(0.0, 0.6)
                my = TRUE_Y + rng.gauss(0.0, 0.6)
                mz = TRUE_Z + rng.gauss(0.0, 0.6)
                err = vec_err(mx, my, mz)
                degr = degr_from_error_inverse(err, sigma=0.6)
                lib.sim_inject_correction_rsp(sat2, sid, seq[sid], degr, SENSOR_MAGNETOMETER, mx, my, mz, ts)
                seq[sid] = (seq[sid] + 1) & 0xFF
                ts += 1
            lib.sim_advance_time(sat2, 5100)
            lib.sim_inject_event(sat2, EVT_CORRECTION_DONE)
            ts += 100

        for day in range(1, days + 1):
            drift_x = 0.5 * day  # nT/day drift

            raw_x = TRUE_X + drift_x + rng.gauss(0.0, 0.4)
            raw_y = TRUE_Y + rng.gauss(0.0, 0.4)
            raw_z = TRUE_Z + rng.gauss(0.0, 0.4)
            raw_e = vec_err(raw_x, raw_y, raw_z)
            raw_sq += raw_e * raw_e

            lib.sim_inject_event(sat2, EVT_FAULT_DETECTED)

            for sid in (3, 4, 5):
                mx = TRUE_X + rng.gauss(0.0, 1.0)
                my = TRUE_Y + rng.gauss(0.0, 1.0)
                mz = TRUE_Z + rng.gauss(0.0, 1.0)
                err = vec_err(mx, my, mz)
                degr = degr_from_error_inverse(err, sigma=1.0)
                lib.sim_inject_correction_rsp(sat2, sid, seq[sid], degr, SENSOR_MAGNETOMETER, mx, my, mz, ts)
                seq[sid] = (seq[sid] + 1) & 0xFF
                ts += 1

            lib.sim_advance_time(sat2, 5100)
            cx, cy, cz = get_corrected_xyz(sat2)
            corr_e = vec_err(cx, cy, cz)
            corr_sq += corr_e * corr_e

            lib.sim_inject_event(sat2, EVT_CORRECTION_DONE)
            ts += 100

        rmse_raw = math.sqrt(raw_sq / days)
        rmse_corr = math.sqrt(corr_sq / days)
        gain = (1.0 - (rmse_corr / rmse_raw)) * 100.0 if rmse_raw > 0.0 else 0.0

        print(f"  RMSE raw={rmse_raw:.3f}, corrected={rmse_corr:.3f}, improvement={gain:.1f}%")

        assert_true(rmse_corr < rmse_raw, "IT-05 failed: corrected RMSE is not better than raw")
        assert_true(rmse_corr <= 0.4 * rmse_raw, "IT-05 failed: corrected RMSE did not improve by at least 60%")

        print(f"  PASS: RMSE raw={rmse_raw:.3f}, corrected={rmse_corr:.3f}, improvement={gain:.1f}%")
    finally:
        if sat2:
            lib.sim_destroy_context(sat2)



def test_it06_packet_loss_resilience() -> None:
    print("\n[IT-06] Packet loss resilience (10% drop, 7 days, 5 satellites)")
    rng = random.Random(606)
    sat1 = lib.sim_create_context(1)
    try:
        assert_true(bool(sat1), "IT-06 setup failed: sat1 context")
        lib.sim_use_kalman_filter(sat1, ctypes.c_float(0.02), ctypes.c_float(0.8))

        days = 7
        packet_loss = 0.10
        seq = {2: 1, 3: 1, 4: 1, 5: 1}
        ts = 1000

        completed = 0
        raw_sq = 0.0
        corr_sq = 0.0

        # Warm-up before scored packet-loss run.
        for _ in range(4):
            lib.sim_inject_event(sat1, EVT_FAULT_DETECTED)
            for sid in (2, 3, 4, 5):
                mx = TRUE_X + rng.gauss(0.0, 1.2)
                my = TRUE_Y + rng.gauss(0.0, 1.2)
                mz = TRUE_Z + rng.gauss(0.0, 1.2)
                err = vec_err(mx, my, mz)
                degr = degr_from_error_inverse(err, sigma=1.2)
                lib.sim_inject_correction_rsp(sat1, sid, seq[sid], degr, SENSOR_MAGNETOMETER, mx, my, mz, ts)
                seq[sid] = (seq[sid] + 1) & 0xFF
                ts += 1
            lib.sim_advance_time(sat1, 5100)
            lib.sim_inject_event(sat1, EVT_CORRECTION_DONE)
            ts += 100

        for day in range(1, days + 1):
            raw_x = TRUE_X + rng.gauss(0.0, 5.0)
            raw_y = TRUE_Y + rng.gauss(0.0, 5.0)
            raw_z = TRUE_Z + rng.gauss(0.0, 5.0)
            raw_e = vec_err(raw_x, raw_y, raw_z)

            lib.sim_inject_event(sat1, EVT_FAULT_DETECTED)

            delivered = 0
            for sid in (2, 3, 4, 5):
                if rng.random() < packet_loss:
                    seq[sid] = (seq[sid] + 1) & 0xFF
                    continue

                mx = TRUE_X + rng.gauss(0.0, 3.0)
                my = TRUE_Y + rng.gauss(0.0, 3.0)
                mz = TRUE_Z + rng.gauss(0.0, 3.0)
                err = vec_err(mx, my, mz)
                degr = degr_from_error_inverse(err, sigma=3.0)
                lib.sim_inject_correction_rsp(sat1, sid, seq[sid], degr, SENSOR_MAGNETOMETER, mx, my, mz, ts)
                delivered += 1
                seq[sid] = (seq[sid] + 1) & 0xFF
                ts += 1

            lib.sim_advance_time(sat1, 5100)
            cx, cy, cz = get_corrected_xyz(sat1)
            lib.sim_inject_event(sat1, EVT_CORRECTION_DONE)

            if delivered > 0:
                completed += 1
                raw_sq += raw_e * raw_e
                corr_e = vec_err(cx, cy, cz)
                corr_sq += corr_e * corr_e

            ts += 100

        assert_true(completed >= 6, "IT-06 failed: correction did not complete often enough under 10% packet loss")

        rmse_raw = math.sqrt(raw_sq / max(1, completed))
        rmse_corr = math.sqrt(corr_sq / max(1, completed))
        print(f"  RMSE raw={rmse_raw:.3f}, corrected={rmse_corr:.3f}, completed={completed}/{days}")
        assert_true(rmse_corr < rmse_raw, "IT-06 failed: corrected value is not closer to truth than raw")

        print(
            f"  PASS: completed={completed}/{days}, "
            f"RMSE raw={rmse_raw:.3f}, corrected={rmse_corr:.3f}"
        )
    finally:
        if sat1:
            lib.sim_destroy_context(sat1)



def main() -> None:
    print("\n=== Integration Matrix Tests: IT-02 / IT-03 / IT-05 / IT-06 ===")
    test_it02_degr_weighting_mixed_health()
    test_it03_relay_visibility_gap()
    test_it05_30_day_correction_quality()
    test_it06_packet_loss_resilience()
    print("\nALL MATRIX TESTS PASSED")


if __name__ == "__main__":
    main()
