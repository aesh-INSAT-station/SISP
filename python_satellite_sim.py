import argparse
import ctypes
import os
import random
from collections import defaultdict

# -------------------------
# Config
# -------------------------
BASE_DIR = os.path.dirname(__file__)
DLL_PATH = os.path.join(BASE_DIR, "c++ implemnetation", "build", "bin", "Release", "sisp.dll")
DEFAULT_NUM_SATS = 5
DEFAULT_MAX_RESPONSE_FRAMES = 10
DEFAULT_PACKET_LOSS_RATE = 0.0
DEFAULT_RANDOM_SEED = 1337

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
        0xA: "BORROW_DECISION",
        0xF: "FAILURE",
    }
    return names.get(svc, f"SVC_{svc}")


# -------------------------
# Simulation state
# -------------------------
sat_contexts = {}
stats = defaultdict(int)
frame_queue = []  # Queue frames to avoid recursion during callbacks
in_callback = False  # Flag to detect if we're in TX callback
PACKET_LOSS_RATE = DEFAULT_PACKET_LOSS_RATE
RNG = random.Random(DEFAULT_RANDOM_SEED)


def route_frame(dst: int, frame: bytes):
    svc, sndr, rcvr, seq, degr, flags = unpack_header(frame)
    stats[f"tx_{service_name(svc)}"] += 1

    # Broadcast destination
    if dst == 0xFF or rcvr == 0xFF:
        targets = [sid for sid in sat_contexts.keys() if sid != sndr]
    else:
        targets = [dst] if dst in sat_contexts else []

    delivered = 0
    dropped = 0
    stats["frames_offered"] += len(targets)

    for target in targets:
        if PACKET_LOSS_RATE > 0.0 and RNG.random() < PACKET_LOSS_RATE:
            dropped += 1
            stats["frames_dropped"] += 1
            stats[f"drop_{service_name(svc)}"] += 1
            continue

        # Queue frame for deferred injection (avoid recursion).
        frame_queue.append((target, frame))
        delivered += 1
        stats["frames_delivered"] += 1
        stats[f"rx_{service_name(svc)}"] += 1

    return delivered, dropped


def on_tx(dst, buf_ptr, length):
    global in_callback
    frame = ctypes.string_at(buf_ptr, length)
    svc, sndr, rcvr, seq, degr, flags = unpack_header(frame)
    delivered, dropped = route_frame(dst, frame)
    print(
        f"[TX] svc={service_name(svc):15s} sndr=0x{sndr:02X} rcvr=0x{rcvr:02X} "
        f"seq={seq:3d} degr={degr:2d} flags=0b{flags:04b} dst=0x{dst:02X} "
        f"enq={delivered} drop={dropped}"
    )
    in_callback = True
    in_callback = False


def process_queue():
    """Drain all queued frames and inject them (deferred from callbacks)."""
    global frame_queue
    while frame_queue:
        target, frame = frame_queue.pop(0)
        buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
        lib.sim_inject_packet(sat_contexts[target], buf, len(frame))


def parse_args():
    parser = argparse.ArgumentParser(
        description="SISP Level 3 multi-satellite simulation with optional packet loss injection"
    )
    parser.add_argument(
        "--num-sats",
        type=int,
        default=DEFAULT_NUM_SATS,
        help=f"Number of satellite contexts to create (default: {DEFAULT_NUM_SATS})",
    )
    parser.add_argument(
        "--max-response-frames",
        type=int,
        default=DEFAULT_MAX_RESPONSE_FRAMES,
        help=(
            "Maximum queued response frames to process after initial event "
            f"(default: {DEFAULT_MAX_RESPONSE_FRAMES})"
        ),
    )
    parser.add_argument(
        "--packet-loss-rate",
        type=float,
        default=DEFAULT_PACKET_LOSS_RATE,
        help=(
            "Packet drop probability in [0.0, 1.0] applied per routed frame "
            f"(default: {DEFAULT_PACKET_LOSS_RATE})"
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=f"Random seed used for packet drop decisions (default: {DEFAULT_RANDOM_SEED})",
    )
    args = parser.parse_args()

    if args.num_sats < 2:
        parser.error("--num-sats must be >= 2")
    if args.max_response_frames < 1:
        parser.error("--max-response-frames must be >= 1")
    if args.packet_loss_rate < 0.0 or args.packet_loss_rate > 1.0:
        parser.error("--packet-loss-rate must be between 0.0 and 1.0")

    return args


def main():
    args = parse_args()
    global PACKET_LOSS_RATE
    global RNG
    PACKET_LOSS_RATE = args.packet_loss_rate
    RNG = random.Random(args.seed)

    frame_queue.clear()
    stats.clear()

    # Create satellite contexts
    for sat_id in range(1, args.num_sats + 1):
        ptr = lib.sim_create_context(sat_id)
        if not ptr:
            raise RuntimeError(f"Failed to create context for sat {sat_id}")
        sat_contexts[sat_id] = ptr

    cb = TX_CB(on_tx)
    lib.sim_register_tx_callback(cb)

    print("\n=== Multi-Satellite Protocol Simulation (Python Level 3) ===")
    print(f"Satellites: {list(sat_contexts.keys())}")
    print(
        "Config: "
        f"packet_loss_rate={PACKET_LOSS_RATE:.2f}, seed={args.seed}, "
        f"max_response_frames={args.max_response_frames}"
    )
    print(
        "NOTE: Cascading failures suppress cascading re-broadcasts after "
        f"{args.max_response_frames} processed frames to prevent mesh storm\n"
    )

    # Simple test: trigger ONE failure, observe propagation
    print("[TEST] Injecting EVT_CRITICAL_FAILURE on sat1")
    lib.sim_inject_event(sat_contexts[1], EVT_CRITICAL_FAILURE)
    
    # Process first wave of responses with a cap to prevent mesh storms.
    print(
        "[Response] Processing up to "
        f"{args.max_response_frames} outgoing frames from satellite state machine..."
    )
    frames_seen = 0
    while frame_queue and frames_seen < args.max_response_frames:
        target, frame = frame_queue.pop(0)
        buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
        lib.sim_inject_packet(sat_contexts[target], buf, len(frame))
        frames_seen += 1

    print(f"[Observed] {frames_seen} frames broadcast from initial failure trigger")

    print("\n=== Final Satellite States (After Initial Failure Wave) ===")
    # State enum: 0=IDLE, 20=CRITICAL_FAIL (based on state_machine.hpp)
    state_map = {
        0: "IDLE", 1: "CORR_WAIT_RSP", 2: "CORR_COMPUTING", 
        3: "RELAY_REACHING_OUT", 4: "RELAY_WAIT_ACCEPT", 5: "RELAY_RECEIVING", 
        6: "RELAY_SENDING", 7: "RELAY_PROCESSING", 8: "RECV_HEARTBEAT", 
        9: "SEND_HEARTBEAT", 10: "CRITICAL_FAIL", 11: "DOWNLINK_WAIT_ACK", 12: "BORROW_RESPONDING",
        20: "CRITICAL_FAIL_EX"
    }
    for sat_id, ctx in sat_contexts.items():
        state = lib.sim_get_state(ctx)
        degr = lib.sim_get_degr(ctx)
        state_name = state_map.get(state, f"UNKNOWN({state})")
        print(f"  sat{sat_id}: state={state:2d} ({state_name:18s}) degr={degr:2d}")

    print("\n=== Traffic Summary (TX only) ===")
    for k in sorted(stats.keys()):
        if k.startswith("tx_"):
            print(f"{k:30s} {stats[k]:3d}")

    if PACKET_LOSS_RATE > 0.0:
        offered = stats["frames_offered"]
        dropped = stats["frames_dropped"]
        delivered = stats["frames_delivered"]
        observed_drop_rate = (float(dropped) / float(offered)) if offered else 0.0
        print("\n=== Packet Loss Summary ===")
        print(f"frames_offered               {offered:3d}")
        print(f"frames_delivered             {delivered:3d}")
        print(f"frames_dropped               {dropped:3d}")
        print(f"observed_drop_rate           {observed_drop_rate:.3f}")
        for k in sorted(stats.keys()):
            if k.startswith("drop_"):
                print(f"{k:30s} {stats[k]:3d}")

    # Cleanup
    for ctx in sat_contexts.values():
        lib.sim_destroy_context(ctx)

    print("\nSimulation complete.")


if __name__ == "__main__":
    main()
