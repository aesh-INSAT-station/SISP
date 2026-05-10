# Correction Algorithms: Weighted Median, Kalman, Hybrid

**Source files:**
- `c++ implemnetation/include/sisp_correction.hpp` — Interface + structs
- `c++ implemnetation/src/sisp_correction.cpp` — Implementations
- `all_tests/test_kalman_gaussian_3sat.py` — Algorithm demo
- `all_tests/test_noise_weighting_and_algorithms.py` — Full comparison benchmark

---

## Architecture: Pluggable Filter Interface

All correction algorithms implement a single C++ interface:

```cpp
struct CorrectionInput {
    Vec3Reading readings[8];   // up to 8 neighbour sensor values (x, y, z, ts_ms)
    float       weights[8];    // DEGR-derived trust weights [0.05, 1.0]
    uint8_t     count;         // number of valid readings
};

struct CorrectionOutput {
    Vec3Reading corrected;     // corrected (x, y, z) estimate
    float       confidence;    // 0.0–1.0 (count / 8)
    uint8_t     used_count;
};

class CorrectionFilter {
public:
    virtual bool apply(const CorrectionInput& in, CorrectionOutput& out) = 0;
};
```

The active filter is set via `sim_use_kalman_filter()`, `sim_use_weighted_median_filter()`, or `sim_use_hybrid_filter()`. If no filter is set, the state machine falls back to a plain weighted average.

---

## DEGR Weighting

Before any filter runs, the state machine computes a weight for each neighbour response:

$$w_i = \max(0.05,\; 1 - \mathrm{DEGR}_i / 15)$$

| DEGR | Weight |
|---|---|
| 0 (healthy) | 1.000 |
| 4 | 0.733 |
| 8 | 0.467 |
| 12 | 0.200 |
| 14 | 0.067 |
| 15 (failed) | 0.050 (clamped) |

The 0.05 floor prevents zero-weight inputs from being silently ignored. This weighting model (inverse_error) was validated to give 17.8% better steady-state error than neutral (equal) weighting.

---

## Algorithm 1: Weighted Median Filter

### Method

For each axis $a \in \{x, y, z\}$ independently:
1. Sort readings $\{r_{i,a}\}$ by value.
2. Accumulate weights from smallest to largest.
3. Return the value where cumulative weight first reaches 50% of total.

```
Sorted readings: [-2, 0, 1, 3, 5]
Weights:         [0.2, 0.8, 1.0, 0.5, 0.3]  → total = 2.8, 50% = 1.4
Cumulative:      [0.2, 1.0, ...]             → crosses 1.4 at r=1  → output: 1
```

### Properties
- **Breakdown point:** 50% — up to half the inputs can be arbitrarily corrupted without affecting the output.
- **No state:** Purely functional, no memory between rounds.
- **Complexity:** $O(n \log n)$ per axis.

### When to use
Best in scenarios with symmetric, low-level noise and up to half the peers badly corrupted. **Degrades significantly at high noise** — see benchmark results below.

---

## Algorithm 2: Kalman Filter

### State Model

6-state constant-velocity model: $\mathbf{x} = [x, y, z, \dot{x}, \dot{y}, \dot{z}]^\top$

State transition (identity, no motion model assumed between corrections):

$$\mathbf{x}_{k|k-1} = \mathbf{x}_{k-1}, \quad P_{k|k-1} = P_{k-1} + Q$$

Measurement model (observe position only):

$$H = [I_3 \;\; 0_3], \quad \mathbf{z} = H\mathbf{x} + \mathbf{v}, \quad \mathbf{v} \sim \mathcal{N}(0, R_{\text{eff}})$$

### DEGR-Aware Measurement Noise

The effective measurement noise is inflated by the average neighbourhood degradation:

$$R_{\text{eff}} = r \cdot \left(1 + \frac{\bar{D}}{4}\right), \quad \bar{D} = \frac{\sum_i w_i D_i}{\sum_i w_i}$$

This makes the filter appropriately cautious when the neighbourhood is degraded.

### Kalman Update

Standard equations with a numerically stable $3 \times 3$ matrix inversion using explicit determinant:

$$K = P_{k|k-1} H^\top (H P_{k|k-1} H^\top + R_{\text{eff}})^{-1}$$
$$\mathbf{x}_k = \mathbf{x}_{k|k-1} + K(\mathbf{z}_k - H\mathbf{x}_{k|k-1})$$
$$P_k = (I - KH) P_{k|k-1}$$

### Default Parameters

| Parameter | Value | Effect |
|---|---|---|
| Process noise `q` | 0.02 | Low → trust state model |
| Measurement noise `r` | 0.8 | Moderate → weight measurements fairly |
| Initial covariance | $10 \cdot I_6$ | High → start uncertain, converge quickly |

### When to use
Optimal for Gaussian noise at any level. Best single-algorithm choice for most scenarios.

---

## Algorithm 3: Hybrid Filter (Recommended for Production)

Chains Weighted Median → Kalman:

```
Input readings
    │
    ▼
Weighted Median (robust outlier rejection)
    │  median output (clean 3-vector)
    ▼
Kalman update (temporal smoothing + drift tracking)
    │
    ▼
Output corrected estimate
```

The median pre-filter removes gross outliers before they can corrupt the Kalman state. Kalman provides temporal smoothing and drift compensation.

**Performance:** Competitive with pure Kalman in Gaussian noise, better than pure Kalman for persistent biases and mixed fault scenarios.

---

## Algorithm 4: NIS-Gated Kalman

Adds a chi-square gate at the Kalman measurement update step. Before updating the state, the Normalized Innovation Squared is checked:

$$\text{NIS} = (\mathbf{z} - H\mathbf{x}_{k|k-1})^\top S^{-1} (\mathbf{z} - H\mathbf{x}_{k|k-1}), \quad S = H P H^\top + R$$

If $\text{NIS} > \chi^2_{3,\,0.95} = 7.815$, the measurement is rejected and the state propagates without update.

**Best for:** Scenarios with one persistently biased satellite. Poor for high symmetric noise (too many rejections).

---

## Benchmark Results

From `test_noise_weighting_and_algorithms.py` — 90 rounds, ground truth $(42, -17.5, 9.25)$, balanced neighbourhood (4 responders):

### Steady-state gain over raw (no correction), σ=20 noise:

| Algorithm | Corrected error | Raw error | Gain |
|---|---|---|---|
| Weighted Median | 21.18 | 21.73 | +0.54 |
| Kalman | 9.40 | 21.73 | **+12.3** |
| NIS-Gated Kalman | 9.40 | 21.73 | **+12.3** |
| Hybrid | 9.58 | 21.73 | **+12.2** |

### Outlier burst stress (15% of rounds: 5× spike in one sensor):

| Algorithm | Corrected error | Gain |
|---|---|---|
| Weighted Median | 15.73 | +3.51 |
| Kalman | 6.04 | **+13.20** |
| NIS-Gated Kalman | 5.99 | **+13.26** |
| Hybrid | 6.88 | **+12.36** |

### Persistent bias (one satellite always reports +40 offset):

| Algorithm | Corrected error | Gain |
|---|---|---|
| Weighted Median | 13.09 | **+18.11** |
| Kalman | 14.94 | +16.27 |
| NIS-Gated Kalman | 31.50 | −0.30 (hurt!) |
| Hybrid | 9.88 | **+21.33** |

**Key takeaways:**
- Kalman is best for Gaussian noise at all levels.
- Weighted Median degrades at high noise but handles persistent bias reasonably.
- NIS-Gated Kalman is hurt by persistent bias (the innovation is always large, so measurements are always rejected).
- **Hybrid is the safest choice for unknown noise environments.**

---

## 30-Day Long-Term Result

From `test_integration_matrix_it02_it03_it05_it06.py` IT-05:

| | RMSE |
|---|---|
| Raw (no correction) | 8.909 |
| Kalman corrected | **0.504** |
| **Improvement** | **94.3%** |

The Kalman velocity states track and compensate 0.5 nT/day systematic drift over 30 days.

---

## Python API

```python
# Use Kalman with tuned parameters
lib.sim_use_kalman_filter(ctx, 0.02, 0.8)   # (process_noise, measurement_noise)

# Use weighted median
lib.sim_use_weighted_median_filter(ctx)

# Use hybrid (recommended for production)
lib.sim_use_hybrid_filter(ctx, 0.02, 0.8)

# Inject a synthetic correction response for testing
lib.sim_inject_correction_rsp(ctx, sndr=2, seq=1, degr=0,
    sensor_type=1, x=42.1, y=-17.3, z=9.4, ts_ms=1000)

# Read corrected output
out = (ctypes.c_float * 3)()
lib.sim_get_corrected(ctx, out)
print(out[0], out[1], out[2])
```
