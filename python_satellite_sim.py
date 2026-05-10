import ctypes
import os
import struct
import time
from collections import defaultdict

# -------------------------
# Config
# -------------------------
BASE_DIR = os.path.dirname(__file__)
DLL_PATH = os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll")
NUM_SATS = 5
SIM_SECONDS = 7
TICK_MS = 100

if not os.path.exists(DLL_PATH):
    raise FileNotFoundError(f"sisp.dll not found at: {DLL_PATH}")

lib = ctypes.CDLL(DLL_PATH)

# -------------------------
# C API bindings
# -------------------------
# Context* sim_create_context(uint8_t my_id);
lib.sim_create_context.argtypes = [ctypes.c_uint8]
lib.sim_create_context.restype = ctypes.c_void_p

# void sim_destroy_context(SISP::Context* ctx);
lib.sim_destroy_context.argtypes = [ctypes.c_void_p]
lib.sim_destroy_context.restype = None

# void sim_inject_packet(SISP::Context* ctx, const uint8_t* buf, uint16_t len);
lib.sim_inject_packet.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16]
lib.sim_inject_packet.restype = None

# void sim_inject_event(SISP::Context* ctx, SISP::Event evt);
lib.sim_inject_event.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.sim_inject_event.restype = None

# void sim_advance_time(SISP::Context* ctx, uint32_t ms);
lib.sim_advance_time.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
lib.sim_advance_time.restype = None

# uint8_t sim_get_degr(const SISP::Context* ctx);
lib.sim_get_degr.argtypes = [ctypes.c_void_p]
lib.sim_get_degr.restype = ctypes.c_uint8

# SISP::State sim_get_state(const SISP::Context* ctx);
lib.sim_get_state.argtypes = [ctypes.c_void_p]
lib.sim_get_state.restype = ctypes.c_int

# void sim_register_tx_callback(sim_tx_cb cb);
TX_CB = ctypes.CFUNCTYPE(None, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16)
lib.sim_register_tx_callback.argtypes = [TX_CB]
lib.sim_register_tx_callback.restype = None

# -------------------------
# Event enum values (must match C++)
# -------------------------
EVT_FAULT_DETECTED = 12
EVT_ENERGY_LOW = 14
EVT_CRITICAL_FAILURE = 21

# -------------------------
# Helpers
# -------------------------
def unpack_header(frame: bytes):
    """Unpack 5-byte protocol header from frame[0:5]."""
    b0, b1, b2, b3, b4 = frame[:5]
    svc = (b0 >> 4) & 0x0F
    sndr = ((b0 & 0x0F) << 4) | ((b1 >> 4) & 0x0F)
    rcvr = ((b1 & 0x0F) << 4) | ((b2 >> 4) & 0x0F)
    seq = ((b2 & 0x0F) << 4) | ((b3 >> 4) & 0x0F)
    degr = b3 & 0x0F
    flags = (b4 >> 4) & 0x0F
    return svc, sndr, rcvr, seq, degr, flags


def service_name(svc: int) -> str:
    names = {
        0x1: "CORRECTION_REQ",
        0x2: "CORRECTION_RSP",
        0x3: "RELAY_REQ",
        0x4: "RELAY_ACCEPT",
        0x5: "RELAY_REJECT",
        0x6: "DOWNLINK_DATA",
        0x7: "DOWNLINK_ACK",
        0x8: "STATUS_BROADCAST",
        0x9: "HEARTBEAT",
        0xE: "BORROW_REQ",
        0xF: "FAILURE",
    }
    return names.get(svc, f"SVC_{svc}")


# -------------------------
# Simulation state
# -------------------------
sat_contexts = {}
stats = defaultdict(int)


def route_frame(dst: int, frame: bytes):
    svc, sndr, rcvr, seq, degr, flags = unpack_header(frame)
    stats[f"tx_{service_name(svc)}"] += 1

    # Broadcast destination
    if dst == 0xFF or rcvr == 0xFF:
        targets = [sid for sid in sat_contexts.keys() if sid != sndr]
    else:
        targets = [dst] if dst in sat_contexts else []

    for target in targets:
        buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
        lib.sim_inject_packet(sat_contexts[target], buf, len(frame))
        stats[f"rx_{service_name(svc)}"] += 1


def on_tx(dst, buf_ptr, length):
    frame = ctypes.string_at(buf_ptr, length)
    svc, sndr, rcvr, seq, degr, flags = unpack_header(frame)
    print(
        f"[TX] svc={service_name(svc):15s} sndr=0x{sndr:02X} rcvr=0x{rcvr:02X} "
        f"seq={seq:3d} degr={degr:2d} flags=0b{flags:04b} dst=0x{dst:02X}"
    )
    route_frame(dst, frame)


def main():
    # Create satellite contexts
    for sat_id in range(1, NUM_SATS + 1):
        ptr = lib.sim_create_context(sat_id)
        if not ptr:
            raise RuntimeError(f"Failed to create context for sat {sat_id}")
        sat_contexts[sat_id] = ptr

    cb = TX_CB(on_tx)
    lib.sim_register_tx_callback(cb)

    print("\n=== Multi-Satellite Protocol Simulation ===")
    print(f"Satellites: {list(sat_contexts.keys())}")

    # IT-01: Trigger correction on sat2
    print("\n[IT-01] Trigger correction on sat2")
    lib.sim_inject_event(sat_contexts[2], EVT_FAULT_DETECTED)

    # IT-03: Relay across visibility gap (simulate low energy on sat2)
    print("\n[IT-03] Relay request from sat2")
    lib.sim_inject_event(sat_contexts[2], EVT_ENERGY_LOW)

    # IT-04: Failure broadcast from sat1
    print("\n[IT-04] Critical failure on sat1")
    lib.sim_inject_event(sat_contexts[1], EVT_CRITICAL_FAILURE)

    # Advance simulated time
    steps = int((SIM_SECONDS * 1000) / TICK_MS)
    for _ in range(steps):
        for ctx in sat_contexts.values():
            lib.sim_advance_time(ctx, TICK_MS)

    print("\n=== Final Satellite States ===")
    for sat_id, ctx in sat_contexts.items():
        state = lib.sim_get_state(ctx)
        degr = lib.sim_get_degr(ctx)
        print(f"sat{sat_id}: state={state:2d} degr={degr:2d}")

    print("\n=== Traffic Summary ===")
    for k in sorted(stats.keys()):
        print(f"{k:24s} {stats[k]}")

    # Cleanup
    for ctx in sat_contexts.values():
        lib.sim_destroy_context(ctx)

    print("\nSimulation complete.")


if __name__ == "__main__":
    main()
