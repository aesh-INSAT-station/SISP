#pragma once

#include "sisp_protocol.hpp"
#include <array>
#include <cstdint>
#include <vector>

namespace SISP {

/**
 * Satellite Inter-Service Protocol (SISP)
 * Correction Filter Module
 *
 * This module is responsible for taking weighted sensor readings and
 * computing corrected values. It is intentionally separate from the
 * protocol layer to allow different correction algorithms to be plugged
 * in without affecting the transport/state-machine behavior.
 *
 * The protocol layer (state machine) simply collects readings and their
 * weights, then calls a correction algorithm to produce the final value.
 */

/**
 * Correction context holds sensor readings and weights for processing.
 */
struct CorrectionInput {
    std::array<Vec3Reading, 8> readings;
    std::array<float, 8> weights;      // Per-neighbor weight (0.0 to 1.0)
    uint8_t count;                     // How many readings are valid
};

/**
 * Output after correction has been applied.
 */
struct CorrectionOutput {
    Vec3Reading corrected;             // Final result
    float confidence;                  // 0.0 = low, 1.0 = high
    uint8_t used_count;                // How many readings influenced result
};

/**
 * Base class for correction algorithms.
 * Subclass this to implement different filtering strategies.
 */
class CorrectionFilter {
public:
    virtual ~CorrectionFilter() = default;

    /**
     * Apply the correction algorithm to weighted readings.
     *
     * @param input  Collected readings with weights
     * @param output Result (must be populated by implementation)
     * @return true if correction succeeded, false if insufficient data
     */
    virtual bool apply(const CorrectionInput& input, CorrectionOutput& output) = 0;
};

/**
 * Weighted median filter: sorts readings by value and selects the
 * point where cumulative weight crosses 50%.
 *
 * Good for: robust filtering, outlier rejection, real-time constraint.
 * Signal is in the readings; weight represents confidence in each reading.
 */
class WeightedMedianFilter : public CorrectionFilter {
public:
    bool apply(const CorrectionInput& input, CorrectionOutput& output) override;

private:
    float compute_1d_median(const std::array<Vec3Reading, 8>& readings,
                            const std::array<float, 8>& weights,
                            uint8_t count,
                            size_t axis);
};

/**
 * Kalman filter: state-space estimation with process and measurement noise.
 *
 * Good for: temporal smoothing, noise reduction, dynamic state estimation.
 * Requires tuning of Q (process noise) and R (measurement noise).
 */
class KalmanFilter : public CorrectionFilter {
public:
    KalmanFilter(float process_noise = 0.01f, float measurement_noise = 1.0f);
    ~KalmanFilter() override = default;

    bool apply(const CorrectionInput& input, CorrectionOutput& output) override;

    void reset();
    void set_state(const Vec3Reading& x);

private:
    // State: [x, y, z, vx, vy, vz]^T (position + velocity)
    std::array<float, 6> state;
    std::array<std::array<float, 6>, 6> covariance;

    float q;  // Process noise
    float r;  // Measurement noise
};

/**
 * Hybrid filter: uses weighted median for robust outlier rejection,
 * then applies light Kalman smoothing on the result.
 *
 * Good for: production scenarios with mixed quality data.
 */
class HybridFilter : public CorrectionFilter {
public:
    HybridFilter(float kalman_process_noise = 0.01f,
                 float kalman_measurement_noise = 1.0f);
    ~HybridFilter() override = default;

    bool apply(const CorrectionInput& input, CorrectionOutput& output) override;

    void reset();

private:
    WeightedMedianFilter median_filter;
    KalmanFilter kalman_filter;
};

}  // namespace SISP
