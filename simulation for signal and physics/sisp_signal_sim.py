import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from scipy.special import erfc
from scipy.stats import binom

# --- Constants ---
C_MPS = 299_792_458.0
K_B = 1.380649e-23

R_CONV = 0.5
R_RS = 223 / 255
R_TOTAL = R_CONV * R_RS
CODE_EXPANSION = 1.0 / R_TOTAL  # ~= 2.2857

FRAME_BITS = 64 * 8

# --- Core Mathematical Models ---
def calc_ber_uncoded(ebn0_db):
    ebn0_lin = 10**(ebn0_db / 10)
    return 0.5 * erfc(np.sqrt(ebn0_lin))

def calc_ber_conv(ebn0_db):
    # Rate 1/2, K=7, d_free = 10
    ebn0_lin = 10**(ebn0_db / 10)
    return 0.5 * erfc(np.sqrt(5 * ebn0_lin))

def calc_ber_concatenated(ebn0_db):
    """Approximate post-decoding BER for concatenated conv + RS.

    This uses a simple engineering model:
    - Treat convolutional post-Viterbi BER as i.i.d. bit errors.
    - Convert to byte-error probability.
    - Compute RS(255,223), t=16 decode *failure* probability exactly via binomial tail.
    - If RS fails, decoded bits are assumed random -> BER ~= 0.5; else ~0.

    The key property: at low Eb/N0 this saturates to BER ~ 0.5 (not “perfect”).
    """
    ber_conv = calc_ber_conv(ebn0_db)
    p_byte = 1.0 - (1.0 - ber_conv) ** 8
    p_fail = binom.sf(16, 255, p_byte)  # P(N_errors > 16)
    return 0.5 * p_fail

def calc_link_budget(d_km, p_tx_dbm, f_c_ghz, g_tx, g_rx, t_sys, b_hz, rb_bps):
    c = C_MPS
    f_c_hz = f_c_ghz * 1e9
    d_m = d_km * 1000
    
    l_fs_db = 20 * np.log10(d_m) + 20 * np.log10(f_c_hz) + 20 * np.log10(4 * np.pi / c)
    l_point_db = 2.0
    n_w = K_B * t_sys * b_hz
    n_dbm = 10 * np.log10(n_w) + 30
    
    snr_db = p_tx_dbm + g_tx + g_rx - l_fs_db - l_point_db - n_dbm
    ebn0_db = snr_db + 10 * np.log10(b_hz / rb_bps)
    return snr_db, ebn0_db

def calc_per_from_post_ber(ber_post, info_bits):
    """Packet error probability from post-decoding BER assuming i.i.d. bit errors."""
    ber_post = np.clip(ber_post, 0.0, 1.0)
    return 1.0 - np.exp(info_bits * np.log1p(-ber_post))

# --- Streamlit UI Setup ---
st.set_page_config(page_title="SISP Signal Simulation", layout="wide")
st.title("SISP Module M3: Physical Layer (Production Sizes)")

# Production Packet Sizes (Uncoded Bits)
packets = {
    "CORRECTION_REQ (8B)": 64,
    "CORRECTION_RSP (22B)": 176,
    "Fixed Simulator Frame (64B)": FRAME_BITS
}

tab1, tab2, tab3 = st.tabs(["Plot 1: BER Curves", "Plot 2: Distance Range", "Plot 3: PER vs Range"])

with tab1:
    st.header("Coding Gain Analysis")
    ebn0_range = np.linspace(0, 20, 600)
    fig1, ax1 = plt.subplots(figsize=(10, 5))
    ax1.semilogy(ebn0_range, calc_ber_uncoded(ebn0_range), label='Uncoded BPSK')
    ax1.semilogy(ebn0_range, calc_ber_conv(ebn0_range), label='Conv (K=7, R=1/2)')
    ax1.semilogy(ebn0_range, calc_ber_concatenated(ebn0_range), label='Concatenated (Conv+RS)')
    ax1.axhline(y=1e-6, color='red', linestyle='--', label='Target BER (10^-6)')
    ax1.set(ylim=(1e-12, 1), xlabel='Eb/N0 (dB)', ylabel='BER')
    ax1.grid(True, which="both", ls="--")
    ax1.legend()
    st.pyplot(fig1)

with tab2:
    st.header("Link Budget & Maximum Range")
    p_tx = st.slider("Tx Power (dBm)", 20.0, 40.0, 30.0)
    g_dbi = st.slider("Antenna Gain (dBi) — Tx and Rx", 0.0, 35.0, 23.0)
    d_range = np.logspace(2, 5, 500)
    _, ebn0_ka = calc_link_budget(d_range, p_tx, 26.0, g_dbi, g_dbi, 280, 1e5, 1e5)
    fig2, ax2 = plt.subplots(figsize=(10, 5))
    ax2.semilogx(d_range, ebn0_ka, label=f'Ka-Band (26 GHz, Gtx=Grx={g_dbi:.1f} dBi)')
    ax2.axhline(y=4.5, color='green', linestyle='--', label='Min Viable (4.5 dB)')
    ax2.set(xlabel='Distance (km)', ylabel='Received Eb/N0 (dB)')
    ax2.grid(True, which="both", ls="--")
    ax2.legend()
    st.pyplot(fig2)

with tab3:
    st.header("Packet Error Rate (64-Byte Frame Constraint)")
    st.caption("Note: the C++ transport uses a fixed 64-byte frame and validates a checksum over the full frame; the 64B curve is the protocol-relevant drop probability per transmission.")
    d_range_per = np.linspace(100, 100000, 500)
    _, ebn0_per = calc_link_budget(d_range_per, p_tx, 26.0, g_dbi, g_dbi, 280, 1e5, 1e5)
    ber_for_per = calc_ber_concatenated(ebn0_per)
    
    fig3, ax3 = plt.subplots(figsize=(10, 5))
    for name, bits in packets.items():
        per = calc_per_from_post_ber(ber_for_per, bits)
        ax3.semilogy(d_range_per, per, label=f'{name} (~{int(bits*CODE_EXPANSION)} coded bits on-air)')
    
    ax3.axhline(y=1e-4, color='black', linestyle='--', label='Target Max PER (10^-4)')
    ax3.set(ylim=(1e-6, 1), xlim=(10000, 100000), xlabel='Distance (km)', ylabel='PER')
    ax3.grid(True, which="both", ls="--")
    ax3.legend()
    st.pyplot(fig3)