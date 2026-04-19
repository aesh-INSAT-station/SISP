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
    # Byte error rate into RS decoder
    p_byte = 1 - (1 - ber_c)**8
    
    # RS(255, 223) error correction bound (t=16)
    # Using the tight approximation for residual byte error rate
    p_rs = np.zeros_like(p_byte)
    for i in range(len(p_byte)):
        if p_byte[i] > 1e-10:
            # Prevent overflow/underflow in comb
            p_rs[i] = comb(255, 17) * (p_byte[i]**17) * ((1 - p_byte[i])**238)
        else:
            p_rs[i] = 0.0
            
    # Convert residual byte error rate roughly back to bit error rate
    # For RS, a byte error usually contains ~4 bit errors
    return p_rs / 2 

def calc_link_budget(d_km, p_tx_dbm, f_c_ghz, g_tx, g_rx, t_sys, b_hz, rb_bps):
    p_tx_w = 10**((p_tx_dbm - 30) / 10)
    c = 3e8
    f_c_hz = f_c_ghz * 1e9
    d_m = d_km * 1000
    
    # Friis Path Loss
    l_fs_db = 20 * np.log10(d_m) + 20 * np.log10(f_c_hz) + 20 * np.log10(4 * np.pi / c)
    l_point_db = 2.0
    
    # Noise Power
    k_b = 1.38e-23
    n_w = k_b * t_sys * b_hz
    n_dbm = 10 * np.log10(n_w) + 30
    
    # SNR and Eb/N0
    snr_db = p_tx_dbm + g_tx + g_rx - l_fs_db - l_point_db - n_dbm
    ebn0_db = snr_db + 10 * np.log10(b_hz / rb_bps)
    
    return snr_db, ebn0_db

def calc_per(ber, packet_bits):
    return 1 - (1 - ber)**packet_bits

# --- Streamlit UI Setup ---

st.set_page_config(page_title="SISP Physical Layer Simulation", layout="wide")
st.title("SISP Physical Layer — Link & Error Simulation")
st.markdown("Module M3 Deliverables: Interactive BER/PER and Link Budget Analysis")

# Define SISP Packet Sizes (Coded Bits)
packets = {
    "Header Only": 92,
    "CORRECTION_REQ/RSP": 311,
    "RELAY_REQ": 1924,
    "BORROW_DATA": 18852
}

tab1, tab2, tab3 = st.tabs(["Plot 1: BER vs Eb/N0", "Plot 2: SNR vs Distance", "Plot 3: PER vs Distance"])

# --- TAB 1: BER Curves ---
with tab1:
    st.header("BER Analysis — Coding Regimes")
    
    ebn0_range = np.linspace(0, 14, 500)
    ber_u = calc_ber_uncoded(ebn0_range)
    ber_c = calc_ber_conv(ebn0_range)
    ber_concat = calc_ber_concatenated(ebn0_range)
    
    fig1, ax1 = plt.subplots(figsize=(10, 6))
    ax1.semilogy(ebn0_range, ber_u, label='Uncoded BPSK', color='blue', linewidth=2)
    ax1.semilogy(ebn0_range, ber_c, label='Rate-1/2 Conv (K=7)', color='orange', linewidth=2)
    ax1.semilogy(ebn0_range, ber_concat, label='Concatenated (Conv + RS)', color='green', linewidth=2)
    
    ax1.axhline(y=1e-6, color='red', linestyle='--', label='Target BER (10^-6)')
    
    ax1.set_ylim(1e-12, 1)
    ax1.set_xlim(0, 14)
    ax1.set_xlabel('Eb/N0 (dB)')
    ax1.set_ylabel('Bit Error Rate (BER)')
    ax1.set_title('BER vs Eb/N0 for SISP Physical Layer')
    ax1.grid(True, which="both", ls="--", alpha=0.5)
    ax1.legend()
    
    st.pyplot(fig1)
    st.markdown("**Insight:** The horizontal gap at BER 10^-6 demonstrates the ~7 dB coding gain achieved by the concatenated scheme.")

# --- TAB 2: SNR vs Distance ---
with tab2:
    st.header("Maximum Service Range & Link Budget")
    
    col1, col2 = st.columns([1, 3])
    with col1:
        p_tx = st.slider("Tx Power (dBm)", min_value=20.0, max_value=40.0, value=30.0, step=1.0)
        d_max_plot = st.number_input("Max Distance to Plot (km)", value=100000, step=10000)
    
    d_range = np.logspace(2, np.log10(d_max_plot), 500) # 100 km to max
    
    # Ka-Band
    _, ebn0_ka = calc_link_budget(d_range, p_tx, f_c_ghz=26.0, g_tx=10, g_rx=10, t_sys=280, b_hz=1e5, rb_bps=1e5)
    # UHF Comparison
    _, ebn0_uhf = calc_link_budget(d_range, p_tx, f_c_ghz=0.437, g_tx=2, g_rx=2, t_sys=280, b_hz=1e5, rb_bps=1e5)
    
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    ax2.semilogx(d_range, ebn0_ka, label='Ka-Band (26 GHz, 10 dBi antennas)', color='blue', linewidth=2)
    ax2.semilogx(d_range, ebn0_uhf, label='UHF (437 MHz, 2 dBi antennas)', color='purple', linestyle='-.', linewidth=2)
    
    ax2.axhline(y=4.5, color='green', linestyle='--', label='Min Viable Eb/N0 (4.5 dB - Coded)')
    ax2.axhline(y=8.0, color='red', linestyle='--', label='Min Viable Eb/N0 (8.0 dB - Uncoded)')
    
    ax2.set_xlabel('Distance (km) - Log Scale')
    ax2.set_ylabel('Received Eb/N0 (dB)')
    ax2.set_title(f'Link Budget vs Range (Tx Power: {p_tx} dBm)')
    ax2.grid(True, which="both", ls="--", alpha=0.5)
    ax2.legend()
    
    st.pyplot(fig2)

# --- TAB 3: PER vs Distance ---
with tab3:
    st.header("Packet Error Rate (PER) vs Distance")
    
    col3, col4 = st.columns([1, 3])
    with col3:
        msg_type_1 = st.selectbox("Message Type 1", list(packets.keys()), index=1)
        msg_type_2 = st.selectbox("Message Type 2", list(packets.keys()), index=3)
        p_tx_per = st.slider("Tx Power for PER (dBm)", min_value=20.0, max_value=40.0, value=30.0, step=1.0, key='ptx_per')
    
    d_range_per = np.linspace(100, 100000, 1000)
    _, ebn0_per = calc_link_budget(d_range_per, p_tx_per, f_c_ghz=26.0, g_tx=10, g_rx=10, t_sys=280, b_hz=1e5, rb_bps=1e5)
    
    ber_for_per = calc_ber_concatenated(ebn0_per)
    per_1 = calc_per(ber_for_per, packets[msg_type_1])
    per_2 = calc_per(ber_for_per, packets[msg_type_2])
    
    fig3, ax3 = plt.subplots(figsize=(10, 6))
    ax3.semilogy(d_range_per, per_1, label=f'{msg_type_1} ({packets[msg_type_1]} bits)', color='blue', linewidth=2)
    ax3.semilogy(d_range_per, per_2, label=f'{msg_type_2} ({packets[msg_type_2]} bits)', color='red', linewidth=2)
    
    ax3.axhline(y=1e-4, color='black', linestyle='--', label='PER Threshold (10^-4)')
    
    ax3.set_ylim(1e-6, 1)
    ax3.set_xlim(10000, 100000)
    ax3.set_xlabel('Distance (km)')
    ax3.set_ylabel('Packet Error Rate (PER)')
    ax3.set_title('Concatenated Code PER vs Distance')
    ax3.grid(True, which="both", ls="--", alpha=0.5)
    ax3.legend()
    
    st.pyplot(fig3)
    st.markdown("**Insight:** Larger payloads degrade significantly faster over distance. This crossover directly justifies the architectural need for the RELAY service.")