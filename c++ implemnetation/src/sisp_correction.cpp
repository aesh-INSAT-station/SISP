#include "sisp_correction.hpp"
#include <algorithm>
#include <cmath>

namespace SISP {

namespace {

using Mat3 = std::array<std::array<float, 3>, 3>;
using Mat6 = std::array<std::array<float, 6>, 6>;

static float clampf(float value, float lo, float hi) {
    return std::max(lo, std::min(hi, value));
}

static bool invert_3x3(const Mat3& in, Mat3& out) {
    const float a = in[0][0], b = in[0][1], c = in[0][2];
    const float d = in[1][0], e = in[1][1], f = in[1][2];
    const float g = in[2][0], h = in[2][1], i = in[2][2];

    const float A = (e * i) - (f * h);
    const float B = -((d * i) - (f * g));
    const float C = (d * h) - (e * g);
    const float D = -((b * i) - (c * h));
    const float E = (a * i) - (c * g);
    const float F = -((a * h) - (b * g));
    const float G = (b * f) - (c * e);
    const float H = -((a * f) - (c * d));
    const float I = (a * e) - (b * d);

    const float det = (a * A) + (b * B) + (c * C);
    if (std::fabs(det) < 1e-9f) {
        return false;
    }

    const float inv_det = 1.0f / det;
    out[0][0] = A * inv_det;
    out[0][1] = D * inv_det;
    out[0][2] = G * inv_det;
    out[1][0] = B * inv_det;
    out[1][1] = E * inv_det;
    out[1][2] = H * inv_det;
    out[2][0] = C * inv_det;
    out[2][1] = F * inv_det;
    out[2][2] = I * inv_det;
    return true;
}

}  // namespace

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
        output.corrected.ts_ms = 0;
        output.confidence = 0.0f;
        output.used_count = 0;
        return false;
    }

    output.corrected.x = compute_1d_median(input.readings, input.weights, input.count, 0);
    output.corrected.y = compute_1d_median(input.readings, input.weights, input.count, 1);
    output.corrected.z = compute_1d_median(input.readings, input.weights, input.count, 2);

    float total_weight = 0.0f;
    uint32_t latest_ts_ms = 0;
    for (uint8_t i = 0; i < input.count; ++i) {
        total_weight += input.weights[i];
        latest_ts_ms = std::max(latest_ts_ms, input.readings[i].ts_ms);
    }
    output.corrected.ts_ms = latest_ts_ms;
    output.confidence = std::min(1.0f, total_weight / 8.0f);
    output.used_count = input.count;

    return true;
}

/* ■■ Kalman Filter ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■ */

KalmanFilter::KalmanFilter(float process_noise, float measurement_noise)
    : q(process_noise), r(measurement_noise), last_update_ts_ms(0), has_last_update_ts(false) {
    reset();
}

void KalmanFilter::reset() {
    state = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
    last_update_ts_ms = 0;
    has_last_update_ts = false;
    
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
    state[3] = 0.0f;
    state[4] = 0.0f;
    state[5] = 0.0f;
    last_update_ts_ms = x.ts_ms;
    has_last_update_ts = (x.ts_ms > 0);
}

bool KalmanFilter::apply(const CorrectionInput& input, CorrectionOutput& output) {
    if (input.count == 0) {
        output.corrected.x = state[0];
        output.corrected.y = state[1];
        output.corrected.z = state[2];
        output.corrected.ts_ms = has_last_update_ts ? last_update_ts_ms : 0;
        output.confidence = 0.0f;
        output.used_count = 0;
        return false;
    }

    // Build weighted measurement from neighbour readings.
    float meas_x = 0.0f, meas_y = 0.0f, meas_z = 0.0f;
    float meas_ts = 0.0f;
    float total_w = 0.0f;
    bool has_measurement_ts = false;
    for (uint8_t i = 0; i < input.count; ++i) {
        float w = std::max(0.0f, input.weights[i]);
        if (w <= 0.0f) {
            continue;
        }
        meas_x += input.readings[i].x * w;
        meas_y += input.readings[i].y * w;
        meas_z += input.readings[i].z * w;
        meas_ts += static_cast<float>(input.readings[i].ts_ms) * w;
        has_measurement_ts = has_measurement_ts || (input.readings[i].ts_ms > 0);
        total_w += w;
    }
    if (total_w <= 0.0f) {
        output.corrected.x = state[0];
        output.corrected.y = state[1];
        output.corrected.z = state[2];
        output.corrected.ts_ms = has_last_update_ts ? last_update_ts_ms : 0;
        output.confidence = 0.0f;
        output.used_count = 0;
        return false;
    }

    meas_x /= total_w;
    meas_y /= total_w;
    meas_z /= total_w;

    uint32_t meas_ts_ms = has_last_update_ts ? (last_update_ts_ms + 1000U) : 0U;
    if (has_measurement_ts) {
        meas_ts_ms = static_cast<uint32_t>((meas_ts / total_w) + 0.5f);
    }

    float dt_s = 1.0f;
    if (has_last_update_ts && meas_ts_ms > last_update_ts_ms) {
        dt_s = static_cast<float>(meas_ts_ms - last_update_ts_ms) / 1000.0f;
    }
    dt_s = clampf(dt_s, 0.01f, 5.0f);

    // Predict step with constant velocity model.
    std::array<float, 6> x_pred = state;
    x_pred[0] += state[3] * dt_s;
    x_pred[1] += state[4] * dt_s;
    x_pred[2] += state[5] * dt_s;

    Mat6 F{};
    for (size_t i = 0; i < 6; ++i) {
        F[i][i] = 1.0f;
    }
    F[0][3] = dt_s;
    F[1][4] = dt_s;
    F[2][5] = dt_s;

    Mat6 FP{};
    Mat6 P_pred{};
    for (size_t i = 0; i < 6; ++i) {
        for (size_t j = 0; j < 6; ++j) {
            float acc = 0.0f;
            for (size_t k = 0; k < 6; ++k) {
                acc += F[i][k] * covariance[k][j];
            }
            FP[i][j] = acc;
        }
    }
    for (size_t i = 0; i < 6; ++i) {
        for (size_t j = 0; j < 6; ++j) {
            float acc = 0.0f;
            for (size_t k = 0; k < 6; ++k) {
                acc += FP[i][k] * F[j][k];  // multiply by F^T
            }
            P_pred[i][j] = acc;
        }
    }

    const float q_eff = std::max(1e-6f, q);
    const float dt2 = dt_s * dt_s;
    const float dt3 = dt2 * dt_s;
    const float dt4 = dt2 * dt2;
    for (size_t axis = 0; axis < 3; ++axis) {
        const size_t p = axis;
        const size_t v = axis + 3;
        P_pred[p][p] += 0.25f * dt4 * q_eff;
        P_pred[p][v] += 0.5f * dt3 * q_eff;
        P_pred[v][p] += 0.5f * dt3 * q_eff;
        P_pred[v][v] += dt2 * q_eff;
    }

    // Measurement update on position components [x, y, z].
    std::array<float, 3> innovation{};
    innovation[0] = meas_x - x_pred[0];
    innovation[1] = meas_y - x_pred[1];
    innovation[2] = meas_z - x_pred[2];

    Mat3 S{};
    for (size_t i = 0; i < 3; ++i) {
        for (size_t j = 0; j < 3; ++j) {
            S[i][j] = P_pred[i][j];
        }
    }
    const float r_eff = std::max(1e-6f, r / std::max(total_w, 0.05f));
    S[0][0] += r_eff;
    S[1][1] += r_eff;
    S[2][2] += r_eff;

    Mat3 S_inv{};
    if (!invert_3x3(S, S_inv)) {
        state = x_pred;
        covariance = P_pred;
        output.corrected.x = state[0];
        output.corrected.y = state[1];
        output.corrected.z = state[2];
        output.corrected.ts_ms = meas_ts_ms;
        output.confidence = std::min(1.0f, total_w / 8.0f);
        output.used_count = input.count;
        if (has_measurement_ts || has_last_update_ts) {
            last_update_ts_ms = meas_ts_ms;
            has_last_update_ts = true;
        }
        return true;
    }

    std::array<std::array<float, 3>, 6> K{};
    for (size_t i = 0; i < 6; ++i) {
        for (size_t j = 0; j < 3; ++j) {
            float acc = 0.0f;
            for (size_t k = 0; k < 3; ++k) {
                acc += P_pred[i][k] * S_inv[k][j];
            }
            K[i][j] = acc;
        }
    }

    std::array<float, 6> x_new{};
    for (size_t i = 0; i < 6; ++i) {
        x_new[i] = x_pred[i]
            + (K[i][0] * innovation[0])
            + (K[i][1] * innovation[1])
            + (K[i][2] * innovation[2]);
    }

    Mat6 I_minus_KH{};
    for (size_t i = 0; i < 6; ++i) {
        for (size_t j = 0; j < 6; ++j) {
            float value = (i == j) ? 1.0f : 0.0f;
            if (j < 3) {
                value -= K[i][j];
            }
            I_minus_KH[i][j] = value;
        }
    }

    Mat6 temp{};
    Mat6 P_new{};
    for (size_t i = 0; i < 6; ++i) {
        for (size_t j = 0; j < 6; ++j) {
            float acc = 0.0f;
            for (size_t k = 0; k < 6; ++k) {
                acc += I_minus_KH[i][k] * P_pred[k][j];
            }
            temp[i][j] = acc;
        }
    }
    for (size_t i = 0; i < 6; ++i) {
        for (size_t j = 0; j < 6; ++j) {
            float acc = 0.0f;
            for (size_t k = 0; k < 6; ++k) {
                acc += temp[i][k] * I_minus_KH[j][k];  // multiply by (I-KH)^T
            }
            P_new[i][j] = acc;
        }
    }

    for (size_t i = 0; i < 6; ++i) {
        for (size_t j = 0; j < 6; ++j) {
            float acc = 0.0f;
            for (size_t k = 0; k < 3; ++k) {
                acc += K[i][k] * r_eff * K[j][k];
            }
            P_new[i][j] += acc;
        }
    }

    for (size_t i = 0; i < 6; ++i) {
        for (size_t j = i + 1; j < 6; ++j) {
            const float avg = 0.5f * (P_new[i][j] + P_new[j][i]);
            P_new[i][j] = avg;
            P_new[j][i] = avg;
        }
    }

    state = x_new;
    covariance = P_new;

    if (has_measurement_ts || has_last_update_ts) {
        last_update_ts_ms = meas_ts_ms;
        has_last_update_ts = true;
    }

    output.corrected.x = state[0];
    output.corrected.y = state[1];
    output.corrected.z = state[2];
    output.corrected.ts_ms = has_last_update_ts ? last_update_ts_ms : 0;
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
