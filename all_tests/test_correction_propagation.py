#!/usr/bin/env python3
import ctypes
import os

BASE_DIR = os.path.dirname(__file__)
DLL_CANDIDATES = [
    os.path.join(BASE_DIR, "..", "c++ implemnetation", "build", "bin", "Release", "sisp.dll"),
    os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll"),
]
DLL_PATH = next((p for p in DLL_CANDIDATES if os.path.exists(p)), None)

if DLL_PATH is None:
    raise FileNotFoundError("sisp.dll not found in expected build locations.")

lib = ctypes.CDLL(DLL_PATH)

# API bindings
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
lib.sim_get_degr.argtypes = [ctypes.c_void_p]
lib.sim_get_degr.restype = ctypes.c_uint8
lib.sim_get_corrected.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float)]
lib.sim_get_corrected.restype = None
lib.sim_get_neighbour_degr.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8)]
lib.sim_get_neighbour_degr.restype = None
lib.sim_decode_header.argtypes = [
    ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16,
    ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8),
    ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8)
]
lib.sim_decode_header.restype = ctypes.c_uint8

TX_CB = ctypes.CFUNCTYPE(None, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16)
lib.sim_register_tx_callback.argtypes = [TX_CB]
lib.sim_register_tx_callback.restype = None

EVT_FAULT_DETECTED = 12

SERVICE = {
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

STATE = {
    0: "IDLE",
    1: "CORR_WAIT_RSP",
    2: "CORR_COLLECTING",
    3: "CORR_COMPUTING",
    4: "CORR_DONE",
    5: "CORR_RESPONDING",
    20: "CRITICAL_FAIL",
}

sat = {}
q = []


def decode(frame: bytes):
    buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
    svc = ctypes.c_uint8(0)
    sndr = ctypes.c_uint8(0)
    rcvr = ctypes.c_uint8(0)
    seq = ctypes.c_uint8(0)
    degr = ctypes.c_uint8(0)
    flags = ctypes.c_uint8(0)
    ok = lib.sim_decode_header(buf, len(frame), ctypes.byref(svc), ctypes.byref(sndr), ctypes.byref(rcvr), ctypes.byref(seq), ctypes.byref(degr), ctypes.byref(flags))
    if ok == 0:
        return (0xFF, 0, 0, 0, 0, 0)
    return (svc.value, sndr.value, rcvr.value, seq.value, degr.value, flags.value)


def on_tx(dst, buf_ptr, length):
    frame = ctypes.string_at(buf_ptr, length)
    svc, sndr, rcvr, seq, degr, flags = decode(frame)
    print(f"[TX] {SERVICE.get(svc, f'SVC_{svc:X}'):15s} sndr={sndr:02X} rcvr={rcvr:02X} seq={seq:3d} degr={degr:2d} dst={dst:02X}")

    # Route broadcast/unicast in simulator network
    if dst == 0xFF or rcvr == 0xFF:
        targets = [sid for sid in sat.keys() if sid != sndr]
    else:
        targets = [dst] if dst in sat else []

    for t in targets:
        q.append((t, frame))


def pump(max_frames=256):
    n = 0
    while q and n < max_frames:
        target, frame = q.pop(0)
        buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
        lib.sim_inject_packet(sat[target], buf, len(frame))
        n += 1
    return n


def dump(sid):
    st = lib.sim_get_state(sat[sid])
    dg = lib.sim_get_degr(sat[sid])
    out = (ctypes.c_float * 3)()
    lib.sim_get_corrected(sat[sid], out)

    ndeg = (ctypes.c_uint8 * 256)()
    lib.sim_get_neighbour_degr(sat[sid], ndeg)
    seen = {i: int(ndeg[i]) for i in range(1, 4) if int(ndeg[i]) != 0}

    print(f"sat{sid}: state={STATE.get(st, st)} degr={dg} corrected=({out[0]:.2f}, {out[1]:.2f}, {out[2]:.2f}) neigh_degr={seen}")


print("\n=== STEP 2: Correction Propagation Test ===")
for sid in (1, 2, 3):
    sat[sid] = lib.sim_create_context(sid)

cb = TX_CB(on_tx)
lib.sim_register_tx_callback(cb)

print("\n[Inject] sat1 FAULT_DETECTED")
lib.sim_inject_event(sat[1], EVT_FAULT_DETECTED)
frames = pump(128)
print(f"[Pump] injected frames: {frames}")

print("\n[Advance] 5.1s to trigger correction compute")
for _ in range(51):
    for sid in (1, 2, 3):
        lib.sim_advance_time(sat[sid], 100)
    pump(128)

print("\n[Final snapshot]")
for sid in (1, 2, 3):
    dump(sid)

for sid in list(sat.keys()):
    lib.sim_destroy_context(sat[sid])

print("\n=== END STEP 2 ===\n")
