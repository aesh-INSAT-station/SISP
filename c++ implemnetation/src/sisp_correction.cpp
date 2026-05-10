#include "sisp_correction.hpp"
#include <algorithm>
#include <cmath>

namespace SISP {

/* ■■ Weighted Median Filter ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

float WeightedMedianFilter::compute_1d_median(const std::array<Vec3Reading, 8>& readings,
                                              const std::array<float, 8>& weights,
                                              uint8_t count,
                                              size_t axis) {
    std::array<size_t, 8> order{};
    std::array<float, 8> sorted_values{};
    std::array<float, 8> sorted_weights{};

    for (uint8_t i = 0; i < count; ++i) {
        order[i] = i;
    }

    std::sort(order.begin(), order.begin() + count, [&](size_t lhs, size_t rhs) {
        float lhs_val = (axis == 0) ? readings[lhs].x : (axis == 1) ? readings[lhs].y : readings[lhs].z;
        float rhs_val = (axis == 0) ? readings[rhs].x : (axis == 1) ? readings[rhs].y : readings[rhs].z;
        return lhs_val < rhs_val;
    });

    float total_weight = 0.0f;
    for (uint8_t i = 0; i < count; ++i) {
        sorted_values[i] = (axis == 0) ? readings[order[i]].x 
                         : (axis == 1) ? readings[order[i]].y 
                         : readings[order[i]].z;
        sorted_weights[i] = std::max(0.0f, weights[order[i]]);
        total_weight += sorted_weights[i];
    }

    if (total_weight <= 0.0f) {
        return 0.0f;
    }

    float cumulative = 0.0f;
    for (uint8_t i = 0; i < count; ++i) {
        cumulative += sorted_weights[i];
        if (cumulative >= (total_weight * 0.5f)) {
            return sorted_values[i];
        }
    }

    return sorted_values[count - 1];
}

bool WeightedMedianFilter::apply(const CorrectionInput& input, CorrectionOutput& output) {
    if (input.count == 0) {
        output.corrected.x = 0.0f;
        output.corrected.y = 0.0f;
        output.corrected.z = 0.0f;
        output.confidence = 0.0f;
        output.used_count = 0;
        return false;
    }

    output.corrected.x = compute_1d_median(input.readings, input.weights, input.count, 0);
    output.corrected.y = compute_1d_median(input.readings, input.weights, input.count, 1);
    output.corrected.z = compute_1d_median(input.readings, input.weights, input.count, 2);

    float total_weight = 0.0f;
    for (uint8_t i = 0; i < input.count; ++i) {
        total_weight += input.weights[i];
    }
    output.confidence = std::min(1.0f, total_weight / 8.0f);
    output.used_count = input.count;

    return true;
}

/* ■■ Kalman Filter ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

KalmanFilter::KalmanFilter(float process_noise, float measurement_noise)
    : q(process_noise), r(measurement_noise) {
    reset();
}

void KalmanFilter::reset() {
    state = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
    
    // Initialize covariance: high uncertainty initially
    for (size_t i = 0; i < 6; ++i) {
        for (size_t j = 0; j < 6; ++j) {
            covariance[i][j] = (i == j) ? 10.0f : 0.0f;
        }
    }
}

void KalmanFilter::set_state(const Vec3Reading& x) {
    state[0] = x.x;
    state[1] = x.y;
    state[2] = x.z;
}

bool KalmanFilter::apply(const CorrectionInput& input, CorrectionOutput& output) {
    if (input.count == 0) {
        output.corrected.x = state[0];
        output.corrected.y = state[1];
        output.corrected.z = state[2];
        output.confidence = 0.0f;
        output.used_count = 0;
        return false;
    }

    // Simple 1D Kalman per axis (decoupled for efficiency)
    // Simplified: just use weighted average of current readings as measurement
    float meas_x = 0.0f, meas_y = 0.0f, meas_z = 0.0f;
    float total_w = 0.0f;
    for (uint8_t i = 0; i < input.count; ++i) {
        float w = input.weights[i];
        meas_x += input.readings[i].x * w;
        meas_y += input.readings[i].y * w;
        meas_z += input.readings[i].z * w;
        total_w += w;
    }
    if (total_w > 0.0f) {
        meas_x /= total_w;
        meas_y /= total_w;
        meas_z /= total_w;
    }

    // Simplified update: blend state with measurement
    // Real Kalman would use full covariance update; this is a lightweight approximation
    float alpha = 0.3f;  // Measurement trust weight
    state[0] = state[0] * (1.0f - alpha) + meas_x * alpha;
    state[1] = state[1] * (1.0f - alpha) + meas_y * alpha;
    state[2] = state[2] * (1.0f - alpha) + meas_z * alpha;

    output.corrected.x = state[0];
    output.corrected.y = state[1];
    output.corrected.z = state[2];
    output.confidence = std::min(1.0f, total_w / 8.0f);
    output.used_count = input.count;

    return true;
}

/* ■■ Hybrid Filter ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

HybridFilter::HybridFilter(float kalman_process_noise, float kalman_measurement_noise)
    : kalman_filter(kalman_process_noise, kalman_measurement_noise) {
}

bool HybridFilter::apply(const CorrectionInput& input, CorrectionOutput& output) {
    // Step 1: Weighted median for robustness
    CorrectionOutput median_result{};
    if (!median_filter.apply(input, median_result)) {
        output = median_result;
        return false;
    }

    // Step 2: Light Kalman smoothing on the median result
    CorrectionInput kalman_input{};
    kalman_input.readings[0] = median_result.corrected;
    kalman_input.weights[0] = median_result.confidence;
    kalman_input.count = 1;

    return kalman_filter.apply(kalman_input, output);
}

void HybridFilter::reset() {
    kalman_filter.reset();
}

}  // namespace SISP
