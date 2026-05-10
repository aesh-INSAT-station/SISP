#!/usr/bin/env python3
import ctypes
import os
from typing import Dict, List, Optional, Tuple

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

# Event IDs from Event enum in sisp_state_machine.hpp
EVT_GS_VISIBLE = 15
EVT_ALL_FRAGS_SENT = 17
EVT_ALL_FRAGS_RCVD = 18
EVT_SENSOR_READ_DONE = 19

# States (for readable logs)
STATE_NAME = {
    0: "IDLE",
    13: "BORROW_WAIT_ACCEPT",
    14: "BORROW_RECEIVING",
    15: "BORROW_DONE",
    16: "BORROW_SAMPLING",
    17: "BORROW_SENDING",
}

SERVICE_NAME = {
    0x5: "DOWNLINK_DATA",
    0x6: "DOWNLINK_ACK",
    0xA: "BORROW_DECISION",
    0xE: "BORROW_REQ",
}

BORROWER_ID = 1
PROVIDER_A_ID = 2
PROVIDER_B_ID = 3



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



def payload_view(frame: bytes) -> bytes:
    payload_len = int(frame[5])
    ext_len = int(frame[6])
    payload_offset = 8 + ext_len
    return frame[payload_offset:payload_offset + payload_len]



def parse_borrow_decision(payload: bytes) -> Tuple[int, int]:
    if len(payload) < 3:
        return (0, 0)
    accepted = int(payload[0])
    duration = (int(payload[1]) << 8) | int(payload[2])
    return (accepted, duration)



def parse_downlink_data(payload: bytes) -> Tuple[int, int, int, bytes]:
    if len(payload) < 6:
        return (0, 0, 0, b"")
    frag_idx = (int(payload[0]) << 8) | int(payload[1])
    frag_total = (int(payload[2]) << 8) | int(payload[3])
    data_len = (int(payload[4]) << 8) | int(payload[5])
    data = payload[6:6 + data_len]
    return (frag_idx, frag_total, data_len, data)



class BorrowFlowNetwork:
    def __init__(self, drop_second_decision: bool) -> None:
        self.drop_second_decision = drop_second_decision
        self.sat: Dict[int, ctypes.c_void_p] = {}
        self.queue: List[Tuple[int, bytes]] = []
        self.decision_transmissions_to_borrower = 0
        self.decision_delivered_to_borrower: List[int] = []
        self.accepted_provider_id: Optional[int] = None
        self.dropped_decision_from: Optional[int] = None
        self.tx_log: List[str] = []
        self.cb = TX_CB(self.on_tx)

    def setup(self) -> None:
        for sid in (BORROWER_ID, PROVIDER_A_ID, PROVIDER_B_ID):
            ptr = lib.sim_create_context(sid)
            if not ptr:
                raise RuntimeError(f"Failed to create context for sat{sid}")
            self.sat[sid] = ptr
        lib.sim_register_tx_callback(self.cb)

    def cleanup(self) -> None:
        for ptr in self.sat.values():
            lib.sim_destroy_context(ptr)
        self.sat.clear()

    def inject_packet(self, target_id: int, frame: bytes) -> None:
        buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
        lib.sim_inject_packet(self.sat[target_id], buf, len(frame))

    def on_tx(self, dst, buf_ptr, length):
        frame = ctypes.string_at(buf_ptr, length)
        svc, sndr, rcvr, seq, degr, flags = decode_header(frame)

        if dst == 0xFF or rcvr == 0xFF:
            targets = [sid for sid in self.sat.keys() if sid != sndr]
        else:
            targets = [dst] if dst in self.sat else []

        base = (
            f"[TX] svc={service_name(svc):15s} sndr={sndr:02X} rcvr={rcvr:02X} "
            f"seq={seq:3d} dst={dst:02X} targets={targets}"
        )

        payload = payload_view(frame)
        if svc == 0xA:
            accepted, duration = parse_borrow_decision(payload)
            base += f" decision=(accepted={accepted}, duration_s={duration})"
        elif svc == 0x5:
            frag_idx, frag_total, data_len, frag_data = parse_downlink_data(payload)
            text = frag_data.decode("ascii", errors="replace")
            base += f" fragment=({frag_idx+1}/{frag_total}, len={data_len}) text='{text}'"

        print(base)
        self.tx_log.append(base)

        for target in targets:
            # Optional model: drop the second answer (sat3 -> borrower BORROW_DECISION).
            if (
                self.drop_second_decision
                and svc == 0xA
                and sndr == PROVIDER_B_ID
                and target == BORROWER_ID
                and self.dropped_decision_from is None
            ):
                self.dropped_decision_from = sndr
                print("[NET] dropping second BORROW_DECISION (from sat3 to sat1)")
                continue

            if svc == 0xA and target == BORROWER_ID:
                self.decision_transmissions_to_borrower += 1

            self.queue.append((target, frame))

    def pump(self, max_frames: int = 512) -> int:
        processed = 0
        while self.queue and processed < max_frames:
            target, frame = self.queue.pop(0)
            svc, sndr, rcvr, seq, degr, flags = decode_header(frame)
            if svc == 0xA and target == BORROWER_ID:
                self.decision_delivered_to_borrower.append(sndr)
                if self.accepted_provider_id is None:
                    self.accepted_provider_id = sndr
            self.inject_packet(target, frame)
            processed += 1
        return processed

    def borrower_recovered_text(self) -> str:
        rx_len = int(lib.sim_get_relay_rx_len(self.sat[BORROWER_ID]))
        if rx_len <= 0:
            return ""
        rx_buf = (ctypes.c_uint8 * rx_len)()
        copied = int(lib.sim_copy_relay_rx_payload(self.sat[BORROWER_ID], rx_buf, rx_len))
        return bytes(rx_buf[:copied]).decode("ascii", errors="replace")



def run_case(case_name: str, drop_second_decision: bool) -> None:
    print("\n" + "=" * 90)
    print(case_name)
    print("=" * 90)

    network = BorrowFlowNetwork(drop_second_decision=drop_second_decision)
    network.setup()

    try:
        paragraph_provider_a = "Orbit stable. Borrow camera. Send map now."
        paragraph_provider_b = "Backup ready. Alternate camera data online."

        print(f"Provider A paragraph (before): {paragraph_provider_a}")
        print(f"Provider B paragraph (before): {paragraph_provider_b}")

        a_bytes = paragraph_provider_a.encode("ascii")
        b_bytes = paragraph_provider_b.encode("ascii")
        lib.sim_set_relay_payload(
            network.sat[PROVIDER_A_ID],
            (ctypes.c_uint8 * len(a_bytes)).from_buffer_copy(a_bytes),
            len(a_bytes),
        )
        lib.sim_set_relay_payload(
            network.sat[PROVIDER_B_ID],
            (ctypes.c_uint8 * len(b_bytes)).from_buffer_copy(b_bytes),
            len(b_bytes),
        )

        print("\n[STEP] Borrower sat1 issues BORROW_REQ (GS_VISIBLE event)")
        lib.sim_inject_event(network.sat[BORROWER_ID], EVT_GS_VISIBLE)
        for _ in range(8):
            if network.pump() == 0:
                break

        borrower_state = int(lib.sim_get_state(network.sat[BORROWER_ID]))
        print(f"Borrower state after decisions: {state_name(borrower_state)} ({borrower_state})")
        print(f"Decision responses transmitted to sat1: {network.decision_transmissions_to_borrower}")
        print(f"Decision responses delivered to sat1: {network.decision_delivered_to_borrower}")

        if network.accepted_provider_id is None:
            raise AssertionError("No BORROW_DECISION delivered to borrower")

        print(
            f"Accepted provider selected by first delivered decision: sat{network.accepted_provider_id}"
        )

        print(
            f"\n[STEP] Trigger SENSOR_READ_DONE only on accepted provider sat{network.accepted_provider_id}"
        )
        lib.sim_inject_event(network.sat[network.accepted_provider_id], EVT_SENSOR_READ_DONE)
        for _ in range(8):
            if network.pump() == 0:
                break

        # Close out both sides for deterministic final states.
        lib.sim_inject_event(network.sat[network.accepted_provider_id], EVT_ALL_FRAGS_SENT)
        lib.sim_inject_event(network.sat[BORROWER_ID], EVT_ALL_FRAGS_RCVD)

        provider_state = int(lib.sim_get_state(network.sat[network.accepted_provider_id]))
        borrower_state = int(lib.sim_get_state(network.sat[BORROWER_ID]))
        print(f"Provider state: {state_name(provider_state)} ({provider_state})")
        print(f"Borrower state: {state_name(borrower_state)} ({borrower_state})")

        recovered = network.borrower_recovered_text()
        print(f"Borrower paragraph (after): {recovered}")

        expected = paragraph_provider_a if network.accepted_provider_id == PROVIDER_A_ID else paragraph_provider_b
        if recovered != expected:
            raise AssertionError(
                f"Recovered paragraph mismatch. Expected '{expected}', got '{recovered}'"
            )

        if drop_second_decision:
            print(
                f"Dropped second decision sender: sat{network.dropped_decision_from if network.dropped_decision_from else 'none'}"
            )

        print("\nResult: communication uses explicit unicast addresses after acceptance")
        print("- BORROW_REQ uses broadcast target 0xFF")
        print("- BORROW_DECISION uses unicast target sat1")
        print(f"- DOWNLINK_DATA then comes from accepted sat{network.accepted_provider_id} to sat1")

    finally:
        network.cleanup()



def main() -> None:
    run_case(
        case_name="CASE 1: Multiple answers delivered (first accepted, later answer effectively ignored)",
        drop_second_decision=False,
    )
    run_case(
        case_name="CASE 2: Multiple answers modeled, second answer dropped",
        drop_second_decision=True,
    )


if __name__ == "__main__":
    main()
