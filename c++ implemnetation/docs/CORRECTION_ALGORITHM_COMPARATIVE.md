# Correction Algorithm Comparative Analysis

## Scope
This document compares five correction paths used in the simulation harness:
- raw (weighted average fallback)
- weighted_median
- kalman
- gated_kalman (benchmark-side innovation gate)
- hybrid (weighted median plus Kalman smoothing)

The analysis is based on results produced by all_tests/test_noise_weighting_and_algorithms.py.

## Mathematical intuition

### 1) Raw weighted average
Estimator is mean-like and minimizes squared error under Gaussian assumptions.
It is simple but sensitive to large outliers.

### 2) Weighted median
For each axis independently, it picks the value where cumulative weight crosses 50 percent.
This is robust to spikes because extreme samples do not dominate the estimate as strongly as with a mean.

### 3) Kalman
State model combines prediction plus measurement update with covariance propagation.
Strength: temporal smoothing and noise suppression.
Weakness: if outliers are frequent or persistent and not explicitly rejected, innovations can still bias the state.

### 4) Gated Kalman (in benchmark)
Same Kalman core, but benchmark-side logic marks very large innovation samples as DEGR 15.
Strength: better on impulsive spikes.
Weakness: can over-reject under persistent bias and lose useful measurement information.

### 5) Hybrid
Pipeline:
1. weighted median creates robust measurement summary
2. Kalman smooths that robust summary in time
This combines outlier resistance and temporal smoothing.

## Scenario matrix used
The benchmark covers:
- balanced Gaussian responders across sigma levels
- one healthy plus one broken responder
- burst_5pct_heavy
- burst_15pct_moderate
- persistent_bias_peer3
- mixed_spike_plus_drift

## Observed comparative behavior

### Balanced and moderate Gaussian noise
- kalman is usually strongest or tied strongest.
- hybrid is close and sometimes best in steady state.
- weighted_median alone is often less accurate when noise is mostly Gaussian.

### Burst outliers
- kalman and gated_kalman improve clearly over raw and weighted_median.
- hybrid is typically best or tied best due to robust front-end plus smoothing.

### Persistent bias
- weighted_median and hybrid are strong.
- gated_kalman can collapse if the gate rejects too aggressively.

### Mixed spike plus drift
- hybrid is strongest in the reported run.
- kalman and gated_kalman are close, but hybrid keeps the best combined robustness.

## Practical recommendation
For production-like mixed noise and outlier conditions, prefer hybrid as default.
Use kalman when noise is close to Gaussian and model assumptions hold.
Use gated_kalman only with carefully tuned innovation thresholds, ideally with adaptive gates.

## Where this is implemented
- C++ correction implementations: c++ implemnetation/src/sisp_correction.cpp
- C++ correction interfaces: c++ implemnetation/include/sisp_correction.hpp
- Python comparison harness: all_tests/test_noise_weighting_and_algorithms.py

## Suggested next improvements
- Add adaptive chi-square innovation gate (NIS-based) instead of fixed thresholds.
- Export benchmark results to CSV for plotting and trend comparison.
- Add missing-data and dropout scenarios for resilience evaluation.
