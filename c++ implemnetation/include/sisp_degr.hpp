#pragma once

#include "sisp_protocol.hpp"

namespace SISP {

/* ■■ DEGR Computation (Section 9) ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

/**
 * Compute the degradation metric (0-15) from four sources:
 * 
 * @param k_factor      Kalman correction coefficient (1.0 = healthy)
 * @param svd_residual  Normalized residual from SVD fault detector (0.0-1.0)
 * @param age_days      Satellite mission age in days
 * @param orbit_error_m Deviation from nominal orbit in metres (from ADCS)
 * @return              DEGR value (0=healthy, 15=critically degraded)
 * 
 * Mapping to Kalman filter:
 *   R_eff = R_base × (1 + DEGR/4)
 *   DEGR=0 → R_eff = R_base
 *   DEGR=15 → R_eff = 4.75 × R_base (filter nearly ignores peer)
 */
uint8_t compute_degr(float k_factor, float svd_residual, 
                     uint32_t age_days, float orbit_error_m);

}  // namespace SISP
