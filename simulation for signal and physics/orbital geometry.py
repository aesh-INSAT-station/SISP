import numpy as np
from skyfield.api import load, EarthSatellite

def calculate_orbital_visibility():
    print("--- SISP Module M1: Orbital Geometry Simulation ---")
    
    # Load timescale and ephemeris
    ts = load.timescale()
    
    # Sample TLEs (Two satellites in roughly similar LEO orbits, slightly offset)
    # Using generic Starlink-like orbital parameters for realism
    tle1_l1 = "1 45176U 20001A   23274.50000000  .00000000  00000-0  00000-0 0  9998"
    tle1_l2 = "2 45176  53.0000 180.0000 0001000   0.0000   0.0000 15.00000000    05"
    
    tle2_l1 = "1 45177U 20001B   23274.50000000  .00000000  00000-0  00000-0 0  9999"
    tle2_l2 = "2 45177  53.0000 185.0000 0001000   0.0000   0.0000 15.00000000    04"

    sat_A = EarthSatellite(tle1_l1, tle1_l2, 'Sat A', ts)
    sat_B = EarthSatellite(tle2_l1, tle2_l2, 'Sat B', ts)

    # Simulate over one typical LEO orbit (90 minutes), step every 1 minute
    t = ts.utc(2026, 4, 19, 13, range(91))

    # Get ECI Positions and Velocities (in km and km/s)
    state_A = sat_A.at(t)
    state_B = sat_B.at(t)
    
    pos_A = state_A.position.km
    pos_B = state_B.position.km
    vel_A = state_A.velocity.km_per_s
    vel_B = state_B.velocity.km_per_s

    # Earth Exclusion Parameters
    R_earth = 6371.0 # km
    h_atm = 100.0    # km clearance
    R_excl = R_earth + h_atm
    
    f_c = 26e9 # Ka-band (26 GHz)
    c_km = 299792.458 # Speed of light in km/s

    print("\nSimulating 90 minutes of orbital data...")
    print(f"{'Time (min)':<12} | {'LoS Clear?':<12} | {'Slant Range (km)':<18} | {'Doppler Shift (kHz)':<20}")
    print("-" * 70)

    in_window = False
    window_start = 0

    for i in range(len(t)):
        rA_vec = pos_A[:, i]
        rB_vec = pos_B[:, i]
        vA_vec = vel_A[:, i]
        vB_vec = vel_B[:, i]

        rA_mag = np.linalg.norm(rA_vec)
        rB_mag = np.linalg.norm(rB_vec)

        # 1. Calculate Line of Sight (Earth Blockage)
        dot_prod = np.dot(rA_vec, rB_vec) / (rA_mag * rB_mag)
        gamma = np.arccos(np.clip(dot_prod, -1.0, 1.0))
        gamma_max = np.arccos(R_excl / rA_mag) + np.arccos(R_excl / rB_mag)
        
        los_clear = gamma < gamma_max

        # 2. Calculate Slant Range
        d_vec = rB_vec - rA_vec
        d_mag = np.linalg.norm(d_vec)

        # 3. Calculate Range Rate (Doppler)
        v_rel_vec = vB_vec - vA_vec
        range_rate = np.dot(d_vec, v_rel_vec) / d_mag # km/s
        
        # Doppler shift calculation: f_shift = f_c * (range_rate / c)
        doppler_hz = f_c * (range_rate / c_km)
        doppler_khz = doppler_hz / 1000.0

        # Output specific milestones to console (every 10 mins or on state change)
        if los_clear and not in_window:
            in_window = True
            window_start = i
            print(f"{i:<12} | {'YES (OPEN)':<12} | {d_mag:<18.2f} | {doppler_khz:<20.2f}")
        elif not los_clear and in_window:
            in_window = False
            print(f"{i:<12} | {'NO (CLOSE)':<12} | {d_mag:<18.2f} | {doppler_khz:<20.2f}")
            print(f"--> Visibility Window Lasted {i - window_start} minutes.\n")
        elif i % 15 == 0:
            status = "YES" if los_clear else "NO"
            print(f"{i:<12} | {status:<12} | {d_mag:<18.2f} | {doppler_khz:<20.2f}")

if __name__ == "__main__":
    calculate_orbital_visibility()