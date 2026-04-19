import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from scipy.special import erfc, comb

# --- Core Mathematical Models ---
def calc_ber_uncoded(ebn0_db):
    ebn0_lin = 10**(ebn0_db / 10)
    return 0.5 * erfc(np.sqrt(ebn0_lin))

def calc_ber_conv(ebn0_db):
    # Rate 1/2, K=7, d_free = 10
    ebn0_lin = 10**(ebn0_db / 10)
    return 0.5 * erfc(np.sqrt(5 * ebn0_lin))

def calc_ber_concatenated(ebn0_db):
    ber_c = calc_ber_conv(ebn0_db)
    p_byte = 1 - (1 - ber_c)**8 # Byte error rate into RS decoder
    
    # RS(255, 223) error correction bound (t=16)
    p_rs = np.zeros_like(p_byte)
    for i in range(len(p_byte)):
        if p_byte[i] > 1e-10:
            p_rs[i] = comb(255, 17) * (p_byte[i]**17) * ((1 - p_byte[i])**238)
        else:
            p_rs[i] = 0.0
    return p_rs / 2 # Approx bit error rate

def calc_link_budget(d_km, p_tx_dbm, f_c_ghz, g_tx, g_rx, t_sys, b_hz, rb_bps):
    c = 3e8
    f_c_hz = f_c_ghz * 1e9
    d_m = d_km * 1000
    
    l_fs_db = 20 * np.log10(d_m) + 20 * np.log10(f_c_hz) + 20 * np.log10(4 * np.pi / c)
    l_point_db = 2.0
    n_w = 1.38e-23 * t_sys * b_hz
    n_dbm = 10 * np.log10(n_w) + 30
    
    snr_db = p_tx_dbm + g_tx + g_rx - l_fs_db - l_point_db - n_dbm
    ebn0_db = snr_db + 10 * np.log10(b_hz / rb_bps)
    return snr_db, ebn0_db

def calc_per(ber, uncoded_bits):
    coded_bits = int(uncoded_bits * 2.29) # Conv + RS overhead
    return 1 - (1 - ber)**coded_bits

# --- Streamlit UI Setup ---
st.set_page_config(page_title="SISP Signal Simulation", layout="wide")
st.title("SISP Module M3: Physical Layer (Production Sizes)")

# Production Packet Sizes (Uncoded Bits)
packets = {
    "CORRECTION_REQ (8B)": 64,
    "CORRECTION_RSP (22B)": 176,
    "Fixed Simulator Frame (64B)": 512
}

tab1, tab2, tab3 = st.tabs(["Plot 1: BER Curves", "Plot 2: Distance Range", "Plot 3: PER vs Range"])

with tab1:
    st.header("Coding Gain Analysis")
    ebn0_range = np.linspace(0, 14, 500)
    fig1, ax1 = plt.subplots(figsize=(10, 5))
    ax1.semilogy(ebn0_range, calc_ber_uncoded(ebn0_range), label='Uncoded BPSK')
    ax1.semilogy(ebn0_range, calc_ber_concatenated(ebn0_range), label='Concatenated (Conv+RS)')
    ax1.axhline(y=1e-6, color='red', linestyle='--', label='Target BER (10^-6)')
    ax1.set(ylim=(1e-12, 1), xlabel='Eb/N0 (dB)', ylabel='BER')
    ax1.grid(True, which="both", ls="--")
    ax1.legend()
    st.pyplot(fig1)

with tab2:
    st.header("Link Budget & Maximum Range")
    p_tx = st.slider("Tx Power (dBm)", 20.0, 40.0, 30.0)
    d_range = np.logspace(2, 5, 500)
    _, ebn0_ka = calc_link_budget(d_range, p_tx, 26.0, 10, 10, 280, 1e5, 1e5)
    fig2, ax2 = plt.subplots(figsize=(10, 5))
    ax2.semilogx(d_range, ebn0_ka, label='Ka-Band (26 GHz)')
    ax2.axhline(y=4.5, color='green', linestyle='--', label='Min Viable (4.5 dB)')
    ax2.set(xlabel='Distance (km)', ylabel='Received Eb/N0 (dB)')
    ax2.grid(True, which="both", ls="--")
    ax2.legend()
    st.pyplot(fig2)

with tab3:
    st.header("Packet Error Rate (64-Byte Frame Constraint)")
    d_range_per = np.linspace(100, 100000, 500)
    _, ebn0_per = calc_link_budget(d_range_per, p_tx, 26.0, 10, 10, 280, 1e5, 1e5)
    ber_for_per = calc_ber_concatenated(ebn0_per)
    
    fig3, ax3 = plt.subplots(figsize=(10, 5))
    for name, bits in packets.items():
        ax3.semilogy(d_range_per, calc_per(ber_for_per, bits), label=f'{name} (~{int(bits*2.29)} coded bits)')
    
    ax3.axhline(y=1e-4, color='black', linestyle='--', label='Target Max PER (10^-4)')
    ax3.set(ylim=(1e-6, 1), xlim=(10000, 100000), xlabel='Distance (km)', ylabel='PER')
    ax3.grid(True, which="both", ls="--")
    ax3.legend()
    st.pyplot(fig3)