"""
SISP Value Proposition Dashboard
=================================
Quantified KPIs across five dimensions, projected 50 years (2025–2075):

  1. Sensor Quality & Availability
  2. Energy & Carbon Impact
  3. Mission Economics & Satellite Life
  4. Industry Transformation (Modular / Shared-Compute)
  5. 50-Year Projection

Run:
    streamlit run "simulation for signal and physics/sisp_value_dashboard.py"
"""

import math
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D

# ─── Theme ────────────────────────────────────────────────────────────────────
plt.style.use("dark_background")
for k, v in {
    "axes.facecolor": "#0a0a0a", "figure.facecolor": "#0a0a0a",
    "axes.edgecolor": "#333", "grid.color": "#1e1e1e",
    "text.color": "#fff", "xtick.color": "#888", "ytick.color": "#888",
    "axes.prop_cycle": plt.cycler(color=[
        "#00a2ff", "#ff6b35", "#00e5a0", "#ffcc00", "#cc44ff", "#ff4466"]),
}.items():
    plt.rcParams[k] = v

st.set_page_config(page_title="SISP Value Proposition", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
html,body,[data-testid="stAppViewContainer"]{background:#060606;color:#fff;font-family:'Outfit',sans-serif;}
[data-testid="stSidebar"]{background:#0d0d0d;border-right:1px solid rgba(0,162,255,.2);}
h1,h2,h3{color:#00a2ff!important;font-weight:700!important;}
.stTabs [data-baseweb="tab"]{background:rgba(255,255,255,.03);border-radius:8px 8px 0 0;color:#888;border:none;padding:10px 22px;}
.stTabs [aria-selected="true"]{background:rgba(0,162,255,.12)!important;color:#00a2ff!important;border-bottom:2px solid #00a2ff!important;}
.metric-card{background:rgba(0,162,255,.07);border:1px solid rgba(0,162,255,.18);border-radius:12px;padding:18px 22px;margin-bottom:8px;}
.win-card{background:rgba(0,229,160,.07);border:1px solid rgba(0,229,160,.2);border-radius:12px;padding:14px 18px;margin:4px 0;}
.stButton>button{background:#00a2ff;color:#000;border-radius:8px;border:none;font-weight:600;}
</style>""", unsafe_allow_html=True)

st.title("SISP · Satellite Inter-Service Protocol")
st.caption("Quantified value proposition — sensor quality, energy, mission economics, industry transformation, 50-year impact")

YEAR_START = 2025

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — global assumptions
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.image("simulation for signal and physics/logo.png", width="stretch")
    st.markdown("---")
    st.header("Constellation Assumptions")

    n_sats = st.slider("Constellation size (satellites)", 10, 5000, 100, 10)
    sat_cost_k = st.slider("Satellite unit cost ($K)", 50, 10_000, 500, 50)
    design_life_yr = st.slider("Design life without SISP (years)", 1, 10, 3, 1)
    life_ext_pct = st.slider("SISP life extension (%)", 10, 100, 45, 5)
    annual_fail_pct = st.slider("Annual sensor failure rate (%)", 2, 40, 12, 1)
    borrow_recovery_pct = st.slider("Failures recovered via borrowing (%)", 10, 90, 60, 5)

    st.markdown("---")
    st.header("Launch & Mass")
    launch_cost_per_kg = st.slider("Launch cost ($/kg)", 1_000, 50_000, 6_000, 500)
    sat_mass_kg = st.slider("Satellite mass (kg)", 1, 500, 5, 1)
    volume_reduction_pct = st.slider("Volume/mass reduction via modularity (%)", 5, 50, 25, 5)

    st.markdown("---")
    st.header("RF / Connectivity")
    gs_coverage_pct = st.slider("Ground-station LoS coverage (% orbit)", 5, 30, 10, 1)
    isl_coverage_pct = st.slider("ISL LoS coverage (% orbit)", 20, 80, 45, 5)
    data_gb_per_day = st.slider("Daily data per satellite (GB)", 0.1, 200.0, 5.0, 0.5)

    st.markdown("---")
    st.header("Energy (RF only)")
    p_tx_w = st.slider("Tx DC power (W)", 1.0, 20.0, 10.0, 0.5)
    p_rx_w = st.slider("Rx DC power (W)", 0.5, 10.0, 2.5, 0.5)
    correction_per_day = st.slider("Corrections/day", 1, 100, 24, 1)
    n_neighbours = st.slider("Neighbours per correction", 2, 8, 6, 1)

    st.markdown("---")
    st.header("Carbon & Environment")
    co2_per_launch_t = st.slider("CO₂ per launch (tonnes)", 50, 1000, 300, 50)
    energy_mix_gco2_kwh = st.slider("Grid carbon intensity (gCO₂/kWh)", 50, 600, 300, 25)

# ═══════════════════════════════════════════════════════════════════════════════
# DERIVED CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
sat_cost = sat_cost_k * 1_000
life_ext_factor = 1 + life_ext_pct / 100
effective_life = design_life_yr * life_ext_factor

# Correction energy
FRAME_BITS = 512
EXPANSION = 2.287  # Conv+RS
R_BPS_CTRL = 12_500
t_frame_s = (FRAME_BITS * EXPANSION) / R_BPS_CTRL          # ~93.6 ms
e_corr_event_j = (1 + n_neighbours) * t_frame_s * (p_tx_w + n_neighbours * p_rx_w)
e_corr_daily_j = correction_per_day * e_corr_event_j
e_corr_daily_wh = e_corr_daily_j / 3600

# ISL vs GS connectivity gain
isl_gs_ratio = isl_coverage_pct / max(gs_coverage_pct, 0.1)

# Data relay via ISL
# With ISL, data can be forwarded to nearest satellite with GS pass →
# effectively available_time = isl_coverage * relay_hops (up to 3)
relay_mult = min(isl_gs_ratio * 0.6, 10)           # conservative 60% efficiency

# Replacement economics
annual_fail_frac = annual_fail_pct / 100
borrow_recovery_frac = borrow_recovery_pct / 100
missions_per_yr_baseline = n_sats / design_life_yr
missions_per_yr_sisp = n_sats / effective_life

failures_per_yr = n_sats * annual_fail_frac
recoveries_per_yr = failures_per_yr * borrow_recovery_frac
replacements_avoided_per_yr = recoveries_per_yr
cost_saved_per_yr = replacements_avoided_per_yr * sat_cost
co2_saved_per_yr_t = replacements_avoided_per_yr * co2_per_launch_t

# Modular mass reduction → launch cost savings per new satellite
mass_saved_kg = sat_mass_kg * volume_reduction_pct / 100
launch_saving_per_sat = mass_saved_kg * launch_cost_per_kg

# Projected constellation growth (industry baseline)
growth_rates = {"Conservative (5%/yr)": 0.05, "Moderate (12%/yr)": 0.12,
                "Aggressive (22%/yr)": 0.22}

HORIZON = 50   # years
years = np.arange(HORIZON + 1)
cal_years = YEAR_START + years

# ═══════════════════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════════════════
(tab_exec, tab_sensor, tab_energy, tab_econ, tab_industry, tab_50yr) = st.tabs([
    "Executive Summary",
    "Sensor Quality",
    "Energy & Carbon",
    "Mission Economics",
    "Industry Transformation",
    "50-Year Projection",
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 0 — EXECUTIVE SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
with tab_exec:
    st.subheader("SISP at a Glance — Why It Matters")
    st.markdown("""
    > **SISP turns a satellite constellation from a collection of independent nodes
    > into a cooperative, self-healing network.** When one satellite's sensor degrades,
    > its neighbours compensate — in real time, with no ground intervention.
    > The same protocol doubles effective data downlink availability, extends
    > mission life, and enables modular satellite hardware economics.
    """)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Sensor RMSE improvement", "94 %", "vs raw readings (30-day)")
    with c2:
        val = f"${cost_saved_per_yr/1e6:.1f}M" if cost_saved_per_yr >= 1e6 else f"${cost_saved_per_yr/1e3:.0f}K"
        st.metric("Annual cost savings", val, f"{replacements_avoided_per_yr:.0f} missions avoided")
    with c3:
        st.metric("ISL vs GS availability", f"{isl_gs_ratio:.1f}×", f"{isl_coverage_pct}% vs {gs_coverage_pct}%")
    with c4:
        st.metric("Life extension", f"+{life_ext_pct}%", f"{design_life_yr}yr → {effective_life:.1f}yr")

    st.markdown("---")
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.metric("CO₂ saved/year", f"{co2_saved_per_yr_t:,.0f} t", "avoided launches")
    with c6:
        st.metric("Correction energy/day", f"{e_corr_daily_wh*1000:.1f} mWh", "per satellite")
    with c7:
        st.metric("Launch saving/satellite", f"${launch_saving_per_sat:,.0f}", f"−{volume_reduction_pct}% mass")
    with c8:
        cumu_10yr = cost_saved_per_yr * 10
        label = f"${cumu_10yr/1e9:.2f}B" if cumu_10yr >= 1e9 else f"${cumu_10yr/1e6:.1f}M"
        st.metric("10-year cumulative savings", label, "constellation-wide")

    st.markdown("---")
    st.subheader("Short / Medium / Long Term Impact")

    col_s, col_m, col_l = st.columns(3)
    with col_s:
        st.markdown("**Short term (1–5 years)**")
        st.markdown(f"""
<div class="win-card">
✅ <b>Sensor quality:</b> 85–94% RMSE improvement immediately<br>
✅ <b>Energy:</b> Correction costs only {e_corr_daily_wh*1000:.1f} mWh/sat/day<br>
✅ <b>Relay:</b> {isl_gs_ratio:.1f}× more downlink windows available<br>
✅ <b>Risk:</b> Sensor failure no longer ends the mission
</div>""", unsafe_allow_html=True)
    with col_m:
        st.markdown("**Medium term (5–15 years)**")
        five_yr = cost_saved_per_yr * 5
        st.markdown(f"""
<div class="win-card">
✅ <b>Cost:</b> ${five_yr/1e6:.0f}M saved in 5 years (this constellation)<br>
✅ <b>Carbon:</b> {co2_saved_per_yr_t*5:,.0f} t CO₂ avoided<br>
✅ <b>Modularity:</b> ${launch_saving_per_sat*n_sats/1e6:.1f}M launch savings via mass reduction<br>
✅ <b>Life:</b> Satellites retired after {effective_life:.1f} yr not {design_life_yr} yr
</div>""", unsafe_allow_html=True)
    with col_l:
        st.markdown("**Long term (15–50 years)**")
        industry_market_b = 5.5  # $5.5B EO satellite market
        sisp_capture_pct = 15
        st.markdown(f"""
<div class="win-card">
✅ <b>Industry:</b> Modular satellite economy — rent sensors, not buy<br>
✅ <b>Debris:</b> Fewer replacements → slower debris growth<br>
✅ <b>Market:</b> ~${industry_market_b*sisp_capture_pct/100:.1f}B addressable "SaaS" satellite market<br>
✅ <b>Infra:</b> Constellation as distributed computing fabric
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — SENSOR QUALITY
# ─────────────────────────────────────────────────────────────────────────────
with tab_sensor:
    st.subheader("Sensor Quality Improvement")

    col_l, col_r = st.columns([1, 2])
    with col_l:
        st.markdown("**Experimental results (C++ + Python)**")
        st.markdown("""
| Scenario | Raw RMSE | Corrected | Improvement |
|---|---|---|---|
| Nominal noise (σ=2) | 2.50 | 1.30 | **48%** |
| Large fault (σ=25) | 22.71 | 8.47 | **63%** |
| 30-day drift | 8.91 | 0.50 | **94%** |
| 10% packet loss | 8.29 | 1.20 | **86%** |
| Burst outliers 15% | 19.25 | 5.99 | **69%** |
""")
        st.markdown("**Algorithm ranking** (steady-state error):")
        st.markdown("""
1. 🥇 **Hybrid** (best for unknown noise)
2. 🥈 **Kalman** (best for Gaussian)
3. 🥉 **NIS-Gated Kalman** (best vs bias)
4. **Weighted Median** (only useful < σ=5)
""")

    with col_r:
        sigma_vals = [2, 5, 8, 12, 16, 20, 30, 40, 60]
        raw_err   = [2.19, 5.16, 8.31, 13.73, 18.45, 21.73, 34.20, 47.08, 66.47]
        kal_err   = [1.08, 2.53, 4.36, 6.47,  7.77,  9.40,  15.6,  25.0,  33.6]
        hyb_err   = [1.03, 2.90, 4.54, 5.95,  8.02,  9.58,  15.7,  24.2,  40.0]
        med_err   = [2.34, 6.13, 9.88, 14.84, 20.13, 21.18, 36.1,  50.9,  78.8]

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.semilogy(sigma_vals, raw_err,  "o--", lw=1.5, label="No correction (raw)")
        ax.semilogy(sigma_vals, kal_err,  "s-",  lw=2,   label="Kalman")
        ax.semilogy(sigma_vals, hyb_err,  "^-",  lw=2,   label="Hybrid")
        ax.semilogy(sigma_vals, med_err,  "D--", lw=1.5, label="Weighted Median")
        ax.set(xlabel="Noise σ", ylabel="Steady-state RMSE (log scale)")
        ax.legend(framealpha=0.2)
        ax.grid(True, which="both", ls="--", alpha=0.3)
        st.pyplot(fig)

    st.markdown("---")
    st.subheader("Effective Sensor Availability (with Borrowing)")

    sigma_borrow = st.slider("Sensor noise level σ", 1.0, 30.0, 5.0, 0.5)
    avail_without = (1 - annual_fail_frac) ** design_life_yr * 100
    avail_with = 100 - (annual_fail_frac * (1 - borrow_recovery_frac)) * 100 * design_life_yr
    avail_with = max(avail_with, 10.0)

    years_arr = np.arange(0, design_life_yr * 2 + 1)
    avail_baseline = 100 * (1 - annual_fail_frac) ** years_arr
    recovered_each_yr = annual_fail_frac * borrow_recovery_frac
    avail_sisp = 100 * np.array([
        max((1 - annual_fail_frac * (1 - borrow_recovery_frac)) ** y, 5)
        for y in years_arr
    ])

    fig2, ax2 = plt.subplots(figsize=(10, 3.5))
    ax2.plot(years_arr, avail_baseline, "o--", lw=1.5, label="Baseline (no SISP)")
    ax2.plot(years_arr, avail_sisp,    "s-",  lw=2,   label="With SISP borrowing")
    ax2.axvline(design_life_yr, color="#ffcc00", ls=":", lw=1.2, alpha=0.6,
                label=f"Design life ({design_life_yr} yr)")
    ax2.set(xlabel="Mission year", ylabel="Fleet-average sensor availability (%)",
            ylim=(0, 105))
    ax2.legend(framealpha=0.2)
    ax2.grid(True, ls="--", alpha=0.3)
    st.pyplot(fig2)

    st.info(f"After {design_life_yr} years: baseline availability "
            f"**{avail_baseline[min(design_life_yr,len(avail_baseline)-1)]:.0f}%** → "
            f"SISP **{avail_sisp[min(design_life_yr,len(avail_sisp)-1)]:.0f}%**  "
            f"(+{avail_sisp[min(design_life_yr,len(avail_sisp)-1)]-avail_baseline[min(design_life_yr,len(avail_baseline)-1)]:.0f} pp)")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — ENERGY & CARBON
# ─────────────────────────────────────────────────────────────────────────────
with tab_energy:
    st.subheader("Energy, Connectivity & Carbon")

    st.markdown("### ISL vs Ground Station — Data Relay Advantage")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Ground pass window", f"{gs_coverage_pct}% of orbit",
                  f"≈{gs_coverage_pct*0.01*90:.0f} min/orbit")
    with c2:
        st.metric("ISL window", f"{isl_coverage_pct}% of orbit",
                  f"≈{isl_coverage_pct*0.01*90:.0f} min/orbit")
    with c3:
        st.metric("Relay multiplier", f"{isl_gs_ratio:.1f}×",
                  "more effective downlink time")

    # Connectivity comparison chart
    orbit_pct = np.linspace(0, 100, 500)
    gs_thresh = gs_coverage_pct
    isl_thresh = isl_coverage_pct

    fig3, ax3 = plt.subplots(figsize=(10, 3.5))
    ax3.fill_between(orbit_pct, 0, 1,
                     where=orbit_pct <= gs_thresh,
                     alpha=0.35, color="#ff6b35", label=f"GS window ({gs_coverage_pct}%)")
    ax3.fill_between(orbit_pct, 0, 1,
                     where=orbit_pct <= isl_thresh,
                     alpha=0.25, color="#00a2ff", label=f"ISL window ({isl_coverage_pct}%)")
    ax3.set(xlabel="Orbit position (%)", ylabel="Link available",
            yticks=[], xlim=(0, 100))
    ax3.legend(loc="upper right", framealpha=0.2)
    ax3.grid(False)
    ax3.set_facecolor("#0a0a0a")
    st.pyplot(fig3)

    st.markdown("---")
    st.markdown("### Correction Protocol Energy (per satellite per day)")

    col_l, col_r = st.columns(2)
    with col_l:
        t_frame_ms = t_frame_s * 1000
        e_total_daily_wh_fleet = e_corr_daily_wh * n_sats
        st.write({
            "Frame time (Conv+RS, 12.5 kHz)": f"{t_frame_ms:.1f} ms",
            "Correction event duration (N+1 frames)": f"{(n_neighbours+1)*t_frame_ms/1000:.3f} s",
            "Within 5-second timer": "YES" if (n_neighbours+1)*t_frame_ms/1000 < 5.0 else "NO",
            "Energy per correction event (network)": f"{e_corr_event_j:.3f} J",
            "Corrections per day": correction_per_day,
            "Daily correction energy (per satellite)": f"{e_corr_daily_wh*1000:.2f} mWh",
            "Fleet-wide daily correction energy": f"{e_total_daily_wh_fleet/1000:.3f} Wh",
        })

    with col_r:
        categories = ["Correction\nprotocol", "Downlink\n(traditional)", "Relay via ISL"]
        # Rough numbers for comparison
        dl_wh = data_gb_per_day * 8e9 / (100e3) / 3600 * p_tx_w  # at 100 kbps
        relay_wh = dl_wh / isl_gs_ratio  # ISL allows choosing better window → less ARQ
        vals = [e_corr_daily_wh, dl_wh, relay_wh]
        colors = ["#00a2ff", "#ff6b35", "#00e5a0"]
        fig4, ax4 = plt.subplots(figsize=(5, 3.5))
        bars = ax4.bar(categories, vals, color=colors, alpha=0.85, width=0.5)
        ax4.set(ylabel="Energy (Wh/day)", title="Daily comms energy breakdown")
        for bar, v in zip(bars, vals):
            ax4.text(bar.get_x() + bar.get_width()/2, v * 1.05, f"{v:.3f} Wh",
                     ha="center", va="bottom", fontsize=9, color="#ccc")
        ax4.grid(True, axis="y", ls="--", alpha=0.3)
        st.pyplot(fig4)

    st.markdown("---")
    st.markdown("### Carbon Footprint")

    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        launches_baseline = n_sats / design_life_yr
        launches_sisp = n_sats / effective_life
        launches_avoided = launches_baseline - launches_sisp
        co2_launch_saved = launches_avoided * co2_per_launch_t
        st.metric("Launches avoided/year", f"{launches_avoided:.1f}",
                  f"baseline {launches_baseline:.1f} → SISP {launches_sisp:.1f}")
    with col_c2:
        st.metric("CO₂ from avoided launches/yr", f"{co2_launch_saved:,.0f} t",
                  f"≈ {co2_launch_saved/1e6*1000:.0f} passenger flights")
    with col_c3:
        # SISP correction energy carbon cost
        e_fleet_corr_kwh_yr = e_corr_daily_wh * n_sats * 365 / 1000
        co2_elec_saved_kg = e_fleet_corr_kwh_yr * energy_mix_gco2_kwh / 1000
        st.metric("Electricity CO₂ (protocol overhead)", f"{co2_elec_saved_kg:.1f} kg/yr",
                  "negligible vs launch savings")

    years_50 = np.arange(0, 51)
    r = 0.12  # 12%/yr growth
    launches_b = (n_sats * (1 + r) ** years_50) / design_life_yr
    launches_s = (n_sats * (1 + r) ** years_50) / effective_life
    co2_b_cum = np.cumsum(launches_b * co2_per_launch_t) / 1e6
    co2_s_cum = np.cumsum(launches_s * co2_per_launch_t) / 1e6

    fig5, ax5 = plt.subplots(figsize=(10, 3.5))
    ax5.fill_between(YEAR_START + years_50, co2_b_cum, co2_s_cum,
                     alpha=0.3, color="#00e5a0", label="CO₂ saved (SISP)")
    ax5.plot(YEAR_START + years_50, co2_b_cum, "--", color="#ff6b35", lw=1.5, label="Baseline cumulative CO₂")
    ax5.plot(YEAR_START + years_50, co2_s_cum, "-", color="#00a2ff", lw=2, label="SISP cumulative CO₂")
    ax5.set(xlabel="Year", ylabel="Cumulative CO₂ (Mt)", title="50-Year CO₂: Baseline vs SISP")
    ax5.legend(framealpha=0.2)
    ax5.grid(True, ls="--", alpha=0.3)
    st.pyplot(fig5)
    co2_gap_50 = (co2_b_cum[-1] - co2_s_cum[-1])
    st.success(f"Over 50 years: SISP avoids **{co2_gap_50:.1f} Mt CO₂** (growing constellation, {r*100:.0f}%/yr growth)")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — MISSION ECONOMICS
# ─────────────────────────────────────────────────────────────────────────────
with tab_econ:
    st.subheader("Mission Economics & Satellite Life")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Design life (baseline)", f"{design_life_yr} yr")
    with c2:
        st.metric("Effective life (SISP)", f"{effective_life:.1f} yr", f"+{life_ext_pct}%")
    with c3:
        st.metric("Annual failures", f"{failures_per_yr:.1f}",
                  f"{annual_fail_pct}% of {n_sats} sats")
    with c4:
        st.metric("Recoveries via borrowing", f"{recoveries_per_yr:.1f}/yr",
                  f"{borrow_recovery_pct}% success rate")

    st.markdown("---")
    st.markdown("### Per-Year Savings Breakdown")

    col_l, col_r = st.columns(2)
    with col_l:
        # Savings breakdown
        saving_borrowing = recoveries_per_yr * sat_cost
        saving_life_ext = (missions_per_yr_baseline - missions_per_yr_sisp) * sat_cost
        saving_launch_mass = missions_per_yr_sisp * launch_saving_per_sat
        saving_gs_ops = isl_gs_ratio * n_sats * 50_000 / 365  # rough GS ops cost reduction

        labels = ["Recovered\nfailures", "Life extension\n(fewer replacements)",
                  "Launch mass\nreduction", "GS operations\nreduction"]
        values = [saving_borrowing / 1e6, saving_life_ext / 1e6,
                  saving_launch_mass / 1e6, saving_gs_ops / 1e6]
        fig6, ax6 = plt.subplots(figsize=(6, 4))
        bars = ax6.barh(labels, values, color=["#00a2ff","#00e5a0","#ffcc00","#ff6b35"], alpha=0.85)
        ax6.set(xlabel="Annual savings ($M)", title="SISP value sources")
        for bar, v in zip(bars, values):
            ax6.text(v + 0.01, bar.get_y() + bar.get_height()/2,
                     f"${v:.2f}M", va="center", fontsize=9, color="#ccc")
        ax6.grid(True, axis="x", ls="--", alpha=0.3)
        st.pyplot(fig6)

    with col_r:
        total_annual = sum(values)
        capex_sisp = n_sats * 20_000  # ~$20K integration cost per satellite (estimate)
        payback_yr = capex_sisp / (total_annual * 1e6) if total_annual > 0 else 99
        st.write({
            "Savings from recovered failures/yr": f"${saving_borrowing/1e6:.2f}M",
            "Savings from life extension/yr": f"${saving_life_ext/1e6:.2f}M",
            "Savings from mass reduction/yr": f"${saving_launch_mass/1e6:.2f}M",
            "GS operations reduction/yr (estimate)": f"${saving_gs_ops/1e6:.2f}M",
            "Total annual savings": f"${total_annual:.2f}M",
        })
        st.markdown("---")
        st.write({
            "SISP integration cost (est.)": f"${capex_sisp/1e3:.0f}K",
            "Payback period": f"{payback_yr:.2f} years" if payback_yr < 10 else ">10 yr",
            "10-year ROI": f"{(total_annual*1e6*10 - capex_sisp)/capex_sisp*100:.0f}%" if capex_sisp > 0 else "∞",
        })

    st.markdown("---")
    st.markdown("### Mission Replacement Rate Comparison")
    yrs = np.arange(0, HORIZON + 1)
    r_growth = 0.10
    consts = n_sats * (1 + r_growth) ** yrs
    missions_b = consts / design_life_yr
    missions_s = consts / effective_life
    missions_saved_cum = np.cumsum(missions_b - missions_s)
    cost_saved_cum = missions_saved_cum * sat_cost / 1e9

    fig7, (ax7a, ax7b) = plt.subplots(1, 2, figsize=(12, 4))
    ax7a.plot(YEAR_START + yrs, missions_b, "--", color="#ff6b35", lw=1.5, label="Baseline missions/yr")
    ax7a.plot(YEAR_START + yrs, missions_s, "-", color="#00a2ff", lw=2, label="SISP missions/yr")
    ax7a.fill_between(YEAR_START + yrs, missions_s, missions_b, alpha=0.2, color="#00e5a0",
                       label="Missions avoided")
    ax7a.set(xlabel="Year", ylabel="Replacement missions/yr", title="Annual replacement rate")
    ax7a.legend(framealpha=0.2, fontsize=8)
    ax7a.grid(True, ls="--", alpha=0.3)

    ax7b.plot(YEAR_START + yrs, cost_saved_cum, "-", color="#00e5a0", lw=2)
    ax7b.fill_between(YEAR_START + yrs, 0, cost_saved_cum, alpha=0.2, color="#00e5a0")
    ax7b.set(xlabel="Year", ylabel="Cumulative savings ($B)", title="Cumulative mission cost savings")
    ax7b.grid(True, ls="--", alpha=0.3)
    ax7b.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.1f}B"))

    st.pyplot(fig7)
    st.success(f"50-year cumulative savings (growing constellation): **${cost_saved_cum[-1]:.1f}B**")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — INDUSTRY TRANSFORMATION
# ─────────────────────────────────────────────────────────────────────────────
with tab_industry:
    st.subheader("Industry Transformation: Modular Satellites & Shared Infrastructure")

    st.markdown("""
    SISP enables a paradigm shift analogous to what cloud computing did to enterprise IT:
    **from owning dedicated hardware to renting shared services**.

    | Traditional model | SISP-enabled model |
    |---|---|
    | Each satellite carries full sensor redundancy | Borrow sensors from neighbours on demand |
    | Sensor failure = mission degraded/ended | Sensor failure = transparent failover |
    | Replace entire satellite when sensor fails | Keep satellite, borrow capability |
    | Fixed, monolithic hardware design | Modular, interoperable sensor economy |
    | Ground station required for every operation | ISL enables peer-to-peer autonomous ops |
    | Data center cooling: 30–40% of energy | Distributed sensor compute: no cooling overhead |
    """)

    st.markdown("---")
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("### Modular Satellite Volume Reduction")
        st.markdown(f"""
By removing redundant sensor hardware (SISP covers via borrowing):
- **Mass reduction:** {volume_reduction_pct}% of {sat_mass_kg} kg = **{mass_saved_kg:.1f} kg/satellite**
- **Launch cost saving:** ${launch_saving_per_sat:,.0f}/satellite
- **Volume reduction:** Enables move from 3U → 2U CubeSat format
- **Power reduction:** Fewer sensors → lower standby power → more comms power budget
""")

        # Mass reduction waterfall
        labels = ["Original\nmass", "Remove\nredundant\nsensors", "SISP\nsatellite"]
        vals = [sat_mass_kg, -mass_saved_kg, sat_mass_kg - mass_saved_kg]
        colors = ["#00a2ff", "#ff4466", "#00e5a0"]
        fig8, ax8 = plt.subplots(figsize=(5, 3.5))
        running = [sat_mass_kg, sat_mass_kg - mass_saved_kg]
        bottoms = [0, sat_mass_kg - mass_saved_kg]
        ax8.bar(["Baseline"], sat_mass_kg, color="#ff6b35", alpha=0.8)
        ax8.bar(["SISP"], sat_mass_kg - mass_saved_kg, color="#00a2ff", alpha=0.8)
        ax8.bar(["Reduction"], mass_saved_kg, color="#00e5a0", alpha=0.8)
        ax8.set(ylabel="Mass (kg)", title="Satellite mass comparison")
        ax8.grid(True, axis="y", ls="--", alpha=0.3)
        st.pyplot(fig8)

    with col_b:
        st.markdown("### Satellite-as-a-Service Market")
        eo_market_b = 5.5
        sisp_addr_pct = 15
        st.markdown(f"""
**Current EO (Earth Observation) satellite market:** ~${eo_market_b}B/year

With SISP-enabled sensor borrowing and shared services:
- **Addressable "SaaS satellite" market:** ~${eo_market_b*sisp_addr_pct/100:.2f}B/yr
- **Growth:** Following cloud analogy — cloud went from 0 to $500B in 15 years
- **Revenue model:** Charge per borrowed sensor-hour, per correction event, per relay hop
""")
        saas_years = np.arange(15)
        saas_market = eo_market_b * 0.02 * (1.35 ** saas_years)
        fig9, ax9 = plt.subplots(figsize=(5, 3.5))
        ax9.fill_between(YEAR_START + saas_years, 0, saas_market, alpha=0.3, color="#ffcc00")
        ax9.plot(YEAR_START + saas_years, saas_market, "-o", color="#ffcc00", lw=2, ms=4)
        ax9.set(xlabel="Year", ylabel="SaaS satellite market ($B/yr)",
                title="Projected SISP-enabled SaaS market")
        ax9.grid(True, ls="--", alpha=0.3)
        ax9.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.1f}B"))
        st.pyplot(fig9)

    st.markdown("---")
    st.markdown("### Shared Computation & Distributed Sensor Infrastructure")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("""
**Analogy: Cloud Data Centers**

Traditional data centers spend 30–40% of energy on cooling.
AWS alone saved ~$1B/year by moving to shared infrastructure.

**In space, there is no cooling problem** — passive radiation is free.
SISP enables the equivalent of a distributed sensor cloud:
- Satellite A borrows optical sensor from satellite B
- Satellite C relays A's data through B to ground
- No dedicated ground station needed for routine operations
- Effective: **every satellite improves every other satellite's capability**
""")

    with col_c2:
        # Metcalfe's law: value ∝ n²
        n_range = np.arange(2, 500)
        value_baseline = n_range               # isolated: linear
        value_sisp = n_range * np.log2(n_range)  # cooperative: super-linear
        fig10, ax10 = plt.subplots(figsize=(5, 3.5))
        ax10.plot(n_range, value_baseline / value_baseline[-1], "--", color="#ff6b35",
                  lw=1.5, label="Isolated constellation")
        ax10.plot(n_range, value_sisp / value_sisp[-1], "-", color="#00a2ff",
                  lw=2, label="SISP cooperative constellation")
        ax10.set(xlabel="Constellation size", ylabel="Normalised value",
                 title="Network effect: cooperative vs isolated")
        ax10.legend(framealpha=0.2)
        ax10.grid(True, ls="--", alpha=0.3)
        st.pyplot(fig10)
        st.caption("Value grows as n·log₂(n) with SISP vs linear without — the cooperative network effect.")

    st.markdown("---")
    st.markdown("### Debris & Sustainability")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        active_sats_2025 = 7500
        debris_growth = 0.03  # 3%/yr
        debris_2025 = 27000
        yrs_d = np.arange(51)
        sats_b = active_sats_2025 * (1.12 ** yrs_d)
        sats_s = active_sats_2025 * (1.12 ** yrs_d) * (design_life_yr / effective_life) + \
                 active_sats_2025 * (1 - design_life_yr / effective_life)
        debris_b = debris_2025 * (1 + debris_growth) ** yrs_d + np.cumsum(sats_b / design_life_yr) * 0.1
        debris_s = debris_2025 * (1 + debris_growth) ** yrs_d + np.cumsum(sats_s / effective_life) * 0.1

        fig11, ax11 = plt.subplots(figsize=(5, 3.5))
        ax11.plot(YEAR_START + yrs_d, debris_b / 1000, "--", color="#ff6b35", lw=1.5, label="Baseline")
        ax11.plot(YEAR_START + yrs_d, debris_s / 1000, "-", color="#00a2ff", lw=2, label="With SISP")
        ax11.fill_between(YEAR_START + yrs_d, debris_s/1000, debris_b/1000, alpha=0.2, color="#00e5a0",
                          label="Debris avoided")
        ax11.set(xlabel="Year", ylabel="Tracked debris objects (thousands)",
                 title="Space debris projection")
        ax11.legend(framealpha=0.2, fontsize=8)
        ax11.grid(True, ls="--", alpha=0.3)
        st.pyplot(fig11)

    with col_d2:
        st.markdown(f"""
**Why SISP reduces debris growth:**

1. **Fewer replacement launches** — satellites live {life_ext_pct}% longer → fewer retired satellites added to debris field
2. **Recovered failures** — {recoveries_per_yr:.0f} satellites/year that would become derelict debris are kept operational
3. **Smaller satellites** (modular design) → less mass → less energy on deorbit → better deorbit compliance
4. **Fewer emergency launches** — no need to rush a replacement satellite when a sensor fails

At scale (10,000+ constellation), SISP could **defer the Kessler cascade threshold** by 5–15 years.
""")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — 50-YEAR PROJECTION
# ─────────────────────────────────────────────────────────────────────────────
with tab_50yr:
    st.subheader("50-Year Projection (2025–2075)")
    st.caption("Select growth scenario to explore cumulative impact of SISP across the global satellite industry.")

    growth_label = st.radio("Industry growth scenario", list(growth_rates.keys()), index=1, horizontal=True)
    r = growth_rates[growth_label]

    yrs50 = np.arange(51)
    cal = YEAR_START + yrs50

    # Constellation size
    n_t = n_sats * (1 + r) ** yrs50

    # Mission economics
    missions_baseline = n_t / design_life_yr
    missions_sisp = n_t / effective_life
    missions_avoided_cum = np.cumsum(missions_baseline - missions_sisp)
    cost_saved_cum_50 = missions_avoided_cum * sat_cost / 1e9

    # CO2
    co2_baseline_cum = np.cumsum(missions_baseline * co2_per_launch_t) / 1e6  # Mt
    co2_sisp_cum = np.cumsum(missions_sisp * co2_per_launch_t) / 1e6

    # Sensor quality fleet-wide: equivalent full-quality sensor-years saved
    fail_baseline = n_t * annual_fail_frac
    recovered = fail_baseline * borrow_recovery_frac
    sensor_years_saved_cum = np.cumsum(recovered * 0.5)  # avg 0.5 yr life extension per recovery

    # Energy savings (ISL relay efficiency gain)
    energy_saving_wh_yr = n_t * data_gb_per_day * 365 * 8e9 / (100e3) / 3600 * p_tx_w * (1 - 1/isl_gs_ratio) * 0.2
    energy_saved_cum_twh = np.cumsum(energy_saving_wh_yr) / 1e12  # TWh

    fig50, axes = plt.subplots(2, 3, figsize=(16, 9))
    fig50.suptitle(f"SISP 50-Year Impact — {growth_label}", fontsize=13, color="#00a2ff", y=1.01)

    def _plot(ax, x, y_base, y_sisp, ylabel, title, unit="", fill=True):
        ax.plot(x, y_base, "--", color="#ff6b35", lw=1.5, label="Baseline")
        ax.plot(x, y_sisp, "-", color="#00a2ff", lw=2, label="SISP")
        if fill:
            ax.fill_between(x, y_sisp, y_base, alpha=0.2, color="#00e5a0", label="Saved")
        ax.set(xlabel="Year", ylabel=ylabel, title=title)
        ax.legend(framealpha=0.15, fontsize=7)
        ax.grid(True, ls="--", alpha=0.3)

    # 1. Constellation size
    axes[0, 0].plot(cal, n_t, "-", color="#00a2ff", lw=2)
    axes[0, 0].fill_between(cal, 0, n_t, alpha=0.15, color="#00a2ff")
    axes[0, 0].set(xlabel="Year", ylabel="Satellites", title="Global constellation size")
    axes[0, 0].grid(True, ls="--", alpha=0.3)
    axes[0, 0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}K"))

    # 2. Missions / replacements
    _plot(axes[0, 1], cal, missions_baseline, missions_sisp, "Missions/yr", "Annual replacement missions")

    # 3. Cumulative cost saved
    axes[0, 2].plot(cal, cost_saved_cum_50, "-", color="#00e5a0", lw=2)
    axes[0, 2].fill_between(cal, 0, cost_saved_cum_50, alpha=0.2, color="#00e5a0")
    axes[0, 2].set(xlabel="Year", ylabel="Savings ($B)", title="Cumulative mission cost savings")
    axes[0, 2].grid(True, ls="--", alpha=0.3)
    axes[0, 2].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.0f}B"))

    # 4. CO2
    _plot(axes[1, 0], cal, co2_baseline_cum, co2_sisp_cum, "CO₂ (Mt)", "Cumulative CO₂ from launches")

    # 5. Sensor-years recovered
    axes[1, 1].plot(cal, sensor_years_saved_cum / 1e6, "-", color="#ffcc00", lw=2)
    axes[1, 1].fill_between(cal, 0, sensor_years_saved_cum / 1e6, alpha=0.2, color="#ffcc00")
    axes[1, 1].set(xlabel="Year", ylabel="Sensor-years (M)", title="Cumulative sensor-years saved via borrowing")
    axes[1, 1].grid(True, ls="--", alpha=0.3)

    # 6. Energy savings
    axes[1, 2].plot(cal, energy_saved_cum_twh, "-", color="#cc44ff", lw=2)
    axes[1, 2].fill_between(cal, 0, energy_saved_cum_twh, alpha=0.2, color="#cc44ff")
    axes[1, 2].set(xlabel="Year", ylabel="TWh", title="Cumulative energy saved (ISL relay efficiency)")
    axes[1, 2].grid(True, ls="--", alpha=0.3)

    plt.tight_layout()
    st.pyplot(fig50)

    st.markdown("---")
    st.markdown("### 50-Year Summary")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Missions avoided", f"{missions_avoided_cum[-1]:,.0f}",
                  f"over 50 years")
    with c2:
        st.metric("Cost saved", f"${cost_saved_cum_50[-1]:.0f}B",
                  "cumulative")
    with c3:
        co2_gap = co2_baseline_cum[-1] - co2_sisp_cum[-1]
        st.metric("CO₂ avoided", f"{co2_gap:.0f} Mt",
                  "cumulative")
    with c4:
        st.metric("Sensor-years saved", f"{sensor_years_saved_cum[-1]/1e6:.1f}M",
                  "via borrowing")
    with c5:
        st.metric("Energy saved", f"{energy_saved_cum_twh[-1]:.1f} TWh",
                  "relay efficiency")

    st.markdown("---")
    st.markdown("### Vision: The SISP Ecosystem in 2075")
    st.markdown(f"""
> By 2075, the global satellite fleet has grown to **{n_t[-1]/1000:.0f}K satellites**
> under the {growth_label.lower()} scenario. Without SISP, maintaining this fleet requires
> **{missions_baseline[-1]:,.0f} replacement missions per year** — an unsustainable pace.
>
> With SISP, the fleet becomes **self-healing**: satellites borrow sensors from neighbours,
> relay data across visibility gaps, and coordinate corrections autonomously.
> Only **{missions_sisp[-1]:,.0f} missions/year** are needed — a reduction of
> **{(1-missions_sisp[-1]/missions_baseline[-1])*100:.0f}%**.
>
> The cumulative savings — **${cost_saved_cum_50[-1]:.0f}B** and **{co2_gap:.0f} Mt CO₂** —
> represent not just operational efficiency, but the foundation of a
> **modular, sustainable, cooperative space economy**.
>
> Every satellite improves every other satellite. The protocol is the product.
""")
