import math
import os
import ctypes
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
from scipy.special import erfc
from scipy.stats import binom

# Apply Dark Theme to Matplotlib
plt.style.use('dark_background')
plt.rcParams['axes.facecolor'] = '#0a0a0a'
plt.rcParams['figure.facecolor'] = '#0a0a0a'
plt.rcParams['axes.edgecolor'] = '#333333'
plt.rcParams['grid.color'] = '#222222'
plt.rcParams['text.color'] = '#ffffff'
plt.rcParams['xtick.color'] = '#888888'
plt.rcParams['ytick.color'] = '#888888'


try:
    from skyfield.api import load, EarthSatellite, wgs84

    _SKYFIELD_OK = True
except Exception:
    _SKYFIELD_OK = False


# =============================================================================
# Constants + shared PHY/protocol model
# =============================================================================

C_MPS = 299_792_458.0
K_B = 1.380649e-23
T0_K = 290.0  # IEEE standard reference temperature

FRAME_BYTES = 64
FRAME_BITS = FRAME_BYTES * 8

# Coding parameters (Conv R=1/2, RS(255,223))
R_CONV = 0.5
R_RS = 223.0 / 255.0
R_TOTAL = R_CONV * R_RS

# K=7 R=1/2 NASA-standard convolutional code free distance
CONV_K7_D_FREE = 10
# Coefficient from spectral distance enumerator for K=7 R=1/2 code (soft Viterbi)
CONV_K7_COEFF = 36


def qfunc(x: np.ndarray) -> np.ndarray:
    return 0.5 * erfc(x / np.sqrt(2.0))


def ber_uncoded_awgn(ebn0_db: np.ndarray, modulation: str) -> np.ndarray:
    """Rigorous AWGN BER models.

    BPSK / QPSK:   P_b = (1/2)·erfc(sqrt(Eb/N0))          — exact coherent AWGN
    GMSK BT=0.3:   P_b = (1/2)·erfc(sqrt(0.68·Eb/N0))     — Murota-Hirade 1981, §III
                   α_BT=0.68 captures inter-symbol interference from BT filtering
    2-FSK coh.:    P_b = Q(sqrt(Eb/N0))                     — orthogonal coherent FSK
    2-FSK noncoh.: P_b = (1/2)·exp(−Eb/(2·N0))             — exact noncoherent FSK
    """
    ebn0_lin = 10.0 ** (ebn0_db / 10.0)

    if modulation in ("BPSK", "QPSK"):
        return 0.5 * erfc(np.sqrt(ebn0_lin))

    if modulation == "GMSK_BT03":
        # GMSK BT=0.3 coherent detection — Murota & Hirade (1981)
        # α_BT ≈ 0.68 for BT=0.3; equals 0.85 for BT→∞ (BPSK limit)
        alpha_bt = 0.68
        return 0.5 * erfc(np.sqrt(alpha_bt * ebn0_lin))

    if modulation == "2FSK_COH":
        return qfunc(np.sqrt(ebn0_lin))

    if modulation == "2FSK_NONCOH":
        return 0.5 * np.exp(-0.5 * ebn0_lin)

    raise ValueError(f"Unknown modulation: {modulation}")


def _ber_conv_k7_r12(ebn0_db: np.ndarray, modulation: str) -> np.ndarray:
    """Post-Viterbi BER for K=7 R=1/2 code via union bound (soft decision).

    For BPSK/QPSK/GMSK through AWGN — Heller & Jacobs (1971), d_free=10:
        P_b ≤ 36 · Q(sqrt(10 · Eb/N0))

    For FSK, coherent or noncoherent, the channel BER p is first computed,
    then the union bound is applied on the coded sequence BER using the
    soft-decision approximation with the channel error probability.
    """
    ebn0_lin = 10.0 ** (ebn0_db / 10.0)

    if modulation in ("BPSK", "QPSK", "GMSK_BT03"):
        # Soft-decision Viterbi union bound (Heller & Jacobs 1971)
        # d_free = 10, leading term coefficient = 36
        return np.minimum(
            CONV_K7_COEFF * qfunc(np.sqrt(CONV_K7_D_FREE * ebn0_lin)),
            0.5,
        )

    # For FSK: hard-decision bound using channel BER p
    # P_b ≤ Σ_{d=d_free}^{∞} c_d · B(d) where B(d) ≈ (4p(1-p))^(d/2)
    # Leading term approximation: P_b ≤ 36 · (4p(1−p))^5
    p_ch = ber_uncoded_awgn(ebn0_db, modulation)
    term = np.clip(4.0 * p_ch * (1.0 - p_ch), 0.0, 1.0) ** (CONV_K7_D_FREE / 2.0)
    return np.minimum(CONV_K7_COEFF * term, 0.5)


def ber_post_decoding(ebn0_db: np.ndarray, modulation: str, coding: str) -> np.ndarray:
    """Post-FEC BER.

    CONV uses the K=7 R=1/2 soft-Viterbi union bound (replaces constant 7 dB proxy).
    CONV_RS cascades the Viterbi BER into the RS(255,223) byte-error model.
    """
    if coding == "NONE":
        return ber_uncoded_awgn(ebn0_db, modulation)

    if coding == "CONV":
        return _ber_conv_k7_r12(ebn0_db, modulation)

    if coding == "CONV_RS":
        ber_conv = _ber_conv_k7_r12(ebn0_db, modulation)
        # Byte error probability after Viterbi (assumes i.i.d. residual bits)
        p_byte = 1.0 - (1.0 - ber_conv) ** 8
        # RS(255,223): t=16 correctable byte errors; failure if >16 byte errors
        p_fail = binom.sf(16, 255, p_byte)  # P(N_err > 16)
        # Failed RS block → effectively random bits (BER→0.5)
        return 0.5 * p_fail

    raise ValueError(f"Unknown coding: {coding}")


def coding_expansion(coding: str) -> float:
    if coding == "NONE":
        return 1.0
    if coding == "CONV":
        return 1.0 / R_CONV
    if coding == "CONV_RS":
        return 1.0 / R_TOTAL
    raise ValueError(f"Unknown coding: {coding}")


def nf_to_tsys(nf_db: float, t_ant_k: float = 100.0) -> float:
    """Convert receiver noise figure (dB) + antenna noise temp to system noise temperature.

    T_sys = T_ant + T_rx  where  T_rx = T0·(F−1),  F = 10^(NF/10)
    T0 = 290 K (IEEE reference).  T_ant ≈ 100 K typical for inter-satellite UHF.
    """
    f_lin = 10.0 ** (nf_db / 10.0)
    t_rx = T0_K * (f_lin - 1.0)
    return t_ant_k + t_rx


def calc_link_budget(
    d_km: np.ndarray,
    p_tx_dbm: float,
    f_hz: float,
    g_tx_dbi: float,
    g_rx_dbi: float,
    t_sys_k: float,
    b_hz: float,
    r_bps: float,
    pointing_loss_db: float,
    misc_loss_db: float,
    doppler_margin_db: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute SNR and Eb/N0 from free-space link budget.

    doppler_margin_db: additional implementation loss for Doppler compensation
    (e.g., 1.5 dB for GMSK/GFSK on 12.5 kHz narrow-band ISL at 437 MHz).
    """
    d_m = d_km * 1000.0
    l_fs_db = 20.0 * np.log10(d_m) + 20.0 * np.log10(f_hz) + 20.0 * np.log10(4.0 * np.pi / C_MPS)

    n_w = K_B * t_sys_k * b_hz
    n_dbm = 10.0 * np.log10(n_w) + 30.0

    snr_db = (p_tx_dbm + g_tx_dbi + g_rx_dbi
              - l_fs_db - pointing_loss_db - misc_loss_db - doppler_margin_db
              - n_dbm)
    ebn0_db = snr_db + 10.0 * np.log10(b_hz / max(r_bps, 1.0))
    return snr_db, ebn0_db


def per_from_ber(ber: np.ndarray, info_bits: int) -> np.ndarray:
    ber = np.clip(ber, 0.0, 1.0)
    return 1.0 - np.exp(info_bits * np.log1p(-ber))


def one_way_prop_delay_s(d_km: float) -> float:
    return (d_km * 1000.0) / C_MPS


def fmt_si_rate(bps: float) -> str:
    if bps >= 1e6:
        return f"{bps/1e6:.2f} Mbps"
    if bps >= 1e3:
        return f"{bps/1e3:.2f} kbps"
    return f"{bps:.0f} bps"


def fmt_time_s(seconds: float) -> str:
    if seconds < 1e-3:
        return f"{seconds*1e6:.1f} µs"
    if seconds < 1.0:
        return f"{seconds*1e3:.2f} ms"
    if seconds < 120.0:
        return f"{seconds:.2f} s"
    if seconds < 3600.0:
        return f"{seconds/60.0:.2f} min"
    return f"{seconds/3600.0:.2f} h"


# =============================================================================
# C++ protocol probe (optional; used for message energy attribution)
# =============================================================================

SERVICES = {
    0x0: "CORRECTION_REQ",
    0x1: "CORRECTION_RSP",
    0x2: "RELAY_REQ",
    0x3: "RELAY_ACCEPT",
    0x4: "RELAY_REJECT",
    0x5: "RELAY_DATA",
    0x6: "HEARTBEAT",
    0x7: "DOWNLINK_DATA",
    0x8: "DOWNLINK_ACK",
    0xA: "BORROW_DECISION",
    0xE: "BORROW_REQ",
    0xF: "FAILURE",
}

# Must match `SISP::Event` values in `c++ implemnetation/include/sisp_state_machine.hpp`.
EVT_FAULT_DETECTED = 12
EVT_ENERGY_LOW = 14
EVT_CRITICAL_FAILURE = 21


PHY_NAMES = {0: "CTRL_NARROW", 1: "BULK_WIDE"}


@dataclass(frozen=True)
class TxEvent:
    svc: int
    svc_name: str
    sndr: int
    rcvr: int
    dst: int
    length_b: int
    targets: Tuple[int, ...]
    phy_profile: int = 0  # 0=CONTROL_437_NARROW, 1=BULK_437_WIDE (frame byte 8)


def _unpack_header(frame: bytes) -> Tuple[int, int, int, int, int, int]:
    """Decode 5-byte packed header.

    Bit layout (encoder canonical):
    Byte 0: [ SVC[3:0] (high 4) | SNDR[7:4] (low 4) ]
    Byte 1: [ SNDR[3:0] (high 4) | RCVR[7:4] (low 4) ]
    Byte 2: [ RCVR[3:0] (high 4) | SEQ[7:4]  (low 4) ]
    Byte 3: [ SEQ[3:0]  (high 4) | DEGR[3:0] (low 4) ]
    Byte 4: [ FLAGS[3:0](high 4) | CKSM[3:0] (low 4) ]
    """
    if len(frame) < 5:
        return (0, 0, 0, 0, 0, 0)
    byte0 = frame[0]
    byte1 = frame[1]
    byte2 = frame[2]
    byte3 = frame[3]
    byte4 = frame[4]

    svc  = (byte0 >> 4) & 0x0F          # high nibble of byte 0
    sndr = ((byte0 & 0x0F) << 4) | ((byte1 >> 4) & 0x0F)
    rcvr = ((byte1 & 0x0F) << 4) | ((byte2 >> 4) & 0x0F)
    seq  = ((byte2 & 0x0F) << 4) | ((byte3 >> 4) & 0x0F)
    degr = byte3 & 0x0F
    flags = (byte4 >> 4) & 0x0F
    return svc, sndr, rcvr, seq, degr, flags


def _decode_phy_profile(frame: bytes) -> int:
    """Read PHY profile from 64-byte frame byte 8.

    After the 5-byte header, encode_frame writes:
      [5] payload_len  [6] ext_len  [7] flags copy
      [8] phy_profile  [9] phy_cap_mask
    Returns 0 (CONTROL_437_NARROW) or 1 (BULK_437_WIDE).
    """
    if len(frame) > 8:
        return int(frame[8]) & 0xFF
    return 0


def _svc_name(svc: int) -> str:
    return SERVICES.get(svc, f"SVC_{svc:X}")


@st.cache_data(show_spinner=False)
def run_protocol_probe(
    dll_path: str,
    scenario: str,
    num_sats: int,
    packet_loss_rate: float,
    advance_total_ms: int,
    tick_ms: int,
    seed: int,
) -> List[TxEvent]:
    """Run a short C++ state-machine probe and return emitted frames.

    This does NOT simulate PHY BER/PER; it measures how many 64B frames the
    state machine *attempts* to send per service.
    """
    if not os.path.exists(dll_path):
        raise FileNotFoundError(f"sisp.dll not found at: {dll_path}")

    rng = random.Random(seed)

    lib = ctypes.CDLL(dll_path)

    # Bindings
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

    TX_CB = ctypes.CFUNCTYPE(None, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint16)
    lib.sim_register_tx_callback.argtypes = [TX_CB]
    lib.sim_register_tx_callback.restype = None

    sat_contexts: Dict[int, int] = {}
    frame_queue: List[Tuple[int, bytes]] = []
    events: List[TxEvent] = []

    def process_queue():
        while frame_queue:
            target, frame = frame_queue.pop(0)
            buf = (ctypes.c_uint8 * len(frame)).from_buffer_copy(frame)
            lib.sim_inject_packet(sat_contexts[target], buf, len(frame))

    def on_tx(dst, buf_ptr, length):
        frame = ctypes.string_at(buf_ptr, length)
        svc, sndr, rcvr, seq, degr, flags = _unpack_header(frame)
        phy = _decode_phy_profile(frame)  # 0=CTRL_NARROW, 1=BULK_WIDE

        # Determine delivery targets (as the python harness does)
        if dst == 0xFF or rcvr == 0xFF:
            targets = tuple(sorted([s for s in sat_contexts.keys() if s != sndr]))
        else:
            targets = (int(dst),) if int(dst) in sat_contexts else tuple()

        # Apply loss (optional)
        delivered_targets: List[int] = []
        for t in targets:
            if packet_loss_rate <= 0.0 or rng.random() > packet_loss_rate:
                frame_queue.append((t, frame))
                delivered_targets.append(t)

        events.append(
            TxEvent(
                svc=int(svc),
                svc_name=_svc_name(int(svc)),
                sndr=int(sndr),
                rcvr=int(rcvr),
                dst=int(dst),
                length_b=int(length),
                targets=tuple(delivered_targets),
                phy_profile=phy,
            )
        )

    cb = TX_CB(on_tx)

    # Create topology
    for sat_id in range(1, int(num_sats) + 1):
        ctx = lib.sim_create_context(ctypes.c_uint8(sat_id))
        if not ctx:
            raise RuntimeError(f"Failed to create context for sat {sat_id}")
        sat_contexts[sat_id] = ctx

    try:
        lib.sim_register_tx_callback(cb)

        # Scenario injections
        if scenario == "Correction (fault detected)":
            lib.sim_inject_event(sat_contexts[1], EVT_FAULT_DETECTED)
            process_queue()

        elif scenario == "Failure broadcast (critical failure)":
            sat_fail = 1 if num_sats < 3 else 3
            lib.sim_inject_event(sat_contexts[sat_fail], EVT_CRITICAL_FAILURE)
            process_queue()

        elif scenario == "Relay request (energy low)":
            lib.sim_inject_event(sat_contexts[1], EVT_ENERGY_LOW)
            process_queue()

        else:
            raise ValueError(f"Unknown scenario: {scenario}")

        # Advance time
        total = 0
        while total < int(advance_total_ms):
            for ctx in sat_contexts.values():
                lib.sim_advance_time(ctx, ctypes.c_uint32(tick_ms))
            process_queue()
            total += int(tick_ms)

    finally:
        for ctx in sat_contexts.values():
            lib.sim_destroy_context(ctx)

    return events


def energy_from_events(
    events: List[TxEvent],
    r_bps: float,
    coding: str,
    p_tx_dc_w: float,
    p_rx_dc_w: float,
    per_frame: float,
    use_expected_retries: bool,
) -> Tuple[Dict[str, dict], Dict[int, dict]]:
    """Aggregate TX/RX energy by service and by satellite.

    If use_expected_retries is True, scale each transmitted frame by E[T]=1/(1-PER).
    This is a first-order PHY-loss adjustment (no ACK modeling).
    """
    exp_tx_mult = 1.0
    if use_expected_retries:
        exp_tx_mult = 1.0 / max(1e-9, (1.0 - float(per_frame)))

    # Treat each protocol frame as FRAME_BYTES on-air, expanded by coding.
    bits_on_air = FRAME_BITS * coding_expansion(coding)
    t_frame = bits_on_air / max(r_bps, 1.0)

    by_service: Dict[str, dict] = {}
    by_sat: Dict[int, dict] = {}

    def sat_rec(sid: int) -> dict:
        if sid not in by_sat:
            by_sat[sid] = {"tx_frames": 0.0, "rx_frames": 0.0, "tx_j": 0.0, "rx_j": 0.0}
        return by_sat[sid]

    for ev in events:
        svc = ev.svc_name
        if svc not in by_service:
            by_service[svc] = {
                "tx_frames": 0.0,
                "rx_frames": 0.0,
                "tx_j": 0.0,
                "rx_j": 0.0,
            }

        # TX side
        tx_frames = 1.0 * exp_tx_mult
        tx_j = tx_frames * t_frame * p_tx_dc_w

        by_service[svc]["tx_frames"] += tx_frames
        by_service[svc]["tx_j"] += tx_j

        srec = sat_rec(ev.sndr)
        srec["tx_frames"] += tx_frames
        srec["tx_j"] += tx_j

        # RX side (each delivered target listens)
        rx_targets = len(ev.targets)
        rx_frames = float(rx_targets) * exp_tx_mult
        rx_j = rx_frames * t_frame * p_rx_dc_w

        by_service[svc]["rx_frames"] += rx_frames
        by_service[svc]["rx_j"] += rx_j

        for t in ev.targets:
            trec = sat_rec(int(t))
            trec["rx_frames"] += 1.0 * exp_tx_mult
            trec["rx_j"] += (1.0 * exp_tx_mult) * t_frame * p_rx_dc_w

    # Add totals
    for rec in by_service.values():
        rec["total_j"] = rec["tx_j"] + rec["rx_j"]
    for rec in by_sat.values():
        rec["total_j"] = rec["tx_j"] + rec["rx_j"]

    return by_service, by_sat


# =============================================================================
# Streamlit UI
# =============================================================================

st.set_page_config(page_title="SISP Unified Simulation", layout="wide")

# Custom Premium Theme: Black and Blue
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');
    
    :root {
        --primary: #00a2ff;
        --bg-dark: #0a0a0a;
        --card-bg: rgba(255, 255, 255, 0.03);
    }
    
    html, body, [data-testid="stAppViewContainer"] {
        background-color: var(--bg-dark);
        color: #ffffff;
        font-family: 'Outfit', sans-serif;
    }
    
    [data-testid="stSidebar"] {
        background-color: #0d0d0d;
        border-right: 1px solid rgba(0, 162, 255, 0.2);
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: transparent;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: var(--card-bg);
        border-radius: 8px 8px 0px 0px;
        color: #888;
        border: none;
        padding: 10px 20px;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: rgba(0, 162, 255, 0.1) !important;
        color: var(--primary) !important;
        border-bottom: 2px solid var(--primary) !important;
    }
    
    h1, h2, h3 {
        color: var(--primary) !important;
        font-weight: 600 !important;
    }
    
    .stButton>button {
        background-color: var(--primary);
        color: white;
        border-radius: 8px;
        border: none;
        box-shadow: 0 4px 15px rgba(0, 162, 255, 0.3);
    }
    
    /* Premium accents for numeric inputs and sliders */
    .stNumberInput, .stSlider {
        background: rgba(0, 162, 255, 0.05);
        border-radius: 8px;
        padding: 10px;
        border: 1px solid rgba(0, 162, 255, 0.1);
    }
    
    /* Fix for "circleds" and "fill" on sliders */
    .stSlider [role="slider"] {
        background-color: var(--primary) !important;
        border-color: var(--primary) !important;
    }
    .stSlider [data-baseweb="slider"] > div > div > div {
        background-color: var(--primary) !important;
    }
    .stSlider div[data-testid="stThumbValue"] {
        color: var(--primary) !important;
    }
    
    /* JSON block and metric values */
    .stJson span, [data-testid="stMetricValue"] {
        color: var(--primary) !important;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("SISP Unified Simulation: Geometry + PHY + Protocol Energy")
st.caption(
    "Merged app: geometry (LoS/Doppler), BER/PER, timing+energy, message energy attribution, KPI comparisons."
)

modulations = {
    "GMSK BT=0.3 (coherent, ISL control baseline)": ("GMSK_BT03", 1.0),
    "BPSK (coherent)": ("BPSK", 1.0),
    "QPSK (Gray, coherent)": ("QPSK", 2.0),
    "2-FSK (coherent, orthogonal)": ("2FSK_COH", 0.5),
    "2-FSK (noncoherent, orthogonal)": ("2FSK_NONCOH", 0.5),
}

coding_modes = {
    "None": "NONE",
    "Convolutional (R=1/2, ~7 dB gain model)": "CONV",
    "Conv + RS(255,223) (t=16)": "CONV_RS",
}

with st.sidebar:
    # Logo placement
    st.image("simulation for signal and physics/logo.png", width="stretch")
    st.markdown("---")
    st.header("Common Inputs")

    st.subheader("RF / Channel")
    f_hz = st.number_input("Carrier frequency (Hz)", min_value=1e6, max_value=100e9, value=437e6, step=1e6)

    channel_preset = st.selectbox("Channel bandwidth preset", ["12.5 kHz", "25 kHz", "Custom"], index=0)
    if channel_preset == "12.5 kHz":
        b_hz = 12_500.0
    elif channel_preset == "25 kHz":
        b_hz = 25_000.0
    else:
        b_hz = float(st.slider("Allocated bandwidth (Hz)", 5_000, 2_000_000, 12_500, 500))

    p_tx_dbm = st.slider("Tx RF power (dBm)", 10.0, 40.0, 30.0, 1.0)
    g_tx = st.slider("Tx antenna gain (dBi)", -2.0, 20.0, 2.0, 0.5)
    g_rx = st.slider("Rx antenna gain (dBi)", -2.0, 20.0, 2.0, 0.5)
    pointing_loss = st.slider("Pointing loss (dB)", 0.0, 5.0, 0.0, 0.5)
    misc_loss = st.slider("Other losses (dB)", 0.0, 10.0, 3.0, 0.5)

    st.subheader("Receiver noise")
    noise_mode = st.radio("Noise model", ["T_sys (K)", "Noise Figure (dB)"], index=1, horizontal=True)
    if noise_mode == "T_sys (K)":
        t_sys = st.slider("System temperature (K)", 150.0, 800.0, 290.0, 10.0)
    else:
        nf_db = st.slider("Receiver NF (dB)", 0.5, 15.0, 5.0, 0.5)
        t_ant = st.slider("Antenna noise temp (K)", 30.0, 300.0, 100.0, 10.0)
        t_sys = nf_to_tsys(nf_db, t_ant_k=t_ant)
        st.markdown(f"→ T_sys = **{t_sys:.1f} K**")

    st.subheader("Doppler / implementation margin")
    st.caption("Extra loss for frequency error from Doppler; ~1.5 dB for GMSK on 12.5 kHz ISL @ 437 MHz.")
    doppler_margin = st.slider("Doppler guard margin (dB)", 0.0, 5.0, 1.5, 0.5)

    st.subheader("Modem")
    modulation_label = st.selectbox("Modulation", list(modulations.keys()), index=0)
    modulation, spectral_eff = modulations[modulation_label]

    coding_label = st.selectbox("FEC", list(coding_modes.keys()), index=2)
    coding = coding_modes[coding_label]

    r_bps = float(b_hz) * float(spectral_eff)
    st.markdown(f"**Derived bit rate:** {fmt_si_rate(r_bps)}")

    st.subheader("DC power (energy)")
    p_tx_dc_w = st.slider("Tx DC power while transmitting (W)", 0.5, 30.0, 10.0, 0.5)
    p_rx_dc_w = st.slider("Rx DC power while receiving (W)", 0.1, 15.0, 2.5, 0.1)


(tab_geo, tab_phy, tab_energy, tab_msg, tab_kpi) = st.tabs(
    [
        "Geometry (LoS + Doppler)",
        "PHY (BER/PER)",
        "Timing & Energy",
        "Protocol Message Energy",
        "KPI Dashboard",
    ]
)


# =============================================================================
# Geometry tab
# =============================================================================

with tab_geo:
    st.subheader("Module M1: Spherical geometry (Earth blockage) + Doppler")

    if not _SKYFIELD_OK:
        st.error("Skyfield is not available in this environment. Install deps from simulation folder requirements.")
    else:
        with st.expander("TLE inputs", expanded=True):
            st.caption("Defaults are generic sample TLEs used for demo; replace with mission TLEs for real windows.")

            col1, col2 = st.columns(2)
            with col1:
                tle1_l1 = st.text_input(
                    "Sat A TLE line 1",
                    value="1 45176U 20001A   23274.50000000  .00000000  00000-0  00000-0 0  9998",
                )
                tle1_l2 = st.text_input(
                    "Sat A TLE line 2",
                    value="2 45176  53.0000 180.0000 0001000   0.0000   0.0000 15.00000000    05",
                )
            with col2:
                tle2_l1 = st.text_input(
                    "Sat B TLE line 1",
                    value="1 45177U 20001B   23274.50000000  .00000000  00000-0  00000-0 0  9999",
                )
                tle2_l2 = st.text_input(
                    "Sat B TLE line 2",
                    value="2 45177  53.0000 185.0000 0001000   0.0000   0.0000 15.00000000    04",
                )

            col3, col4, col5 = st.columns(3)
            with col3:
                start_year = st.number_input("Start year", 2020, 2035, 2026, 1)
                start_month = st.number_input("Start month", 1, 12, 4, 1)
                start_day = st.number_input("Start day", 1, 31, 19, 1)
                start_hour = st.number_input("Start hour (UTC)", 0, 23, 13, 1)
            with col4:
                duration_min = st.slider("Duration (minutes)", 10, 300, 90, 5)
                step_s = st.slider("Step (seconds)", 5, 120, 60, 5)
            with col5:
                r_earth_km = st.number_input("Earth radius (km)", 6300.0, 6400.0, 6371.0, 1.0)
                atm_clear_km = st.number_input("Atmosphere clearance (km)", 0.0, 500.0, 100.0, 10.0)

        # Time vector
        ts = load.timescale()
        n_steps = int(duration_min * 60 / step_s) + 1
        seconds = np.arange(n_steps) * int(step_s)
        # Use a simple UTC start and add seconds.
        t0 = ts.utc(int(start_year), int(start_month), int(start_day), int(start_hour), 0, 0)
        t = ts.tt_jd(t0.tt + seconds / 86400.0)

        sat_a = EarthSatellite(tle1_l1, tle1_l2, "Sat A", ts)
        sat_b = EarthSatellite(tle2_l1, tle2_l2, "Sat B", ts)

        state_a = sat_a.at(t)
        state_b = sat_b.at(t)

        pos_a = state_a.position.km
        pos_b = state_b.position.km
        vel_a = state_a.velocity.km_per_s
        vel_b = state_b.velocity.km_per_s

        r_excl = float(r_earth_km) + float(atm_clear_km)

        los_clear = []
        slant_km = []
        doppler_hz = []

        c_km_s = C_MPS / 1000.0

        for i in range(pos_a.shape[1]):
            rA = pos_a[:, i]
            rB = pos_b[:, i]
            vA = vel_a[:, i]
            vB = vel_b[:, i]

            rA_mag = float(np.linalg.norm(rA))
            rB_mag = float(np.linalg.norm(rB))
            dot_prod = float(np.dot(rA, rB) / (rA_mag * rB_mag))
            gamma = float(np.arccos(np.clip(dot_prod, -1.0, 1.0)))

            gamma_max = float(np.arccos(r_excl / rA_mag) + np.arccos(r_excl / rB_mag))
            ok = gamma < gamma_max

            d_vec = rB - rA
            d_mag = float(np.linalg.norm(d_vec))

            v_rel = vB - vA
            range_rate_km_s = float(np.dot(d_vec, v_rel) / max(d_mag, 1e-9))
            dop = float(f_hz) * (range_rate_km_s / c_km_s)

            los_clear.append(ok)
            slant_km.append(d_mag)
            doppler_hz.append(dop)

        los_clear = np.array(los_clear, dtype=bool)
        slant_km = np.array(slant_km, dtype=float)
        doppler_hz = np.array(doppler_hz, dtype=float)

        # Compute windows
        windows: List[Tuple[int, int]] = []
        in_win = False
        s_idx = 0
        for i, ok in enumerate(los_clear):
            if ok and not in_win:
                in_win = True
                s_idx = i
            if (not ok) and in_win:
                windows.append((s_idx, i - 1))
                in_win = False
        if in_win:
            windows.append((s_idx, len(los_clear) - 1))

        total_contact_s = float(np.sum(los_clear) * float(step_s))

        st.markdown("---")
        st.write(
            {
                "Samples": int(n_steps),
                "Total LoS time": f"{total_contact_s/60.0:.2f} min",
                "Windows": len(windows),
                "Min range": f"{slant_km.min():.1f} km",
                "Max range": f"{slant_km.max():.1f} km",
                "Max |Doppler|": f"{np.max(np.abs(doppler_hz))/1e3:.2f} kHz",
            }
        )

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
        x_min = seconds / 60.0
        ax1.plot(x_min, slant_km)
        ax1.set(ylabel="Slant range (km)")
        ax1.grid(True, ls="--", alpha=0.4)

        ax2.plot(x_min, doppler_hz / 1e3)
        ax2.set(xlabel="Time (min)", ylabel="Doppler (kHz)")
        ax2.grid(True, ls="--", alpha=0.4)

        # Shade non-LoS periods
        for ax in (ax1, ax2):
            ax.fill_between(x_min, ax.get_ylim()[0], ax.get_ylim()[1], where=~los_clear, color="#00a2ff", alpha=0.05)

        st.pyplot(fig)

        st.markdown("---")
        st.markdown("**LoS windows (start/end in minutes from start):**")
        if not windows:
            st.write("No LoS windows in this interval.")
        else:
            rows = []
            for (a, b) in windows:
                rows.append(
                    {
                        "Start (min)": float(seconds[a] / 60.0),
                        "End (min)": float(seconds[b] / 60.0),
                        "Duration (min)": float((seconds[b] - seconds[a] + step_s) / 60.0),
                        "Min range in window (km)": float(slant_km[a : b + 1].min()),
                        "Max |Doppler| in window (kHz)": float(np.max(np.abs(doppler_hz[a : b + 1])) / 1e3),
                    }
                )
            st.dataframe(rows, width="stretch")

        st.markdown("---")
        st.subheader("Optional: Sat-to-ground contact window")
        st.caption("Quick comparison KPI: how much time per orbit is available to talk to Earth.")

        colg1, colg2, colg3 = st.columns(3)
        with colg1:
            gs_lat = st.number_input("Ground station latitude (deg)", -90.0, 90.0, 0.0, 0.1)
            gs_lon = st.number_input("Ground station longitude (deg)", -180.0, 180.0, 0.0, 0.1)
        with colg2:
            min_el_deg = st.slider("Min elevation (deg)", 0.0, 30.0, 10.0, 0.5)
            use_sat = st.selectbox("Which satellite", ["Sat A", "Sat B"], index=0)
        with colg3:
            gs_alt_m = st.number_input("Ground station altitude (m)", -500.0, 5000.0, 0.0, 10.0)

        gs = wgs84.latlon(gs_lat, gs_lon, elevation_m=gs_alt_m)
        sat = sat_a if use_sat == "Sat A" else sat_b
        topocentric = (sat - gs).at(t)
        alt, az, distance = topocentric.altaz()

        elev = alt.degrees
        slant_gs_km = distance.km

        ok_gs = elev >= float(min_el_deg)
        total_gs_s = float(np.sum(ok_gs) * float(step_s))

        st.write(
            {
                "Total GS contact time": f"{total_gs_s/60.0:.2f} min",
                "Max elevation": f"{float(np.max(elev)):.1f} deg",
                "Min slant range": f"{float(np.min(slant_gs_km)):.1f} km",
            }
        )


# =============================================================================
# PHY tab
# =============================================================================

with tab_phy:
    st.subheader("Module M3: Physical layer (engineering BER/PER) and range")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**BER vs $E_b/N_0$**")
        ebn0_range = np.linspace(0, 20, 600)
        ber_none = ber_post_decoding(ebn0_range, modulation=modulation, coding="NONE")
        ber_conv = ber_post_decoding(ebn0_range, modulation=modulation, coding="CONV")
        ber_rs = ber_post_decoding(ebn0_range, modulation=modulation, coding="CONV_RS")

        fig1, ax1 = plt.subplots(figsize=(6, 4))
        ax1.semilogy(ebn0_range, ber_none, label="None")
        ax1.semilogy(ebn0_range, ber_conv, label="Conv")
        ax1.semilogy(ebn0_range, ber_rs, label="Conv+RS")
        ax1.set(ylim=(1e-12, 1), xlabel="Eb/N0 (dB)", ylabel="BER")
        ax1.grid(True, which="both", ls="--", alpha=0.4)
        ax1.legend()
        st.pyplot(fig1)

    with col_b:
        st.markdown("**PER vs distance (64B frame)**")
        d_min = st.number_input("Min distance (km)", min_value=10.0, max_value=20000.0, value=100.0, step=10.0)
        d_max = st.number_input("Max distance (km)", min_value=10.0, max_value=20000.0, value=5000.0, step=50.0)
        n_points = st.slider("Resolution", 100, 800, 400, 50)

        d_km = np.linspace(float(d_min), float(d_max), int(n_points))
        _, ebn0 = calc_link_budget(
            d_km=d_km,
            p_tx_dbm=p_tx_dbm,
            f_hz=float(f_hz),
            g_tx_dbi=g_tx,
            g_rx_dbi=g_rx,
            t_sys_k=t_sys,
            b_hz=float(b_hz),
            r_bps=r_bps,
            pointing_loss_db=pointing_loss,
            misc_loss_db=misc_loss,
            doppler_margin_db=doppler_margin,
        )

        ber = ber_post_decoding(ebn0, modulation=modulation, coding=coding)
        per = per_from_ber(ber, FRAME_BITS)
        per = np.clip(per, 1e-12, 1.0)

        fig2, ax2 = plt.subplots(figsize=(6, 4))
        ax2.semilogy(d_km, per)
        ax2.set(ylim=(1e-8, 1), xlabel="Distance (km)", ylabel="PER")
        ax2.grid(True, which="both", ls="--", alpha=0.4)
        st.pyplot(fig2)


# =============================================================================
# Timing & Energy tab (link-level analytic)
# =============================================================================

with tab_energy:
    st.subheader("Timing + energy: correction snapshot and bulk dump")

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("**Geometry / window**")
        los_window_min = st.slider("Visibility window (minutes)", 1.0, 60.0, 15.0, 1.0)

        st.markdown("**Bulk dump model**")
        dump_mb = st.slider("Dump size (MiB)", 0.01, 50.0, 1.0, 0.01)
        compression_ratio = st.slider("Compression ratio (original/compressed)", 1.0, 20.0, 3.0, 0.5)
        payload_per_frame_b = st.slider("Useful payload per 64B frame (bytes)", 10, 64, 45, 1)
        use_arq = st.checkbox("Assume ARQ retries per frame", value=True)

        st.markdown("**Emergency/bulk PHY override**")
        bulk_bw = st.selectbox("Bulk channel bandwidth", ["same as control", "25 kHz", "12.5 kHz", "Custom"], index=0)
        if bulk_bw == "same as control":
            b_bulk_hz = float(b_hz)
        elif bulk_bw == "25 kHz":
            b_bulk_hz = 25_000.0
        elif bulk_bw == "12.5 kHz":
            b_bulk_hz = 12_500.0
        else:
            b_bulk_hz = float(st.slider("Bulk bandwidth (Hz)", 5_000, 2_000_000, int(b_hz), 500))

        bulk_mod_label = st.selectbox("Bulk modulation", list(modulations.keys()), index=list(modulations.keys()).index(modulation_label))
        bulk_mod, bulk_eff = modulations[bulk_mod_label]
        bulk_coding_label = st.selectbox("Bulk FEC", list(coding_modes.keys()), index=list(coding_modes.keys()).index(coding_label))
        bulk_coding = coding_modes[bulk_coding_label]

        r_bps_bulk = float(b_bulk_hz) * float(bulk_eff)
        st.write({"Bulk derived bit rate": fmt_si_rate(r_bps_bulk)})

    with col_r:
        st.markdown("**Correction snapshot model**")
        n_neigh = st.slider("Neighbours responding", 0, 16, 8, 1)
        repeats = st.slider("Repetitions per frame", 1, 5, 1, 1)
        d_snapshot_km = st.slider("Range for timing/energy (km)", 10.0, 5000.0, 1000.0, 10.0)

    # Correction snapshot
    bits_per_frame_on_air_ctrl = FRAME_BITS * coding_expansion(coding)
    frame_time_ctrl_s = bits_per_frame_on_air_ctrl / max(r_bps, 1.0)
    prop_s = one_way_prop_delay_s(float(d_snapshot_km))

    snapshot_time_s = repeats * ((1 + n_neigh) * frame_time_ctrl_s) + 2.0 * prop_s

    e_req_tx_j = repeats * (1.0 * frame_time_ctrl_s) * p_tx_dc_w
    e_req_rx_neigh_total_j = repeats * (float(n_neigh) * frame_time_ctrl_s) * p_rx_dc_w
    e_rsp_tx_neigh_total_j = repeats * (float(n_neigh) * frame_time_ctrl_s) * p_tx_dc_w
    e_rsp_rx_requester_j = repeats * (float(n_neigh) * frame_time_ctrl_s) * p_rx_dc_w
    snapshot_energy_j = e_req_tx_j + e_req_rx_neigh_total_j + e_rsp_tx_neigh_total_j + e_rsp_rx_requester_j

    # Bulk dump
    dump_bytes = float(dump_mb) * 1024.0 * 1024.0
    dump_bytes_eff = dump_bytes / max(compression_ratio, 1.0)
    n_frames = int(math.ceil(dump_bytes_eff / max(payload_per_frame_b, 1)))

    bits_per_frame_on_air_bulk = FRAME_BITS * coding_expansion(bulk_coding)
    frame_time_bulk_s = bits_per_frame_on_air_bulk / max(r_bps_bulk, 1.0)

    # PER at range
    _, ebn0_at_d = calc_link_budget(
        d_km=np.array([float(d_snapshot_km)]),
        p_tx_dbm=p_tx_dbm,
        f_hz=float(f_hz),
        g_tx_dbi=g_tx,
        g_rx_dbi=g_rx,
        t_sys_k=t_sys,
        b_hz=float(b_bulk_hz),
        r_bps=r_bps_bulk,
        pointing_loss_db=pointing_loss,
        misc_loss_db=misc_loss,
        doppler_margin_db=doppler_margin,
    )
    ber_at_d = float(ber_post_decoding(ebn0_at_d, modulation=bulk_mod, coding=bulk_coding)[0])
    per_frame = float(per_from_ber(np.array([ber_at_d]), FRAME_BITS)[0])
    per_frame = min(max(per_frame, 0.0), 1.0)

    if use_arq:
        exp_tx_per_frame = 1.0 / max(1e-9, (1.0 - per_frame))
        exp_total_frames = n_frames * exp_tx_per_frame
        p_success_file = 1.0
    else:
        exp_total_frames = float(n_frames)
        p_success_file = (1.0 - per_frame) ** n_frames

    bulk_time_s = exp_total_frames * frame_time_bulk_s
    bulk_tx_energy_j = bulk_time_s * p_tx_dc_w
    bulk_rx_energy_j = bulk_time_s * p_rx_dc_w
    bulk_energy_j = bulk_tx_energy_j + bulk_rx_energy_j
    fits_los = bulk_time_s <= (float(los_window_min) * 60.0)

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Correction snapshot results**")
        st.write(
            {
                "Frame TX time": fmt_time_s(frame_time_ctrl_s),
                "One-way propagation": fmt_time_s(prop_s),
                "Total snapshot time": fmt_time_s(snapshot_time_s),
                "Requester TX (J)": round(e_req_tx_j, 3),
                "Requester RX (J)": round(e_rsp_rx_requester_j, 3),
                "Neighbours total RX (J)": round(e_req_rx_neigh_total_j, 3),
                "Neighbours total TX (J)": round(e_rsp_tx_neigh_total_j, 3),
                "Network total (J)": round(snapshot_energy_j, 3),
                "Meets 5 seconds": "YES" if snapshot_time_s <= 5.0 else "NO",
            }
        )

    with c2:
        st.markdown("**Bulk dump results (@ selected range)**")
        st.write(
            {
                "Compressed size": f"{dump_bytes_eff/1024.0:.1f} KiB",
                "Frames": n_frames,
                "Frame PER": f"{per_frame:.3e}",
                "Expected TX frames": f"{exp_total_frames:,.0f}",
                "Total time": fmt_time_s(bulk_time_s),
                "Fits LoS window": "YES" if fits_los else "NO",
                "TX energy": f"{bulk_tx_energy_j/3600.0:.3f} Wh ({bulk_tx_energy_j:.0f} J)",
                "RX energy": f"{bulk_rx_energy_j/3600.0:.3f} Wh ({bulk_rx_energy_j:.0f} J)",
                "Total energy": f"{bulk_energy_j/3600.0:.3f} Wh ({bulk_energy_j:.0f} J)",
                "One-shot success": f"{p_success_file:.3e}" if not use_arq else "(ARQ assumed)",
            }
        )


# =============================================================================
# Protocol message energy attribution tab
# =============================================================================

with tab_msg:
    st.subheader("Energy by SISP message/service type (percent breakdown)")
    st.caption(
        "Two modes: analytic (counts from protocol model) or measured (counts from C++ sisp.dll frame emissions). "
        "Measured mode lets you see which services dominate *attempted* transmissions; PHY loss is applied as an optional expected multiplier."
    )

    # Compute per-frame PER for current control PHY at a representative range
    d_rep_km = st.slider("Representative range for PER adjustment (km)", 10.0, 5000.0, 1000.0, 10.0, key="msg_d")
    _, ebn0_ctrl = calc_link_budget(
        d_km=np.array([float(d_rep_km)]),
        p_tx_dbm=p_tx_dbm,
        f_hz=float(f_hz),
        g_tx_dbi=g_tx,
        g_rx_dbi=g_rx,
        t_sys_k=t_sys,
        b_hz=float(b_hz),
        r_bps=r_bps,
        pointing_loss_db=pointing_loss,
        misc_loss_db=misc_loss,
        doppler_margin_db=doppler_margin,
    )
    ber_ctrl = float(ber_post_decoding(ebn0_ctrl, modulation=modulation, coding=coding)[0])
    per_ctrl = float(per_from_ber(np.array([ber_ctrl]), FRAME_BITS)[0])
    per_ctrl = min(max(per_ctrl, 0.0), 1.0)

    st.write({"Control PHY frame PER (@range)": f"{per_ctrl:.3e}"})

    use_expected = st.checkbox("Apply expected retry multiplier 1/(1-PER)", value=True)

    # Measured mode
    base_dir = os.path.dirname(os.path.dirname(__file__))
    default_dll = os.path.join(base_dir, "c++ implemnetation", "build", "bin", "Release", "sisp.dll")

    st.markdown("---")
    st.markdown("**Measured (C++ protocol) mode**")

    colm1, colm2, colm3 = st.columns(3)
    with colm1:
        dll_path = st.text_input("Path to sisp.dll", value=default_dll)
        scenario = st.selectbox(
            "Probe scenario",
            ["Correction (fault detected)", "Relay request (energy low)", "Failure broadcast (critical failure)"],
            index=0,
        )
    with colm2:
        num_sats = st.slider("Topology size", 2, 8, 5, 1)
        packet_loss_rate = st.slider("Simulated packet loss rate (routing layer)", 0.0, 0.5, 0.0, 0.01)
    with colm3:
        advance_total_ms = st.slider("Advance total time (ms)", 200, 20_000, 2_000, 200)
        tick_ms = st.selectbox("Tick (ms)", [50, 100, 200, 500, 1000], index=1)

    run_probe_btn = st.button("Run protocol probe")

    if run_probe_btn:
        try:
            events = run_protocol_probe(
                dll_path=dll_path,
                scenario=scenario,
                num_sats=int(num_sats),
                packet_loss_rate=float(packet_loss_rate),
                advance_total_ms=int(advance_total_ms),
                tick_ms=int(tick_ms),
                seed=12345,
            )
            if not events:
                st.warning("No frames captured. Try increasing advance time.")
            else:
                by_service, by_sat = energy_from_events(
                    events=events,
                    r_bps=r_bps,
                    coding=coding,
                    p_tx_dc_w=p_tx_dc_w,
                    p_rx_dc_w=p_rx_dc_w,
                    per_frame=per_ctrl,
                    use_expected_retries=use_expected,
                )

                rows = []
                total_j = sum(r["total_j"] for r in by_service.values())
                for svc, r in sorted(by_service.items(), key=lambda kv: kv[1]["total_j"], reverse=True):
                    rows.append(
                        {
                            "Service": svc,
                            "TX frames": r["tx_frames"],
                            "RX frames": r["rx_frames"],
                            "TX energy (J)": r["tx_j"],
                            "RX energy (J)": r["rx_j"],
                            "Total (J)": r["total_j"],
                            "%": (100.0 * r["total_j"] / max(1e-9, total_j)),
                        }
                    )

                st.dataframe(rows, width="stretch")

                # Dual-PHY profile breakdown (CTRL_NARROW vs BULK_WIDE)
                st.markdown("---")
                st.markdown("**Dual-PHY profile breakdown (frame[8] decoded)**")
                st.caption(
                    "CTRL_NARROW = CONTROL_437_NARROW (12.5 kHz, always-on control channel). "
                    "BULK_WIDE = BULK_437_WIDE (25 kHz, relay/borrow data channel). "
                    "State machine selects PHY per-frame based on service and peer capability."
                )
                phy_counts: Dict[str, int] = {"CTRL_NARROW (0x00)": 0, "BULK_WIDE (0x01)": 0, "Unknown": 0}
                for ev in events:
                    if ev.phy_profile == 0:
                        phy_counts["CTRL_NARROW (0x00)"] += 1
                    elif ev.phy_profile == 1:
                        phy_counts["BULK_WIDE (0x01)"] += 1
                    else:
                        phy_counts["Unknown"] += 1
                total_frames = max(sum(phy_counts.values()), 1)
                phy_rows = [
                    {"PHY": k, "Frames": v, "%": 100.0 * v / total_frames}
                    for k, v in phy_counts.items()
                ]
                st.dataframe(phy_rows, width="stretch")

                st.markdown("---")
                st.markdown("**Per-satellite energy (this probe)**")
                sat_rows = []
                for sid, r in sorted(by_sat.items(), key=lambda kv: kv[0]):
                    sat_rows.append(
                        {
                            "Sat": int(sid),
                            "TX frames": r["tx_frames"],
                            "RX frames": r["rx_frames"],
                            "TX (J)": r["tx_j"],
                            "RX (J)": r["rx_j"],
                            "Total (J)": r["total_j"],
                        }
                    )
                st.dataframe(sat_rows, width="stretch")

                st.markdown("---")
                st.write(
                    {
                        "Captured TX events": len(events),
                        "Total energy (network, J)": round(total_j, 3),
                        "Total energy (network, Wh)": round(total_j / 3600.0, 6),
                        "Assumed frame time": fmt_time_s((FRAME_BITS * coding_expansion(coding)) / max(r_bps, 1.0)),
                    }
                )

        except Exception as e:
            st.error(str(e))

    st.markdown("---")
    st.markdown("**Analytic mode (quick planning)**")
    st.caption("Use this if you want a clean, controllable daily message mix without running the DLL.")

    cola1, cola2, cola3 = st.columns(3)
    with cola1:
        daily_corrections = st.slider("Corrections/day", 0, 200, 24, 1)
        neigh = st.slider("Neighbours per correction", 0, 16, 8, 1)
    with cola2:
        daily_failures = st.slider("Failures/day (broadcast)", 0, 50, 0, 1)
        hb_per_hour = st.slider("Heartbeats/hour", 0, 120, 12, 1)
    with cola3:
        relay_ops = st.slider("Relay ops/day", 0, 200, 0, 1)
        relay_data_frames = st.slider("Relay data frames/op", 0, 10000, 0, 10)

    # Analytic frame counts (first-order)
    frames_by_svc = {
        "CORRECTION_REQ": float(daily_corrections),
        "CORRECTION_RSP": float(daily_corrections) * float(neigh),
        "FAILURE": float(daily_failures),
        "HEARTBEAT": float(hb_per_hour) * 24.0,
        "RELAY_REQ": float(relay_ops),
        "RELAY_ACCEPT": float(relay_ops),
        "RELAY_DATA": float(relay_ops) * float(relay_data_frames),
        "DOWNLINK_ACK": 0.0,
    }

    exp_mult = 1.0 / max(1e-9, (1.0 - per_ctrl)) if use_expected else 1.0
    bits_on_air = FRAME_BITS * coding_expansion(coding)
    t_frame = bits_on_air / max(r_bps, 1.0)

    rows = []
    total_j = 0.0
    for svc, n_tx in frames_by_svc.items():
        n_tx_eff = n_tx * exp_mult
        # For analytic mode, assume 1 receiver per unicast frame and (neigh) receivers for broadcasts.
        rx_mult = 1.0
        if svc == "FAILURE":
            rx_mult = float(neigh) if neigh > 0 else 1.0
        if svc == "HEARTBEAT":
            rx_mult = float(neigh) if neigh > 0 else 1.0
        if svc == "CORRECTION_RSP":
            rx_mult = 1.0  # responses go to requester
        if svc == "CORRECTION_REQ":
            rx_mult = float(neigh) if neigh > 0 else 1.0

        tx_j = n_tx_eff * t_frame * p_tx_dc_w
        rx_j = (n_tx_eff * rx_mult) * t_frame * p_rx_dc_w
        tot_j = tx_j + rx_j
        total_j += tot_j
        rows.append({"Service": svc, "TX frames": n_tx_eff, "RX frames": n_tx_eff * rx_mult, "Total (J)": tot_j})

    if total_j > 0:
        for r in rows:
            r["%"] = 100.0 * r["Total (J)"] / total_j

    st.dataframe(sorted(rows, key=lambda r: r["Total (J)"], reverse=True), width="stretch")
    st.write({"Total comms energy/day (Wh)": round(total_j / 3600.0, 6)})


# =============================================================================
# KPI dashboard tab
# =============================================================================

with tab_kpi:
    st.subheader("Business KPIs: energy per data, contact time, ISL vs ground")

    st.markdown("**Spacecraft energy budget (for % metrics)**")
    colk1, colk2, colk3 = st.columns(3)
    with colk1:
        battery_wh = st.number_input("Battery capacity (Wh)", 1.0, 5000.0, 100.0, 1.0)
    with colk2:
        daily_gen_wh = st.number_input("Energy generated per day (Wh)", 0.0, 10000.0, 300.0, 10.0)
    with colk3:
        noncomms_wh = st.number_input("Non-comms energy per day (Wh)", 0.0, 10000.0, 200.0, 10.0)

    st.markdown("---")
    st.markdown("**KPI 1: Energy per MiB over ISL (from bulk model)**")

    dump_mib = st.slider("Data volume (MiB)", 0.01, 50.0, 1.0, 0.01, key="kpi_dump")
    comp = st.slider("Compression ratio", 1.0, 20.0, 3.0, 0.5, key="kpi_comp")
    payload_b = st.slider("Useful payload (B/frame)", 10, 64, 45, 1, key="kpi_payload")
    range_km = st.slider("Range for PER", 10.0, 5000.0, 1000.0, 10.0, key="kpi_range")

    dump_bytes = float(dump_mib) * 1024.0 * 1024.0
    eff_bytes = dump_bytes / max(comp, 1.0)
    frames = int(math.ceil(eff_bytes / max(payload_b, 1)))

    bits_on_air = FRAME_BITS * coding_expansion(coding)
    t_frame = bits_on_air / max(r_bps, 1.0)

    _, ebn0 = calc_link_budget(
        d_km=np.array([float(range_km)]),
        p_tx_dbm=p_tx_dbm,
        f_hz=float(f_hz),
        g_tx_dbi=g_tx,
        g_rx_dbi=g_rx,
        t_sys_k=t_sys,
        b_hz=float(b_hz),
        r_bps=r_bps,
        pointing_loss_db=pointing_loss,
        misc_loss_db=misc_loss,
        doppler_margin_db=doppler_margin,
    )
    ber = float(ber_post_decoding(ebn0, modulation=modulation, coding=coding)[0])
    per = float(per_from_ber(np.array([ber]), FRAME_BITS)[0])
    per = min(max(per, 0.0), 1.0)

    exp_mult = 1.0 / max(1e-9, (1.0 - per))
    t_total = float(frames) * exp_mult * t_frame

    tx_j = t_total * p_tx_dc_w
    rx_j = t_total * p_rx_dc_w
    total_j = tx_j + rx_j

    mib_delivered = eff_bytes / (1024.0 * 1024.0)

    st.write(
        {
            "Frames": frames,
            "Frame PER": f"{per:.3e}",
            "Total time": fmt_time_s(t_total),
            "Energy (TX+RX)": f"{total_j/3600.0:.3f} Wh",
            "Energy per delivered MiB": f"{(total_j/3600.0)/max(mib_delivered, 1e-9):.3f} Wh/MiB",
        }
    )

    st.markdown("---")
    st.markdown("**KPI 2: Ground-link comparison (spacecraft energy only)**")
    st.caption("Ground receiver energy is not part of spacecraft budget; comparison focuses on spacecraft-side TX energy.")

    colg1, colg2, colg3 = st.columns(3)
    with colg1:
        ground_f = st.selectbox("Downlink band", ["UHF (437 MHz)", "Ka (26 GHz)", "Custom"], index=0)
        if ground_f == "UHF (437 MHz)":
            f_g = 437e6
        elif ground_f == "Ka (26 GHz)":
            f_g = 26e9
        else:
            f_g = st.number_input("Ground link carrier (Hz)", 1e6, 100e9, 2.2e9, 1e6)

    with colg2:
        g_tx_g = st.slider("Spacecraft Tx gain (dBi)", -2.0, 40.0, 2.0, 0.5, key="g_tx_g")
        g_rx_g = st.slider("Ground Rx gain (dBi)", 0.0, 70.0, 20.0, 0.5, key="g_rx_g")

    with colg3:
        b_g = st.selectbox("Ground channel bandwidth", ["12.5 kHz", "25 kHz", "100 kHz", "Custom"], index=2)
        if b_g == "12.5 kHz":
            b_g_hz = 12_500.0
        elif b_g == "25 kHz":
            b_g_hz = 25_000.0
        elif b_g == "100 kHz":
            b_g_hz = 100_000.0
        else:
            b_g_hz = float(st.slider("Ground bandwidth (Hz)", 5_000, 5_000_000, 100_000, 10_000, key="b_g_hz"))

    eff = spectral_eff
    r_g = float(b_g_hz) * float(eff)

    # Ground link range proxy: 500..2500 km
    d_g = st.slider("Ground slant range proxy (km)", 200.0, 5000.0, 1200.0, 50.0)

    _, ebn0_g = calc_link_budget(
        d_km=np.array([float(d_g)]),
        p_tx_dbm=p_tx_dbm,
        f_hz=float(f_g),
        g_tx_dbi=float(g_tx_g),
        g_rx_dbi=float(g_rx_g),
        t_sys_k=t_sys,
        b_hz=float(b_g_hz),
        r_bps=float(r_g),
        pointing_loss_db=pointing_loss,
        misc_loss_db=misc_loss,
        doppler_margin_db=0.0,  # ground link: no ISL Doppler constraint
    )

    ber_g = float(ber_post_decoding(ebn0_g, modulation=modulation, coding=coding)[0])
    per_g = float(per_from_ber(np.array([ber_g]), FRAME_BITS)[0])
    per_g = min(max(per_g, 0.0), 1.0)

    bits_on_air_g = FRAME_BITS * coding_expansion(coding)
    t_frame_g = bits_on_air_g / max(r_g, 1.0)
    exp_mult_g = 1.0 / max(1e-9, (1.0 - per_g))

    t_total_g = float(frames) * exp_mult_g * t_frame_g
    tx_j_g = t_total_g * p_tx_dc_w

    st.write(
        {
            "Ground derived bit rate": fmt_si_rate(r_g),
            "Frame PER": f"{per_g:.3e}",
            "Spacecraft TX energy": f"{tx_j_g/3600.0:.3f} Wh",
            "Spacecraft TX Wh/MiB": f"{(tx_j_g/3600.0)/max(mib_delivered, 1e-9):.3f} Wh/MiB",
        }
    )

    st.markdown("---")
    st.markdown("**KPI 3: % of daily energy spent on comms**")
    comms_wh = total_j / 3600.0
    pct_of_gen = 100.0 * comms_wh / max(daily_gen_wh, 1e-9)
    pct_of_batt = 100.0 * comms_wh / max(battery_wh, 1e-9)

    st.write(
        {
            "Comms energy (Wh)": round(comms_wh, 6),
            "% of daily generation": f"{pct_of_gen:.2f}%",
            "% of battery": f"{pct_of_batt:.2f}%",
            "Energy margin (Wh/day)": round(daily_gen_wh - noncomms_wh - comms_wh, 3),
        }
    )
