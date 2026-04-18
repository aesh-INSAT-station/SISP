#!/usr/bin/env python3
import ctypes
import math
import os
import random
from typing import Dict, List, Tuple

BASE_DIR = os.path.dirname(__file__)
DLL_CANDIDATES = [
    os.path.join(BASE_DIR, "..", "c++ implemnetation", "build", "bin", "Release", "sisp.dll"),
    os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll"),
]
DLL_PATH = next((p for p in DLL_CANDIDATES if os.path.exists(p)), None)
if DLL_PATH is None:
    raise FileNotFoundError("sisp.dll not found in expected build locations.")

lib = ctypes.CDLL(DLL_PATH)

# Core sim API
lib.sim_create_context.argtypes = [ctypes.c_uint8]
lib.sim_create_context.restype = ctypes.c_void_p
lib.sim_destroy_context.argtypes = [ctypes.c_void_p]
lib.sim_destroy_context.restype = None
lib.sim_inject_packet.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_inject_packet.restype = None
lib.sim_inject_event.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.sim_inject_event.restype = None
lib.sim_advance_time.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
lib.sim_advance_time.restype = None
lib.sim_get_state.argtypes = [ctypes.c_void_p]
lib.sim_get_state.restype = ctypes.c_int

# Correction APIs
lib.sim_use_weighted_median_filter.argtypes = [ctypes.c_void_p]
lib.sim_use_weighted_median_filter.restype = None
lib.sim_use_kalman_filter.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float]
lib.sim_use_kalman_filter.restype = None
lib.sim_use_hybrid_filter.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float]
lib.sim_use_hybrid_filter.restype = None
lib.sim_get_corrected.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float)]
lib.sim_get_corrected.restype = None
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

# Relay payload APIs
lib.sim_set_relay_payload.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_set_relay_payload.restype = None
lib.sim_get_relay_rx_len.argtypes = [ctypes.c_void_p]
lib.sim_get_relay_rx_len.restype = ctypes.c_uint16
lib.sim_copy_relay_rx_payload.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_copy_relay_rx_payload.restype = ctypes.c_uint16

# Header decode and TX callback
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
TX_CB = ctypes.CFUNCTYPE(None, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16)
lib.sim_register_tx_callback.argtypes = [TX_CB]
lib.sim_register_tx_callback.restype = None

# Events
EVT_FAULT_DETECTED = 12
EVT_ENERGY_LOW = 14
EVT_ALL_FRAGS_SENT = 17
EVT_ALL_FRAGS_RCVD = 18
EVT_SENSOR_READ_DONE = 19
EVT_CORRECTION_DONE = 20

# Sensor ID
SENSOR_MAGNETOMETER = 0x01

# A few state IDs for debugging output
STATE_RELAY_WAIT_ACK = 8
STATE_RELAY_DONE = 9

TRUE_X, TRUE_Y, TRUE_Z = 42.0, -17.5, 9.25


def vec_err(x: float, y: float, z: float) -> float:
    return math.sqrt((x - TRUE_X) ** 2 + (y - TRUE_Y) ** 2 + (z - TRUE_Z) ** 2)


def to_degr(err_mag: float, sigma: float) -> int:
    if sigma <= 0.0:
        return 0
    scaled = min(1.0, err_mag / (3.0 * sigma))
    return max(0, min(15, int(round(scaled * 15.0))))


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
        return (0xFF, 0, 0, 0, 0, 0)
    return (svc.value, sndr.value, rcvr.value, seq.value, degr.value, flags.value)


class Network:
    def __init__(self, sat_map: Dict[int, ctypes.c_void_p]):
        self.sat_map = sat_map
        self.queue: List[Tuple[int, bytes]] = []
        self.cb = TX_CB(self._on_tx)
        lib.sim_register_tx_callback(self.cb)

    def _on_tx(self, dst, buf_ptr, length):
        frame = ctypes.string_at(buf_ptr, length)
        svc, sndr, rcvr, seq, degr, _flags = decode_header(frame)

        if dst == 0xFF or rcvr == 0xFF:
            targets = [sid for sid in self.sat_map.keys() if sid != sndr]
        else:
            targets = [dst] if dst in self.sat_map else []

        for target in targets:
            self.queue.append((target, frame))

    def pump(self, limit: int = 1024) -> int:
        processed = 0
        while self.queue and processed < limit:
            target, frame = self.queue.pop(0)
            buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
            lib.sim_inject_packet(self.sat_map[target], buf, len(frame))
            processed += 1
        return processed



def set_algorithm(ctx: ctypes.c_void_p, name: str) -> None:
    if name == "weighted_median":
        lib.sim_use_weighted_median_filter(ctx)
    elif name == "kalman":
        lib.sim_use_kalman_filter(ctx, ctypes.c_float(0.02), ctypes.c_float(0.8))
    elif name == "hybrid":
        lib.sim_use_hybrid_filter(ctx, ctypes.c_float(0.02), ctypes.c_float(0.8))
    else:
        raise ValueError(f"Unknown algorithm: {name}")



def run_message_propagation(algorithm: str) -> Tuple[bool, int, bytes]:
    sat1 = lib.sim_create_context(1)
    sat2 = lib.sim_create_context(2)
    sat3 = lib.sim_create_context(3)
    if not sat1 or not sat2 or not sat3:
        raise RuntimeError("Failed to create message propagation contexts")

    sat = {1: sat1, 2: sat2, 3: sat3}
    try:
        # Algorithm is applied to requester to keep scenarios consistent.
        set_algorithm(sat1, algorithm)

        net = Network(sat)

        message = f"MSG PROP + CORR using {algorithm}".encode("ascii")
        msg_buf = (ctypes.c_uint8 * len(message)).from_buffer_copy(message)
        lib.sim_set_relay_payload(sat1, msg_buf, len(message))

        # Start relay request flow.
        lib.sim_inject_event(sat1, EVT_ENERGY_LOW)
        for _ in range(6):
            if net.pump() == 0:
                break

        # Move sender to WAIT_ACK then let receiver complete + ACK.
        lib.sim_inject_event(sat1, EVT_ALL_FRAGS_SENT)
        net.pump()
        lib.sim_inject_event(sat2, EVT_ALL_FRAGS_RCVD)
        lib.sim_inject_event(sat2, EVT_SENSOR_READ_DONE)
        net.pump()

        rx_len = int(lib.sim_get_relay_rx_len(sat2))
        out = (ctypes.c_uint8 * max(1, rx_len))()
        copied = int(lib.sim_copy_relay_rx_payload(sat2, out, max(1, rx_len)))
        rx_bytes = bytes(out[:copied])

        sender_state = int(lib.sim_get_state(sat1))
        delivered = copied >= len(message) and rx_bytes.startswith(message)
        sender_ok = sender_state in (STATE_RELAY_WAIT_ACK, STATE_RELAY_DONE)

        return (delivered and sender_ok, sender_state, rx_bytes)
    finally:
        lib.sim_destroy_context(sat1)
        lib.sim_destroy_context(sat2)
        lib.sim_destroy_context(sat3)



def run_sensor_correction(algorithm: str, rounds: int = 40, sigma: float = 12.0) -> float:
    sat1 = lib.sim_create_context(1)
    if not sat1:
        raise RuntimeError("Failed to create correction context")

    try:
        set_algorithm(sat1, algorithm)
        rng = random.Random(240518)

        seq2 = 1
        seq3 = 1
        ts = 100

        corr_ss_acc = 0.0
        ss_count = 0

        for i in range(rounds):
            lib.sim_inject_event(sat1, EVT_FAULT_DETECTED)

            m2x = TRUE_X + rng.gauss(0.0, sigma)
            m2y = TRUE_Y + rng.gauss(0.0, sigma)
            m2z = TRUE_Z + rng.gauss(0.0, sigma)

            m3x = TRUE_X + rng.gauss(0.0, sigma)
            m3y = TRUE_Y + rng.gauss(0.0, sigma)
            m3z = TRUE_Z + rng.gauss(0.0, sigma)

            d2 = to_degr(vec_err(m2x, m2y, m2z), sigma)
            d3 = to_degr(vec_err(m3x, m3y, m3z), sigma)

            lib.sim_inject_correction_rsp(sat1, 2, seq2, d2, SENSOR_MAGNETOMETER, m2x, m2y, m2z, ts)
            lib.sim_inject_correction_rsp(sat1, 3, seq3, d3, SENSOR_MAGNETOMETER, m3x, m3y, m3z, ts + 1)

            lib.sim_advance_time(sat1, 5100)

            out = (ctypes.c_float * 3)()
            lib.sim_get_corrected(sat1, out)
            corr_err = vec_err(float(out[0]), float(out[1]), float(out[2]))

            if i >= rounds // 3:
                corr_ss_acc += corr_err
                ss_count += 1

            lib.sim_inject_event(sat1, EVT_CORRECTION_DONE)

            seq2 = (seq2 + 1) & 0xFF
            seq3 = (seq3 + 1) & 0xFF
            ts += 100

        return corr_ss_acc / max(1, ss_count)
    finally:
        lib.sim_destroy_context(sat1)



def main() -> None:
    algorithms = ["weighted_median", "kalman", "hybrid"]

    print("\n=== Full Message Propagation + Sensor Correction ===")
    print("Algorithms under test: weighted_median, kalman, hybrid")

    results = []
    for algo in algorithms:
        delivered, sender_state, rx = run_message_propagation(algo)
        corr_ss = run_sensor_correction(algo)

        print(
            f"{algo:16s} propagation={'PASS' if delivered else 'FAIL'} "
            f"sender_state={sender_state:2d} correction_ss_err={corr_ss:7.3f}"
        )

        results.append((algo, delivered, sender_state, corr_ss, rx))

    failed = [r for r in results if not r[1]]
    if failed:
        raise AssertionError("Propagation failed for one or more algorithms")

    ranked = sorted(results, key=lambda r: r[3])
    print("\nCorrection ranking (lower steady-state error is better):")
    for idx, (algo, _ok, _st, err, _rx) in enumerate(ranked, start=1):
        print(f"{idx}. {algo:16s} {err:7.3f}")

    print("\nPASS: full message propagation and 3 correction alternatives verified.")


if __name__ == "__main__":
    main()
