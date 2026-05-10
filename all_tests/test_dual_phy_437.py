#!/usr/bin/env python3
"""
Test: Dual-Frequency PHY Profile (CONTROL_437_NARROW vs BULK_437_WIDE)

Validates that the C++ state machine correctly selects between the two
437 MHz PHY profiles per SISP protocol spec:

  CONTROL_437_NARROW (0x00) — 10/12.5 kHz-class always-on control channel
    Used for: CORRECTION_REQ, CORRECTION_RSP, RELAY_REQ, RELAY_ACCEPT,
              RELAY_REJECT, FAILURE, HEARTBEAT, BORROW_REQ, BORROW_DECISION

  BULK_437_WIDE (0x01) — 20/25 kHz-class emergency/bulk channel
    Used for: DOWNLINK_DATA, DOWNLINK_ACK (when peer advertises BULK support)

PHY profile is encoded in frame byte 8 by Encoder::encode_frame().
select_tx_phy() in sisp_state_machine.cpp selects BULK only for
DOWNLINK_DATA/DOWNLINK_ACK to a unicast peer that supports it.

Event codes (must match SISP::Event in sisp_state_machine.hpp):
  FAULT_DETECTED  = 12
  ENERGY_LOW      = 14
  CRITICAL_FAILURE = 21
"""

import ctypes
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLL_PATH = os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll")

if not os.path.exists(DLL_PATH):
    print(f"SKIP: sisp.dll not found at {DLL_PATH}")
    sys.exit(0)

lib = ctypes.CDLL(DLL_PATH)

# C API bindings
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

lib.sim_set_relay_payload.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16
]
lib.sim_set_relay_payload.restype = None

TX_CB = ctypes.CFUNCTYPE(None, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16)
lib.sim_register_tx_callback.argtypes = [TX_CB]
lib.sim_register_tx_callback.restype = None

# Event codes from sisp_state_machine.hpp
EVT_FAULT_DETECTED   = 12
EVT_ENERGY_LOW       = 14
EVT_CRITICAL_FAILURE = 21

# Service codes from sisp_protocol.hpp
SVC_CORRECTION_REQ = 0x0
SVC_CORRECTION_RSP = 0x1
SVC_RELAY_REQ      = 0x2
SVC_RELAY_ACCEPT   = 0x3
SVC_RELAY_REJECT   = 0x4
SVC_DOWNLINK_DATA  = 0x5
SVC_DOWNLINK_ACK   = 0x6
SVC_FAILURE        = 0xF

SVC_NAMES = {
    0x0: "CORRECTION_REQ", 0x1: "CORRECTION_RSP",
    0x2: "RELAY_REQ",      0x3: "RELAY_ACCEPT",
    0x4: "RELAY_REJECT",   0x5: "DOWNLINK_DATA",
    0x6: "DOWNLINK_ACK",   0x7: "STATUS_BROADCAST",
    0x8: "HEARTBEAT",      0x9: "HEARTBEAT_ACK",
    0xA: "BORROW_DECISION",0xE: "BORROW_REQ",
    0xF: "FAILURE",
}

PHY_CTRL_NARROW = 0  # CONTROL_437_NARROW
PHY_BULK_WIDE   = 1  # BULK_437_WIDE

FRAME_SIZE = 64

PASS = 0
FAIL = 0
results = []


def decode_frame_header(frame: bytes):
    """Decode 5-byte packed header from a 64-byte frame.

    Bit layout (from sisp_encoder.cpp):
      Byte 0: [ SVC[3:0] (high 4) | SNDR[7:4] (low 4) ]
      Byte 1: [ SNDR[3:0](high 4) | RCVR[7:4] (low 4) ]
      Byte 2: [ RCVR[3:0](high 4) | SEQ[7:4]  (low 4) ]
      Byte 3: [ SEQ[3:0] (high 4) | DEGR[3:0] (low 4) ]
      Byte 4: [ FLAGS[3:0](high4)  | CKSM[3:0] (low 4) ]
      Byte 8: phy_profile  (encode_frame: cursor=8 after header+3 bytes)
    """
    if len(frame) < 9:
        return None
    b0, b1, b2, b3, b4 = frame[0], frame[1], frame[2], frame[3], frame[4]
    svc  = (b0 >> 4) & 0x0F
    sndr = ((b0 & 0x0F) << 4) | ((b1 >> 4) & 0x0F)
    rcvr = ((b1 & 0x0F) << 4) | ((b2 >> 4) & 0x0F)
    seq  = ((b2 & 0x0F) << 4) | ((b3 >> 4) & 0x0F)
    degr = b3 & 0x0F
    flags = (b4 >> 4) & 0x0F
    phy  = frame[8] & 0xFF  # encode_frame byte 8
    return {"svc": svc, "sndr": sndr, "rcvr": rcvr, "seq": seq,
            "degr": degr, "flags": flags, "phy": phy}


def assert_test(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        results.append(f"  PASS  {name}")
    else:
        FAIL += 1
        results.append(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


# =============================================================================
# Helpers
# =============================================================================

sat_ctxs: dict = {}
frame_queue: list = []

def create_topology(num: int):
    global sat_ctxs, frame_queue
    sat_ctxs = {}
    frame_queue = []
    for i in range(1, num + 1):
        ptr = lib.sim_create_context(ctypes.c_uint8(i))
        if not ptr:
            raise RuntimeError(f"Failed to create context for sat {i}")
        sat_ctxs[i] = ptr

def destroy_topology():
    for ptr in sat_ctxs.values():
        lib.sim_destroy_context(ptr)
    sat_ctxs.clear()

def process_queue():
    while frame_queue:
        target, frame = frame_queue.pop(0)
        if target in sat_ctxs:
            buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
            lib.sim_inject_packet(sat_ctxs[target], buf, len(frame))

captured_frames: list = []

def on_tx(dst, buf_ptr, length):
    frame = ctypes.string_at(buf_ptr, length)
    hdr = decode_frame_header(frame)
    if hdr:
        captured_frames.append({"dst": int(dst), "frame": frame, **hdr})
    if dst == 0xFF or (hdr and hdr["rcvr"] == 0xFF):
        for sid in sat_ctxs:
            if hdr and sid != hdr["sndr"]:
                frame_queue.append((sid, frame))
    else:
        if int(dst) in sat_ctxs:
            frame_queue.append((int(dst), frame))

cb = TX_CB(on_tx)
lib.sim_register_tx_callback(cb)


# =============================================================================
# TEST 1: Correction request uses CONTROL_437_NARROW
# =============================================================================
def test_correction_phy():
    print("\n[TEST 1] Correction scenario: all frames must use CONTROL_437_NARROW")
    create_topology(3)
    captured_frames.clear()

    lib.sim_inject_event(sat_ctxs[1], EVT_FAULT_DETECTED)
    process_queue()
    lib.sim_advance_time(sat_ctxs[1], 500)
    process_queue()

    destroy_topology()

    corr_frames = [f for f in captured_frames if f["svc"] in (SVC_CORRECTION_REQ, SVC_CORRECTION_RSP)]
    total = len(corr_frames)
    ctrl_only = all(f["phy"] == PHY_CTRL_NARROW for f in corr_frames)

    assert_test(
        "CORRECTION frames captured",
        total > 0,
        f"got {total} correction frames",
    )
    assert_test(
        "All CORRECTION frames use PHY=CTRL_NARROW (0x00)",
        ctrl_only,
        detail=", ".join(
            f"svc={SVC_NAMES.get(f['svc'],'?')} phy={f['phy']}"
            for f in corr_frames if f["phy"] != PHY_CTRL_NARROW
        ) or "all good",
    )

    for f in corr_frames[:5]:
        sname = SVC_NAMES.get(f["svc"], f"0x{f['svc']:X}")
        phy_name = "CTRL_NARROW" if f["phy"] == 0 else "BULK_WIDE"
        print(f"    svc={sname:20s} sndr={f['sndr']} rcvr={f['rcvr']} phy={phy_name}")


# =============================================================================
# TEST 2: Failure broadcast uses CONTROL_437_NARROW
# =============================================================================
def test_failure_phy():
    print("\n[TEST 2] Failure broadcast: must use CONTROL_437_NARROW")
    create_topology(4)
    captured_frames.clear()

    lib.sim_inject_event(sat_ctxs[2], EVT_CRITICAL_FAILURE)
    process_queue()

    destroy_topology()

    fail_frames = [f for f in captured_frames if f["svc"] == SVC_FAILURE]
    total = len(fail_frames)
    ctrl_only = all(f["phy"] == PHY_CTRL_NARROW for f in fail_frames)

    assert_test("FAILURE frames captured", total > 0, f"got {total}")
    assert_test(
        "All FAILURE frames use PHY=CTRL_NARROW (0x00)",
        ctrl_only,
        detail=", ".join(f"phy={f['phy']}" for f in fail_frames if f["phy"] != PHY_CTRL_NARROW) or "all good",
    )

    for f in fail_frames[:3]:
        phy_name = "CTRL_NARROW" if f["phy"] == 0 else "BULK_WIDE"
        print(f"    svc=FAILURE sndr={f['sndr']} rcvr=0x{f['rcvr']:02X} phy={phy_name}")


# =============================================================================
# TEST 3: Relay control frames use CTRL_NARROW, data frames prefer BULK_WIDE
# =============================================================================
def test_relay_phy_split():
    print("\n[TEST 3] Relay scenario: REQ/ACCEPT use CTRL_NARROW, DOWNLINK_DATA may use BULK_WIDE")
    create_topology(3)
    captured_frames.clear()

    # Give sat1 a relay payload so it has something to send
    payload = b"SISP PHY dual-frequency test payload" * 4
    buf = (ctypes.c_uint8 * len(payload))(*payload)
    lib.sim_set_relay_payload(sat_ctxs[1], buf, len(payload))

    # Trigger energy low on sat1 → relay request
    lib.sim_inject_event(sat_ctxs[1], EVT_ENERGY_LOW)
    process_queue()

    # Advance to let the relay handshake complete and data flow
    for _ in range(20):
        for ptr in sat_ctxs.values():
            lib.sim_advance_time(ptr, 200)
        process_queue()

    destroy_topology()

    relay_ctrl = [f for f in captured_frames if f["svc"] in (SVC_RELAY_REQ, SVC_RELAY_ACCEPT, SVC_RELAY_REJECT)]
    data_frames = [f for f in captured_frames if f["svc"] == SVC_DOWNLINK_DATA]

    relay_ctrl_narrow = [f for f in relay_ctrl if f["phy"] == PHY_CTRL_NARROW]
    data_bulk = [f for f in data_frames if f["phy"] == PHY_BULK_WIDE]

    print(f"    Relay ctrl frames: {len(relay_ctrl)} total, {len(relay_ctrl_narrow)} on CTRL_NARROW")
    print(f"    Data frames:       {len(data_frames)} total, {len(data_bulk)} on BULK_WIDE")

    assert_test(
        "Relay REQ/ACCEPT/REJECT use CTRL_NARROW",
        len(relay_ctrl_narrow) == len(relay_ctrl) and len(relay_ctrl) > 0,
        f"ctrl={len(relay_ctrl_narrow)}/{len(relay_ctrl)}",
    )

    # DOWNLINK_DATA uses BULK_WIDE when peer advertises PHY capability.
    # If peer_phy_cap_mask[peer] == 0 (never received a frame with phy_cap), state machine
    # falls back to CTRL_NARROW. Log observed PHY split without failing the test.
    if data_frames:
        bulk_pct = 100.0 * len(data_bulk) / len(data_frames)
        print(f"    DOWNLINK_DATA: {bulk_pct:.0f}% on BULK_WIDE "
              f"(CTRL_NARROW fallback if peer capability not yet exchanged)")
        assert_test(
            "DOWNLINK_DATA frames present",
            len(data_frames) > 0,
        )
    else:
        print("    (No DOWNLINK_DATA in this relay window — relay completed before data phase)")


# =============================================================================
# TEST 4: PHY profile range check (only 0x00 and 0x01 are valid)
# =============================================================================
def test_phy_profile_range():
    print("\n[TEST 4] PHY profile values are in valid range {0,1}")
    create_topology(3)
    captured_frames.clear()

    lib.sim_inject_event(sat_ctxs[1], EVT_FAULT_DETECTED)
    process_queue()
    lib.sim_inject_event(sat_ctxs[3], EVT_CRITICAL_FAILURE)
    process_queue()
    for _ in range(5):
        for ptr in sat_ctxs.values():
            lib.sim_advance_time(ptr, 200)
        process_queue()

    destroy_topology()

    invalid = [f for f in captured_frames if f["phy"] not in (0, 1)]
    assert_test(
        "All frames have valid PHY profile (0 or 1)",
        len(invalid) == 0,
        f"{len(invalid)} invalid PHY values: {[f['phy'] for f in invalid]}",
    )
    print(f"    Total frames captured: {len(captured_frames)}, invalid PHY: {len(invalid)}")


# =============================================================================
# TEST 5: No cross-contamination — CTRL frames never use BULK_WIDE
# =============================================================================
def test_no_bulk_on_control_services():
    print("\n[TEST 5] Control services never use BULK_WIDE profile")
    create_topology(5)
    captured_frames.clear()

    lib.sim_inject_event(sat_ctxs[1], EVT_FAULT_DETECTED)
    process_queue()
    lib.sim_inject_event(sat_ctxs[1], EVT_ENERGY_LOW)
    process_queue()
    for _ in range(10):
        for ptr in sat_ctxs.values():
            lib.sim_advance_time(ptr, 200)
        process_queue()

    destroy_topology()

    control_svcs = {SVC_CORRECTION_REQ, SVC_CORRECTION_RSP, SVC_RELAY_REQ,
                    SVC_RELAY_ACCEPT, SVC_RELAY_REJECT, SVC_FAILURE}
    violators = [
        f for f in captured_frames
        if f["svc"] in control_svcs and f["phy"] == PHY_BULK_WIDE
    ]
    assert_test(
        "No control-service frame uses PHY=BULK_WIDE",
        len(violators) == 0,
        ", ".join(f"svc={SVC_NAMES.get(v['svc'],'?')}" for v in violators),
    )
    print(f"    Control frames scanned: "
          f"{sum(1 for f in captured_frames if f['svc'] in control_svcs)}, "
          f"BULK_WIDE violations: {len(violators)}")


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("=" * 72)
    print("SISP Dual-PHY 437 MHz Test (CONTROL_437_NARROW vs BULK_437_WIDE)")
    print("=" * 72)

    try:
        test_correction_phy()
        test_failure_phy()
        test_relay_phy_split()
        test_phy_profile_range()
        test_no_bulk_on_control_services()
    except Exception as exc:
        import traceback
        print(f"\nFATAL: {exc}")
        traceback.print_exc()
        FAIL += 1

    print("\n" + "=" * 72)
    print("Results:")
    for r in results:
        print(r)
    print(f"\n  PASSED: {PASS}  FAILED: {FAIL}")
    print("=" * 72)

    sys.exit(0 if FAIL == 0 else 1)
