import math

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from scipy.special import erfc
from scipy.stats import binom

# --- Constants ---
C_MPS = 299_792_458.0
K_B = 1.380649e-23

FRAME_BYTES = 64
FRAME_BITS = FRAME_BYTES * 8

# Coding parameters (kept consistent with sisp_signal_sim.py)
R_CONV = 0.5
R_RS = 223.0 / 255.0
R_TOTAL = R_CONV * R_RS

CONV_GAIN_DB = 10.0 * math.log10(5.0)  # ~7.0 dB (matches existing conv model)


# --- Math helpers ---

def qfunc(x: np.ndarray) -> np.ndarray:
    return 0.5 * erfc(x / np.sqrt(2.0))


def ber_uncoded_awgn(ebn0_db: np.ndarray, modulation: str) -> np.ndarray:
    """Simple coherent AWGN BER models.

    Notes:
    - BPSK and Gray-coded QPSK have identical BER vs Eb/N0.
    - 2-FSK models are for orthogonal signaling.

    This is an engineering study tool, not a standards-accurate modem model.
    """
    ebn0_lin = 10.0 ** (ebn0_db / 10.0)

    if modulation in ("BPSK", "QPSK"):
        # Pb = Q(sqrt(2*Eb/N0)) = 0.5*erfc(sqrt(Eb/N0))
        return 0.5 * erfc(np.sqrt(ebn0_lin))

    if modulation == "2FSK_COH":
        # Coherent orthogonal BFSK: Pb = Q(sqrt(Eb/N0))
        return qfunc(np.sqrt(ebn0_lin))

    if modulation == "2FSK_NONCOH":
        # Noncoherent orthogonal BFSK: Pb = 0.5 * exp(-Eb/(2N0))
        return 0.5 * np.exp(-0.5 * ebn0_lin)

    raise ValueError(f"Unknown modulation: {modulation}")


def ber_post_decoding(ebn0_db: np.ndarray, modulation: str, coding: str) -> np.ndarray:
    if coding == "NONE":
        return ber_uncoded_awgn(ebn0_db, modulation)

    if coding == "CONV":
        # Approximate coding gain as a constant Eb/N0 offset.
        return ber_uncoded_awgn(ebn0_db + CONV_GAIN_DB, modulation)

    if coding == "CONV_RS":
        # Reuse the same engineering model used in sisp_signal_sim.py.
        ber_conv = ber_uncoded_awgn(ebn0_db + CONV_GAIN_DB, modulation)
        p_byte = 1.0 - (1.0 - ber_conv) ** 8
        p_fail = binom.sf(16, 255, p_byte)  # P(byte_errors > 16)
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
) -> tuple[np.ndarray, np.ndarray]:
    d_m = d_km * 1000.0
    l_fs_db = 20.0 * np.log10(d_m) + 20.0 * np.log10(f_hz) + 20.0 * np.log10(4.0 * np.pi / C_MPS)

    n_w = K_B * t_sys_k * b_hz
    n_dbm = 10.0 * np.log10(n_w) + 30.0

    snr_db = p_tx_dbm + g_tx_dbi + g_rx_dbi - l_fs_db - pointing_loss_db - misc_loss_db - n_dbm
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


# --- Streamlit UI ---
st.set_page_config(page_title="SISP Common-Band Study (437 MHz)", layout="wide")
st.title("SISP Common-Band Study: 437 MHz vs Ka Baseline")
st.caption("Study tool: link budget, PER, and 5-second correction-window timing/energy. C++ protocol code is untouched.")

modulations = {
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
    st.header("UHF (Common Band) Inputs")
    f_uhf_hz = 437e6

    p_tx_dbm = st.slider("Tx RF Power (dBm)", 10.0, 40.0, 30.0, 1.0)
    g_tx = st.slider("Tx Antenna Gain (dBi)", -2.0, 15.0, 2.0, 0.5)
    g_rx = st.slider("Rx Antenna Gain (dBi)", -2.0, 15.0, 2.0, 0.5)

    pointing_loss = st.slider("Pointing Loss (dB)", 0.0, 5.0, 0.0, 0.5)
    misc_loss = st.slider("Other Losses (dB)", 0.0, 10.0, 0.0, 0.5)

    t_sys = st.slider("System Temperature (K)", 150.0, 800.0, 280.0, 10.0)
    b_hz = st.slider("Allocated Bandwidth (Hz)", 5_000, 500_000, 10_000, 500)

    modulation_label = st.selectbox("Modulation", list(modulations.keys()), index=3)
    modulation, spectral_eff = modulations[modulation_label]

    coding_label = st.selectbox("FEC", list(coding_modes.keys()), index=2)
    coding = coding_modes[coding_label]

    r_bps = float(b_hz) * float(spectral_eff)
    st.markdown(f"**Derived Bit Rate:** {fmt_si_rate(r_bps)}  (spectral efficiency ≈ {spectral_eff:.2f} b/s/Hz)")

    st.divider()
    overlay_ka = st.checkbox("Overlay Ka (26 GHz) baseline", value=True)

    if overlay_ka:
        st.subheader("Ka Baseline (for documentation)")
        p_tx_dbm_ka = st.slider("Ka Tx RF Power (dBm)", 10.0, 40.0, 30.0, 1.0, key="ka_ptx")
        g_ka = st.slider("Ka Antenna Gain (dBi) — Tx and Rx", 0.0, 35.0, 23.0, 0.5)
        b_hz_ka = st.slider("Ka Bandwidth (Hz)", 10_000, 5_000_000, 100_000, 10_000, key="ka_b")
        modulation_label_ka = st.selectbox("Ka Modulation", ["BPSK (coherent)", "QPSK (Gray, coherent)"], index=0)
        modulation_ka, spectral_eff_ka = modulations[modulation_label_ka]
        coding_label_ka = st.selectbox("Ka FEC", list(coding_modes.keys()), index=2, key="ka_coding")
        coding_ka = coding_modes[coding_label_ka]
        pointing_loss_ka = st.slider("Ka Pointing Loss (dB)", 0.0, 5.0, 2.0, 0.5, key="ka_point")
        misc_loss_ka = st.slider("Ka Other Losses (dB)", 0.0, 10.0, 0.0, 0.5, key="ka_misc")
        r_bps_ka = float(b_hz_ka) * float(spectral_eff_ka)
        st.markdown(f"**Ka Derived Bit Rate:** {fmt_si_rate(r_bps_ka)}")


tab1, tab2, tab3 = st.tabs([
    "Plot: Eb/N0 & PER vs Range",
    "Timing/Energy: Failure & Correction",
    "5-second Correction Window",
])


with tab1:
    st.subheader("Eb/N0 and Packet Error vs Distance")

    d_min = st.number_input("Min distance (km)", min_value=10.0, max_value=20000.0, value=100.0, step=10.0)
    d_max = st.number_input("Max distance (km)", min_value=10.0, max_value=20000.0, value=5000.0, step=50.0)
    n_points = st.slider("Plot resolution", 100, 800, 400, 50)

    d_km = np.linspace(float(d_min), float(d_max), int(n_points))

    _, ebn0_uhf = calc_link_budget(
        d_km=d_km,
        p_tx_dbm=p_tx_dbm,
        f_hz=f_uhf_hz,
        g_tx_dbi=g_tx,
        g_rx_dbi=g_rx,
        t_sys_k=t_sys,
        b_hz=float(b_hz),
        r_bps=r_bps,
        pointing_loss_db=pointing_loss,
        misc_loss_db=misc_loss,
    )

    ber_uhf = ber_post_decoding(ebn0_uhf, modulation=modulation, coding=coding)
    per_uhf = per_from_ber(ber_uhf, FRAME_BITS)

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(12, 4))
    ax_a.plot(d_km, ebn0_uhf, label=f"UHF 437 MHz — {modulation_label} / {coding_label}")
    ax_a.set(xlabel="Distance (km)", ylabel="Eb/N0 (dB)")
    ax_a.grid(True, ls="--", alpha=0.4)

    ax_b.semilogy(d_km, per_uhf, label="UHF PER (64B frame)")
    ax_b.set(xlabel="Distance (km)", ylabel="PER")
    ax_b.set_ylim(1e-8, 1)
    ax_b.grid(True, which="both", ls="--", alpha=0.4)

    if overlay_ka:
        f_ka_hz = 26e9
        _, ebn0_ka = calc_link_budget(
            d_km=d_km,
            p_tx_dbm=p_tx_dbm_ka,
            f_hz=f_ka_hz,
            g_tx_dbi=g_ka,
            g_rx_dbi=g_ka,
            t_sys_k=t_sys,
            b_hz=float(b_hz_ka),
            r_bps=r_bps_ka,
            pointing_loss_db=pointing_loss_ka,
            misc_loss_db=misc_loss_ka,
        )
        ber_ka = ber_post_decoding(ebn0_ka, modulation=modulation_ka, coding=coding_ka)
        per_ka = per_from_ber(ber_ka, FRAME_BITS)
        ax_a.plot(d_km, ebn0_ka, label="Ka 26 GHz baseline")
        ax_b.semilogy(d_km, per_ka, label="Ka PER (64B frame)")

    ax_a.legend()
    ax_b.legend()
    st.pyplot(fig)


with tab2:
    st.subheader("Energy & Time Scenarios")
    st.caption("Evaluate a single-band UHF concept: keep control traffic at the sidebar bandwidth (e.g., 10 kHz), and optionally bond bandwidth (e.g., 2×) + change modulation/FEC only during bulk/emergency transfers. Bulk feasibility is usually constrained by LoS window time (Module M1), not the 5-second correction timer.")

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("**DC power model (energy study)**")
        p_tx_dc_w = st.slider("Tx DC power while transmitting (W)", 0.5, 30.0, 10.0, 0.5)
        p_rx_dc_w = st.slider("Rx DC power while receiving (W)", 0.1, 15.0, 2.5, 0.1)
        p_adcs_w = st.slider("Extra ADCS/pointing power (W) [Ka-only, optional]", 0.0, 10.0, 3.0, 0.5)

        st.markdown("**Geometry / LoS window (Module M1)**")
        los_window_min = st.slider("Visibility window (minutes)", 1.0, 60.0, 15.0, 1.0)

        st.markdown("**Bulk failure dump**")
        st.markdown("**Bulk/emergency PHY (single-band UHF idea)**")
        bulk_use_control_phy = st.checkbox("Use control PHY for bulk (same modulation/FEC)", value=True)
        bulk_bw_mult = st.selectbox("Bulk bandwidth multiplier (bonding)", [1, 2], index=0, format_func=lambda x: f"{x}×")

        if bulk_use_control_phy:
            bulk_modulation_label = modulation_label
            bulk_modulation = modulation
            bulk_spectral_eff = spectral_eff
            bulk_coding_label = coding_label
            bulk_coding = coding
        else:
            bulk_modulation_label = st.selectbox(
                "Bulk modulation",
                list(modulations.keys()),
                index=list(modulations.keys()).index(modulation_label),
                key="bulk_mod",
            )
            bulk_modulation, bulk_spectral_eff = modulations[bulk_modulation_label]
            bulk_coding_label = st.selectbox(
                "Bulk FEC",
                list(coding_modes.keys()),
                index=list(coding_modes.keys()).index(coding_label),
                key="bulk_fec",
            )
            bulk_coding = coding_modes[bulk_coding_label]

        b_bulk_hz = float(b_hz) * float(bulk_bw_mult)
        r_bps_bulk = b_bulk_hz * float(bulk_spectral_eff)
        st.markdown(
            f"**Bulk derived bit rate:** {fmt_si_rate(r_bps_bulk)}  (B={b_bulk_hz:,.0f} Hz, spectral efficiency ≈ {bulk_spectral_eff:.2f} b/s/Hz)"
        )

        dump_model_note = "manual"
        dump_mb = st.slider("Failure dump size (MB)", 0.01, 10.0, 1.0, 0.01)
        compression_ratio = st.slider("Compression ratio (original/compressed)", 1.0, 20.0, 3.0, 0.5)
        dump_bytes = float(dump_mb) * 1024.0 * 1024.0
        dump_bytes_eff = dump_bytes / max(compression_ratio, 1.0)

        with st.expander("Optional: Low-rank (SVD) dump model", expanded=False):
            enable_low_rank = st.checkbox("Enable low-rank model", value=False)
            if enable_low_rank:
                st.caption("Models a low-rank SVD representation: A≈U_r·diag(s)·V_r^T, storing U (m×r), s (r), V (n×r).")
                m_rows = st.number_input("Matrix rows (m)", min_value=1, max_value=20000, value=256, step=1)
                n_cols = st.number_input("Matrix cols (n)", min_value=1, max_value=20000, value=256, step=1)
                r_rank = st.number_input("Rank kept (r)", min_value=1, max_value=4096, value=16, step=1)

                raw_dtype = st.selectbox("Original element type", ["float32", "float64"], index=0)
                raw_bits_per = 32 if raw_dtype == "float32" else 64
                coeff_bits = st.slider("Quantization bits per SVD coefficient", 8, 32, 12, 1)
                entropy_gain = st.slider("Extra entropy compression gain (×)", 1.0, 10.0, 1.0, 0.5)

                raw_bytes = (float(m_rows) * float(n_cols) * float(raw_bits_per)) / 8.0
                n_coeff = float(r_rank) * (float(m_rows) + float(n_cols) + 1.0)
                svd_bytes = (n_coeff * float(coeff_bits)) / 8.0
                dump_bytes = raw_bytes
                dump_bytes_eff = svd_bytes / max(entropy_gain, 1.0)
                compression_ratio = dump_bytes / max(dump_bytes_eff, 1.0)
                dump_model_note = f"SVD low-rank r={int(r_rank)} (raw {raw_dtype}, coeff {coeff_bits}b)"

                st.write(
                    {
                        "Raw size": f"{raw_bytes/1024.0:.1f} KiB",
                        "SVD coeff count": f"{n_coeff:,.0f}",
                        "SVD size (before entropy)": f"{svd_bytes/1024.0:.1f} KiB",
                        "Effective size": f"{dump_bytes_eff/1024.0:.1f} KiB",
                        "Implied compression ratio": f"{compression_ratio:.2f}×",
                    }
                )

        payload_per_frame_b = st.slider("Useful payload per 64B frame (bytes)", 10, 64, 45, 1)
        use_arq = st.checkbox("Assume ARQ retries per frame", value=True)

    with col_r:
        st.markdown("**Correction snapshot**")
        n_neigh = st.slider("Neighbour responses (count)", 0, 8, 8, 1)
        repeats = st.slider("Repetitions per frame (" + '"double"' + " = 2)", 1, 5, 1, 1)
        d_snapshot_km = st.slider("Range for snapshot calc (km)", 10.0, 5000.0, 1000.0, 10.0)

    bits_per_frame_on_air_ctrl = FRAME_BITS * coding_expansion(coding)
    frame_time_ctrl_s = bits_per_frame_on_air_ctrl / max(r_bps, 1.0)

    # Snapshot timing: (req + N rsp) frames, sequential on channel, plus two propagation delays.
    prop_s = one_way_prop_delay_s(float(d_snapshot_km))
    snapshot_time_s = repeats * ((1 + n_neigh) * frame_time_ctrl_s) + 2.0 * prop_s
    # Energy breakdown (DC power model): separate TX and RX contributions.
    e_req_tx_j = repeats * (1.0 * frame_time_ctrl_s) * p_tx_dc_w
    e_req_rx_neigh_total_j = repeats * (float(n_neigh) * frame_time_ctrl_s) * p_rx_dc_w
    e_rsp_tx_neigh_total_j = repeats * (float(n_neigh) * frame_time_ctrl_s) * p_tx_dc_w
    e_rsp_rx_requester_j = repeats * (float(n_neigh) * frame_time_ctrl_s) * p_rx_dc_w
    snapshot_energy_j = e_req_tx_j + e_req_rx_neigh_total_j + e_rsp_tx_neigh_total_j + e_rsp_rx_requester_j

    st.markdown("---")
    st.markdown("**Correction snapshot results (UHF config)**")
    st.write(
        {
            "Derived bit rate": fmt_si_rate(r_bps),
            "On-air bits per protocol frame": f"{bits_per_frame_on_air_ctrl:.0f} bits",
            "One frame TX time": f"{frame_time_ctrl_s*1000.0:.1f} ms",
            "One-way propagation": f"{prop_s*1000.0:.2f} ms",
            "Total snapshot time": f"{snapshot_time_s:.3f} s",
            "Energy (requester TX)": f"{e_req_tx_j:.2f} J",
            "Energy (neighbours RX request)": f"{e_req_rx_neigh_total_j:.2f} J",
            "Energy (neighbours TX responses)": f"{e_rsp_tx_neigh_total_j:.2f} J",
            "Energy (requester RX responses)": f"{e_rsp_rx_requester_j:.2f} J",
            "Total energy (TX+RX, network)": f"{snapshot_energy_j:.2f} J",
            "Meets 5-second timer?": "YES" if snapshot_time_s <= 5.0 else "NO",
        }
    )

    # Bulk dump model.
    n_frames = int(math.ceil(dump_bytes_eff / max(payload_per_frame_b, 1)))

    bits_per_frame_on_air_bulk = FRAME_BITS * coding_expansion(bulk_coding)
    frame_time_bulk_s = bits_per_frame_on_air_bulk / max(r_bps_bulk, 1.0)

    # PER at selected range (use same PER model as plot; distance affects Eb/N0 thus BER thus PER).
    _, ebn0_at_d = calc_link_budget(
        d_km=np.array([float(d_snapshot_km)]),
        p_tx_dbm=p_tx_dbm,
        f_hz=f_uhf_hz,
        g_tx_dbi=g_tx,
        g_rx_dbi=g_rx,
        t_sys_k=t_sys,
        b_hz=float(b_bulk_hz),
        r_bps=r_bps_bulk,
        pointing_loss_db=pointing_loss,
        misc_loss_db=misc_loss,
    )
    ber_at_d = float(ber_post_decoding(ebn0_at_d, modulation=bulk_modulation, coding=bulk_coding)[0])
    per_frame = float(per_from_ber(np.array([ber_at_d]), FRAME_BITS)[0])
    per_frame = min(max(per_frame, 0.0), 1.0)

    if use_arq:
        # Expected transmissions per successful frame, geometric model.
        exp_tx_per_frame = 1.0 / max(1e-9, (1.0 - per_frame))
        exp_total_frames = n_frames * exp_tx_per_frame
        p_success_file = 1.0  # by assumption (eventual success)
    else:
        exp_total_frames = float(n_frames)
        p_success_file = (1.0 - per_frame) ** n_frames

    bulk_time_s = exp_total_frames * frame_time_bulk_s
    bulk_tx_energy_j = bulk_time_s * p_tx_dc_w
    bulk_rx_energy_j = bulk_time_s * p_rx_dc_w
    bulk_energy_j = bulk_tx_energy_j + bulk_rx_energy_j
    fits_los = bulk_time_s <= (float(los_window_min) * 60.0)

    st.markdown("---")
    st.markdown("**Bulk failure dump results (UHF config @ selected range)**")
    st.write(
        {
            "Dump model": dump_model_note,
            "Compressed size": f"{dump_bytes_eff/1024.0:.1f} KiB",
            "Frames required": n_frames,
            "Bulk derived bit rate": fmt_si_rate(r_bps_bulk),
            "Bulk PHY": f"{bulk_modulation_label} / {bulk_coding_label}",
            "Bulk bandwidth": f"{b_bulk_hz:,.0f} Hz ({int(bulk_bw_mult)}×)",
            "On-air bits per protocol frame": f"{bits_per_frame_on_air_bulk:.0f} bits",
            "Frame PER": f"{per_frame:.3e}",
            "Expected transmitted frames": f"{exp_total_frames:,.0f}",
            "Total TX time": f"{bulk_time_s/60.0:.2f} min",
            "Fits visibility window?": "YES" if fits_los else "NO",
            "Energy (sender TX)": f"{bulk_tx_energy_j/3600.0:.3f} Wh ({bulk_tx_energy_j:.0f} J)",
            "Energy (receiver RX)": f"{bulk_rx_energy_j/3600.0:.3f} Wh ({bulk_rx_energy_j:.0f} J)",
            "Total energy (TX+RX)": f"{bulk_energy_j/3600.0:.3f} Wh ({bulk_energy_j:.0f} J)",
            "One-shot file success prob": f"{p_success_file:.3e}" if not use_arq else "(ARQ assumed)",
        }
    )

    st.markdown("---")
    st.markdown("**Bulk PHY search (UHF single-band, brute force)**")
    st.caption("Scans small candidate sets to find which modulation/FEC/bonding best fits the LoS window for the selected range and dump size model.")

    sort_key = st.selectbox("Sort by", ["Energy (Wh)", "Time (min)", "PER"], index=0)
    top_k = st.slider("Show top results", 3, 20, 10, 1)
    run_search = st.button("Run bulk PHY search")

    if run_search:
        candidates = []
        bw_mults = [1, 2]
        for bw_mult in bw_mults:
            b_cand = float(b_hz) * float(bw_mult)
            for mod_label, (mod_name, eff) in modulations.items():
                for code_label, code_name in coding_modes.items():
                    r_cand = b_cand * float(eff)
                    bits_on_air = FRAME_BITS * coding_expansion(code_name)
                    t_frame = bits_on_air / max(r_cand, 1.0)

                    _, ebn0 = calc_link_budget(
                        d_km=np.array([float(d_snapshot_km)]),
                        p_tx_dbm=p_tx_dbm,
                        f_hz=f_uhf_hz,
                        g_tx_dbi=g_tx,
                        g_rx_dbi=g_rx,
                        t_sys_k=t_sys,
                        b_hz=b_cand,
                        r_bps=r_cand,
                        pointing_loss_db=pointing_loss,
                        misc_loss_db=misc_loss,
                    )
                    ber = float(ber_post_decoding(ebn0, modulation=mod_name, coding=code_name)[0])
                    per = float(per_from_ber(np.array([ber]), FRAME_BITS)[0])
                    per = min(max(per, 0.0), 1.0)

                    if use_arq:
                        exp_tx = 1.0 / max(1e-9, (1.0 - per))
                        exp_frames = float(n_frames) * exp_tx
                    else:
                        exp_frames = float(n_frames)

                    t_total = exp_frames * t_frame
                    e_wh = (t_total * p_tx_dc_w) / 3600.0
                    fits = t_total <= (float(los_window_min) * 60.0)

                    candidates.append(
                        {
                            "Fits": "YES" if fits else "NO",
                            "BW (Hz)": int(b_cand),
                            "BW×": int(bw_mult),
                            "Mod": mod_label,
                            "FEC": code_label,
                            "Rb": fmt_si_rate(r_cand),
                            "PER": per,
                            "Time (min)": t_total / 60.0,
                            "Energy (Wh)": e_wh,
                        }
                    )

        if sort_key == "Energy (Wh)":
            candidates.sort(key=lambda r: (r["Fits"] != "YES", r["Energy (Wh)"]))
        elif sort_key == "Time (min)":
            candidates.sort(key=lambda r: (r["Fits"] != "YES", r["Time (min)"]))
        else:
            candidates.sort(key=lambda r: (r["Fits"] != "YES", r["PER"]))

        st.dataframe(candidates[: int(top_k)], use_container_width=True)

    if overlay_ka:
        bits_per_frame_ka = FRAME_BITS * coding_expansion(coding_ka)
        frame_time_ka = bits_per_frame_ka / max(r_bps_ka, 1.0)

        _, ebn0_ka_at_d = calc_link_budget(
            d_km=np.array([float(d_snapshot_km)]),
            p_tx_dbm=p_tx_dbm_ka,
            f_hz=26e9,
            g_tx_dbi=g_ka,
            g_rx_dbi=g_ka,
            t_sys_k=t_sys,
            b_hz=float(b_hz_ka),
            r_bps=r_bps_ka,
            pointing_loss_db=pointing_loss_ka,
            misc_loss_db=misc_loss_ka,
        )
        ber_ka_at_d = float(ber_post_decoding(ebn0_ka_at_d, modulation=modulation_ka, coding=coding_ka)[0])
        per_frame_ka = float(per_from_ber(np.array([ber_ka_at_d]), FRAME_BITS)[0])
        per_frame_ka = min(max(per_frame_ka, 0.0), 1.0)

        if use_arq:
            exp_tx_per_frame_ka = 1.0 / max(1e-9, (1.0 - per_frame_ka))
            exp_total_frames_ka = n_frames * exp_tx_per_frame_ka
        else:
            exp_total_frames_ka = float(n_frames)

        bulk_time_ka_s = exp_total_frames_ka * frame_time_ka
        bulk_energy_ka_j = bulk_time_ka_s * (p_tx_dc_w + p_adcs_w)
        fits_los_ka = bulk_time_ka_s <= (float(los_window_min) * 60.0)

        st.markdown("---")
        st.markdown("**Ka baseline (same dump + range)**")
        st.write(
            {
                "Derived bit rate": fmt_si_rate(r_bps_ka),
                "Frame PER": f"{per_frame_ka:.3e}",
                "Expected transmitted frames": f"{exp_total_frames_ka:,.0f}",
                "Total TX time": f"{bulk_time_ka_s/60.0:.2f} min",
                "Fits visibility window?": "YES" if fits_los_ka else "NO",
                "Total energy (Tx DC + ADCS)": f"{bulk_energy_ka_j/3600.0:.3f} Wh ({bulk_energy_ka_j:.0f} J)",
            }
        )


with tab3:
    st.subheader("5-second Correction Timer vs Bitrate")
    st.caption("C++ state machine starts a strict 5-second timer after CORRECTION_REQ is sent. This check models the on-air time budget.")

    col_a, col_b = st.columns(2)
    with col_a:
        d_km_timer = st.slider("Worst-case neighbour range (km)", 10.0, 5000.0, 1000.0, 10.0, key="timer_range")
        rsp_count = st.slider("Responses expected", 0, 8, 8, 1, key="timer_rsp")
        repeats_timer = st.slider("Repetitions per frame", 1, 5, 1, 1, key="timer_rep")

    with col_b:
        st.markdown("**Assumptions**")
        st.write(
            {
                "Frame size": f"{FRAME_BYTES} B fixed protocol frame",
                "Coding expansion": f"{coding_expansion(coding):.3f}x",
                "Sequential access": "Yes (worst case, TDMA-like)",
            }
        )

    bits_on_air = FRAME_BITS * coding_expansion(coding)
    frame_tx = bits_on_air / max(r_bps, 1.0)
    prop = one_way_prop_delay_s(float(d_km_timer))

    time_total = repeats_timer * ((1 + rsp_count) * frame_tx) + 2.0 * prop

    # Compute min bitrate to fit in 5 seconds (ignoring propagation, which is tiny at LEO).
    frames_total = repeats_timer * (1 + rsp_count)
    min_r_bps = (frames_total * bits_on_air) / max(1e-9, (5.0 - 2.0 * prop))

    st.markdown("---")
    st.write(
        {
            "Derived bit rate": fmt_si_rate(r_bps),
            "Per-frame TX time": f"{frame_tx*1000.0:.1f} ms",
            "Total time": f"{time_total:.3f} s",
            "Meets 5 seconds?": "YES" if time_total <= 5.0 else "NO",
            "Min bitrate to fit (this config)": fmt_si_rate(min_r_bps),
        }
    )
