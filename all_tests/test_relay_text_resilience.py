#!/usr/bin/env python3
import ctypes
import os
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

# Core API bindings
lib.sim_create_context.argtypes = [ctypes.c_uint8]
lib.sim_create_context.restype = ctypes.c_void_p
lib.sim_destroy_context.argtypes = [ctypes.c_void_p]
lib.sim_destroy_context.restype = None
lib.sim_inject_event.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.sim_inject_event.restype = None
lib.sim_inject_packet.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_inject_packet.restype = None
lib.sim_get_state.argtypes = [ctypes.c_void_p]
lib.sim_get_state.restype = ctypes.c_int

lib.sim_register_tx_callback.argtypes = [ctypes.CFUNCTYPE(None, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16)]
lib.sim_register_tx_callback.restype = None

lib.sim_set_relay_payload.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_set_relay_payload.restype = None
lib.sim_get_relay_rx_len.argtypes = [ctypes.c_void_p]
lib.sim_get_relay_rx_len.restype = ctypes.c_uint16
lib.sim_copy_relay_rx_payload.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_copy_relay_rx_payload.restype = ctypes.c_uint16

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

# Events
EVT_ENERGY_LOW = 14
EVT_ALL_FRAGS_SENT = 17
EVT_ALL_FRAGS_RCVD = 18
EVT_SENSOR_READ_DONE = 19

# Relay states
ST_IDLE = 0
ST_RELAY_SENDING = 7
ST_RELAY_WAIT_ACK = 8
ST_RELAY_DONE = 9
ST_RELAY_RECEIVING = 10
ST_RELAY_STORING = 11
ST_RELAY_DOWNLINKING = 12

STATE_NAME = {
    0: "IDLE",
    7: "RELAY_SENDING",
    8: "RELAY_WAIT_ACK",
    9: "RELAY_DONE",
    10: "RELAY_RECEIVING",
    11: "RELAY_STORING",
    12: "RELAY_DOWNLINKING",
}

SERVICE_NAME = {
    0x0: "CORRECTION_REQ",
    0x1: "CORRECTION_RSP",
    0x2: "RELAY_REQ",
    0x3: "RELAY_ACCEPT",
    0x4: "RELAY_REJECT",
    0x5: "DOWNLINK_DATA",
    0x6: "DOWNLINK_ACK",
    0x7: "STATUS_BROADCAST",
    0x8: "HEARTBEAT",
    0x9: "HEARTBEAT_ACK",
    0xA: "BORROW_DECISION",
    0xE: "BORROW_REQ",
    0xF: "FAILURE",
}

DOWNLINK_DATA_SVC = 0x5
FRAME_SIZE = 64
DOWNLINK_ENVELOPE_BYTES = 6
FRAGMENT_STRIDE = 101  # Mirrors protocol MAX_FRAGMENT_DATA storage stride.

sat_contexts: Dict[int, ctypes.c_void_p] = {}
normal_queue: List[Tuple[int, bytes]] = []
downlink_capture: List[Tuple[int, bytes, Tuple[int, int, int, int, int, int]]] = []

SENDER_ID = 1
RECEIVER_ID = 2


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


def service_name(svc: int) -> str:
    return SERVICE_NAME.get(svc, f"SVC_{svc:X}")


def state_name(state: int) -> str:
    return STATE_NAME.get(state, f"STATE_{state}")


def inject_frame(target_id: int, frame: bytes) -> None:
    buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
    lib.sim_inject_packet(sat_contexts[target_id], buf, len(frame))


def assert_true(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def crc8_maxim(data: bytes) -> int:
    # Reflected CRC-8/MAXIM polynomial (0x31 reflected -> 0x8C), init 0x00.
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x01:
                crc = (crc >> 1) ^ 0x8C
            else:
                crc >>= 1
            crc &= 0xFF
    return crc


def frame_payload_capacity(frame: bytes) -> int:
    # Frame layout: 5-byte header + 3-byte frame metadata + extension + payload + frame checksum.
    ext_len = int(frame[6])
    return FRAME_SIZE - (5 + 3 + 1) - ext_len


def set_seq_and_header_cksm(frame: bytearray, seq: int) -> None:
    # Header packing follows sisp_encoder.cpp nibble layout.
    frame[2] = (frame[2] & 0xF0) | ((seq >> 4) & 0x0F)
    frame[3] = ((seq & 0x0F) << 4) | (frame[3] & 0x0F)

    # Header checksum nibble is low nibble of byte 4.
    frame[4] &= 0xF0
    hdr_crc = crc8_maxim(bytes(frame[0:4]))
    frame[4] |= ((hdr_crc >> 4) & 0x0F)


def build_downlink_frame(template: bytes, seq: int, frag_idx: int, frag_total: int, frag_data: bytes) -> bytes:
    cap = frame_payload_capacity(template)
    max_data = cap - DOWNLINK_ENVELOPE_BYTES
    assert_true(max_data > 0, "Invalid frame template payload capacity")
    assert_true(len(frag_data) <= max_data, "Fragment exceeds frame payload capacity")

    frame = bytearray(template)
    set_seq_and_header_cksm(frame, seq)

    payload_offset = 8 + int(frame[6])
    payload_len = DOWNLINK_ENVELOPE_BYTES + len(frag_data)
    frame[5] = payload_len

    # Clear payload area for deterministic encoding before writing new fragment.
    frame[payload_offset:payload_offset + cap] = b"\x00" * cap

    # DownlinkData payload: [frag_idx:u16][frag_total:u16][data_len:u16][data...]
    frame[payload_offset + 0] = (frag_idx >> 8) & 0xFF
    frame[payload_offset + 1] = frag_idx & 0xFF
    frame[payload_offset + 2] = (frag_total >> 8) & 0xFF
    frame[payload_offset + 3] = frag_total & 0xFF
    frame[payload_offset + 4] = (len(frag_data) >> 8) & 0xFF
    frame[payload_offset + 5] = len(frag_data) & 0xFF
    frame[payload_offset + 6:payload_offset + 6 + len(frag_data)] = frag_data

    # Recompute full frame checksum over bytes [0..62].
    frame[-1] = crc8_maxim(bytes(frame[:-1]))
    return bytes(frame)


def relink_text_from_storage(raw_storage: bytes, fragments: List[bytes]) -> bytes:
    out = bytearray()
    for idx, frag in enumerate(fragments):
        start = idx * FRAGMENT_STRIDE
        out.extend(raw_storage[start:start + len(frag)])
    return bytes(out)


def build_unique_payload(target_len: int) -> bytes:
    # Build deterministic non-repetitive text so recovered output is easy to inspect by eye.
    parts: List[bytes] = []
    i = 1
    while len(b"".join(parts)) < target_len:
        parts.append(f"seg{i:02d}:telemetry+relay+correction|".encode("ascii"))
        i += 1
    return b"".join(parts)[:target_len]


def on_tx(dst, buf_ptr, length):
    frame = ctypes.string_at(buf_ptr, length)
    svc, sndr, rcvr, seq, degr, flags = decode_header(frame)

    if dst == 0xFF or rcvr == 0xFF:
        targets = [sid for sid in sat_contexts.keys() if sid != sndr]
    else:
        targets = [dst] if dst in sat_contexts else []

    print(
        f"[TX] svc={service_name(svc):15s} sndr={sndr:02X} rcvr={rcvr:02X} "
        f"seq={seq:3d} degr={degr:2d} dst={dst:02X} targets={targets}"
    )

    for target in targets:
        if svc == DOWNLINK_DATA_SVC and sndr == SENDER_ID and target == RECEIVER_ID:
            # Capture and hold for controlled sequencing/checksum manipulation.
            downlink_capture.append((target, frame, (svc, sndr, rcvr, seq, degr, flags)))
        else:
            normal_queue.append((target, frame))


def pump_normal_queue(max_frames: int = 512) -> int:
    processed = 0
    while normal_queue and processed < max_frames:
        target, frame = normal_queue.pop(0)
        inject_frame(target, frame)
        processed += 1
    return processed


def print_states(label: str) -> None:
    print(f"\n[{label}]")
    for sid in (SENDER_ID, RECEIVER_ID):
        st = int(lib.sim_get_state(sat_contexts[sid]))
        print(f"  sat{sid}: {state_name(st)} ({st})")


def main() -> None:
    print("\n=== Relay Text Resilience Scenario (Multi-Fragment) ===")
    print("Goal: relink text through checksum errors, out-of-order fragments, and duplicate replay\n")

    sat_contexts[SENDER_ID] = lib.sim_create_context(SENDER_ID)
    sat_contexts[RECEIVER_ID] = lib.sim_create_context(RECEIVER_ID)
    assert_true(bool(sat_contexts[SENDER_ID]), "Failed to create sender context")
    assert_true(bool(sat_contexts[RECEIVER_ID]), "Failed to create receiver context")

    normal_queue.clear()
    downlink_capture.clear()

    cb = TX_CB(on_tx)
    lib.sim_register_tx_callback(cb)

    # Seed payload only forces one valid sender-generated DOWNLINK_DATA frame.
    # We reuse that frame as a transport template for multi-fragment injection.
    template_seed_payload = b"template seed frame for relay capture"
    relay_buf = (ctypes.c_uint8 * len(template_seed_payload)).from_buffer_copy(template_seed_payload)
    lib.sim_set_relay_payload(sat_contexts[SENDER_ID], relay_buf, len(template_seed_payload))

    # Handshake path: sender asks for relay, receiver accepts.
    lib.sim_inject_event(sat_contexts[SENDER_ID], EVT_ENERGY_LOW)
    for _ in range(8):
        if pump_normal_queue() == 0:
            break

    print_states("After relay handshake")
    snd_state = int(lib.sim_get_state(sat_contexts[SENDER_ID]))
    rcv_state = int(lib.sim_get_state(sat_contexts[RECEIVER_ID]))
    assert_true(snd_state == ST_RELAY_SENDING, "Sender did not reach RELAY_SENDING")
    assert_true(rcv_state in (ST_RELAY_RECEIVING, ST_RELAY_STORING), "Receiver not in relay receive path")

    print(f"\nCaptured DOWNLINK_DATA frames: {len(downlink_capture)}")
    assert_true(len(downlink_capture) >= 1, "No DOWNLINK_DATA frame captured")

    target, template_frame, hdr = downlink_capture[0]
    _, _, _, base_seq, _, _ = hdr

    cap = frame_payload_capacity(template_frame)
    max_data_per_fragment = cap - DOWNLINK_ENVELOPE_BYTES
    assert_true(max_data_per_fragment > 0, "Template frame does not allow DOWNLINK_DATA payload")

    # Build a payload guaranteed to require exactly 3 fragments with current frame capacity.
    tail_len = max(1, min(23, max_data_per_fragment - 1))
    target_len = (2 * max_data_per_fragment) + tail_len
    text_payload = build_unique_payload(target_len)

    fragments = [
        text_payload[i:i + max_data_per_fragment]
        for i in range(0, len(text_payload), max_data_per_fragment)
    ]
    assert_true(len(fragments) == 3, "Expected exactly three fragments in this scenario")

    print(f"Frame payload capacity={cap} bytes, max fragment data={max_data_per_fragment} bytes")
    print(f"Target text length: {len(text_payload)} bytes over {len(fragments)} fragments")

    seqs = [((base_seq + i) & 0xFF) for i in range(len(fragments))]
    built_frames = [
        build_downlink_frame(template_frame, seqs[i], i, len(fragments), fragments[i])
        for i in range(len(fragments))
    ]

    # Corrupt one frame checksum to force decoder drop, then continue with valid frames.
    corrupted_mid = bytearray(built_frames[1])
    corrupted_mid[-1] ^= 0x5A

    print("\nInjecting manipulated delivery plan:")
    print(f"  Step 1: Corrupted mid fragment idx=1 seq={seqs[1]} (checksum drop expected)")
    inject_frame(target, bytes(corrupted_mid))

    print(f"  Step 2: Valid tail fragment idx=2 seq={seqs[2]} (out-of-order)")
    inject_frame(target, built_frames[2])

    print(f"  Step 3: Valid head fragment idx=0 seq={seqs[0]}")
    inject_frame(target, built_frames[0])

    print(f"  Step 4: Valid continuation mid fragment idx=1 seq={seqs[1]}")
    inject_frame(target, built_frames[1])

    print(f"  Step 5: Duplicate replay mid fragment idx=1 seq={seqs[1]} (should be dropped)")
    inject_frame(target, built_frames[1])

    # Complete relay lifecycle.
    lib.sim_inject_event(sat_contexts[SENDER_ID], EVT_ALL_FRAGS_SENT)
    assert_true(int(lib.sim_get_state(sat_contexts[SENDER_ID])) == ST_RELAY_WAIT_ACK, "Sender did not reach RELAY_WAIT_ACK")

    lib.sim_inject_event(sat_contexts[RECEIVER_ID], EVT_ALL_FRAGS_RCVD)
    assert_true(int(lib.sim_get_state(sat_contexts[RECEIVER_ID])) == ST_RELAY_DOWNLINKING, "Receiver did not reach RELAY_DOWNLINKING")

    lib.sim_inject_event(sat_contexts[RECEIVER_ID], EVT_SENSOR_READ_DONE)

    # Process ACK to sender.
    for _ in range(6):
        if pump_normal_queue() == 0:
            break

    print_states("After completion events")
    assert_true(int(lib.sim_get_state(sat_contexts[SENDER_ID])) == ST_RELAY_DONE, "Sender did not reach RELAY_DONE")
    assert_true(int(lib.sim_get_state(sat_contexts[RECEIVER_ID])) == ST_IDLE, "Receiver did not return to IDLE")

    rx_len = int(lib.sim_get_relay_rx_len(sat_contexts[RECEIVER_ID]))
    rx_buf = (ctypes.c_uint8 * max(1, rx_len))()
    copied = int(lib.sim_copy_relay_rx_payload(sat_contexts[RECEIVER_ID], rx_buf, max(1, rx_len)))
    recovered_raw = bytes(rx_buf[:copied])
    relinked = relink_text_from_storage(recovered_raw, fragments)

    print(f"\nRecovered raw storage length: {copied} bytes")
    print(f"Relinked text length: {len(relinked)} bytes")
    print(f"Relinked text: {relinked.decode('ascii')}")

    assert_true(copied >= len(text_payload), "Recovered payload shorter than expected")
    assert_true(relinked == text_payload, "Relinked text payload mismatch")

    print("\nPASS: Multi-fragment text relinked after checksum drop, out-of-order delivery, and duplicate replay")


if __name__ == "__main__":
    try:
        main()
    finally:
        for ctx in sat_contexts.values():
            if ctx:
                lib.sim_destroy_context(ctx)
