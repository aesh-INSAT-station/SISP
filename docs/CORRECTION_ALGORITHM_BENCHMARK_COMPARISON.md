# SISP Correction Algorithm Benchmark Comparison

This document compares the correction algorithms exercised by
`all_tests/test_noise_weighting_and_algorithms.py`.

Cell format in the main table:

`corrected_error / raw_error / gain / converge_round`

- `corrected_error`: steady-state corrected vector error.
- `raw_error`: steady-state raw average vector error.
- `gain`: `raw_error - corrected_error`; higher is better.
- `converge_round`: first round where corrected error is below `2.0`; `-` means it did not converge within the run.

## Algorithms

### WeightedMedian

The native C++ weighted median filter sorts readings independently by axis and selects the value where cumulative DEGR-derived trust weight crosses 50%. It is robust to biased peers when one source remains clearly healthier, but can be noisy with Gaussian inputs because it does not smooth over time.

### Kalman

The native C++ Kalman filter uses a 6-state constant-velocity model:

`[x, y, z, vx, vy, vz]`

It first fuses neighbor readings using DEGR-derived weights, then runs a 3D measurement update. It is the strongest general-purpose smoother in the benchmark.

### NIS-Kalman

The Python benchmark wraps the native C++ Kalman filter with normalized innovation squared gating. When a responder's innovation exceeds an adaptive chi-square threshold, that responder is forced to `DEGR=15` before the Kalman update.

This helps with burst outliers, but can over-reject persistently biased data after the predicted state has already been pulled toward the bad source.

### Hybrid

The native C++ hybrid filter applies weighted median first, then runs Kalman smoothing on the median result. This is strongest in the persistent-bias case because the median step suppresses the biased peer before temporal smoothing.

### DIWKCF

The Distributed Information-Weighted Kalman Consensus Filter variant uses information weighting before Kalman:

`information_weight_i = 1 / sigma_i^2`

where:

`sigma_i = 1 + DEGR_i`

The fused measurement is:

`sum(information_weight_i * x_i) / sum(information_weight_i)`

That fused value is then passed into the same native C++ Kalman filter.

### RANSAC-Kalman

RANSAC-Kalman samples 3 readings, forms a consensus set of readings within `2*sigma` of the sample mean, repeats this 10 times, and passes the best inlier mean into the native C++ Kalman filter.

With only two responders in the current harness, RANSAC is less expressive than it would be in a larger constellation. It still works, but usually trails standard Kalman and Hybrid.

### Gossip-Kalman

The gossip variant performs 5 push-sum-style rounds. Each satellite shares value and weight with a random neighbor:

`value_i = (value_i + value_j) / 2`

`weight_i = (weight_i + weight_j) / 2`

The resulting gossip-weighted average is passed into the native C++ Kalman filter. It is useful as a distributed averaging model, but it can spread a strong persistent bias.

## Benchmark Results

| Scenario | WeightedMedian | Kalman | NIS-Kalman | Hybrid | DIWKCF | RANSAC-Kalman | Gossip-Kalman |
|---|---|---|---|---|---|---|---|
| Gaussian sigma=2 | 2.66/2.43/-0.23/4 | 1.20/2.43/+1.23/4 | 1.20/2.43/+1.23/4 | 1.21/2.43/+1.22/13 | 1.27/2.43/+1.16/1 | 1.66/2.43/+0.77/5 | 1.49/2.43/+0.94/1 |
| Gaussian sigma=20 | 24.29/21.86/-2.44/- | 10.68/21.86/+11.18/- | 10.68/21.86/+11.18/- | 10.51/21.86/+11.35/- | 11.87/21.86/+9.98/- | 15.83/21.86/+6.03/- | 14.07/21.86/+7.79/- |
| Gaussian sigma=60 | 73.18/65.23/-7.95/- | 28.68/65.23/+36.54/- | 28.68/65.23/+36.54/- | 32.11/65.23/+33.11/- | 31.34/65.23/+33.89/- | 49.38/65.23/+15.85/- | 37.50/65.23/+27.72/- |
| Burst outlier 5pct 5x | 10.87/11.52/+0.66/100 | 3.97/11.52/+7.55/16 | 3.98/11.52/+7.54/16 | 5.33/11.52/+6.19/15 | 5.17/11.52/+6.35/34 | 7.37/11.52/+4.16/36 | 6.43/11.52/+5.09/15 |
| Burst outlier 15pct 5x | 12.62/16.79/+4.16/- | 4.44/16.79/+12.35/10 | 4.26/16.79/+12.53/10 | 4.40/16.79/+12.39/9 | 7.28/16.79/+9.50/25 | 14.02/16.79/+2.76/46 | 11.50/16.79/+5.28/10 |
| Persistent bias sat3 +40 | 3.17/34.89/+31.72/6 | 8.57/34.89/+26.32/- | 34.83/34.89/+0.06/- | 1.36/34.89/+33.53/11 | 17.07/34.89/+17.82/- | 29.38/34.89/+5.51/3 | 46.30/34.89/-11.41/- |
| Mixed spike plus drift | 20.45/21.95/+1.50/- | 8.49/21.95/+13.45/12 | 8.35/21.95/+13.60/12 | 9.17/21.95/+12.78/37 | 13.31/21.95/+8.63/15 | 20.02/21.95/+1.92/15 | 21.69/21.95/+0.25/- |

## Scenario Winners

| Scenario | Best Algorithm | Reason |
|---|---|---|
| Gaussian sigma=2 | Kalman / NIS-Kalman | Smooths low-amplitude Gaussian noise without needing outlier rejection. |
| Gaussian sigma=20 | Hybrid | Slightly lower steady-state error than Kalman in this run. |
| Gaussian sigma=60 | Kalman / NIS-Kalman | Strong temporal smoothing gives the largest gain. |
| Burst outlier 5pct 5x | NIS-Kalman | Innovation gating rejects sparse spikes. |
| Burst outlier 15pct 5x | NIS-Kalman | Gating remains useful at higher outlier frequency. |
| Persistent bias sat3 +40 | Hybrid | Median prefilter suppresses the biased responder before smoothing. |
| Mixed spike plus drift | NIS-Kalman | Best steady-state error under combined transient and drifting faults. |

## Main Takeaways

Kalman is the best default for Gaussian noise and high-noise regimes. It consistently improves over raw averaging and scales well as noise increases.

Hybrid is the strongest choice when persistent bias is expected. The median stage prevents the Kalman state from being dragged toward a bad peer.

NIS-Kalman is useful for burst outliers and mixed spike/drift scenarios. It does not automatically solve persistent bias, because a biased estimate can become self-consistent after the state adapts.

DIWKCF is a reasonable middle ground. It improves over raw averaging in all benchmark scenarios, but does not beat Kalman/Hybrid when the native DEGR-weighted Kalman already has good signal.

RANSAC-Kalman would likely benefit from more responders. In the current two-responder harness, its consensus selection has too little redundancy.

Gossip-Kalman is not ideal for persistent bias in this setup because gossip averaging can propagate a bad value through the local consensus.

## Recommendation

For the current SISP correction stack:

1. Use `Hybrid` when persistent sensor bias is a primary mission risk.
2. Use `NIS-Kalman` when burst outliers and mixed transient faults dominate.
3. Use standard `Kalman` as the general baseline for Gaussian noise.
4. Keep `DIWKCF`, `RANSAC-Kalman`, and `Gossip-Kalman` as comparative research algorithms, especially for future tests with more than two responders.

## Large-Constellation Data-Driven Recovery Benchmark

The follow-up rigorous benchmark is implemented in:

`all_tests/test_large_constellation_data_recovery.py`

This test uses real telemetry from:

`data/raw/segments.csv`

The raw scalar telemetry channel `CADC0873` is transformed into a dynamic 3D correction target:

`[value_zscore, rolling_mean_zscore, first_difference_zscore]`

Those features are scaled around the same physical vector range used by the protocol correction tests. Each correction round then creates a larger responder constellation with 3, 5, or 8 satellites. Eight responders is the maximum currently accepted by the C++ correction input buffer.

### Injected Fault Model

The rigorous run includes multiple paper-style disturbance phases:

| Phase | Rounds | Faults |
|---|---:|---|
| Nominal | baseline intervals | Per-satellite Gaussian noise with heterogeneous variance |
| Burst storm | 35-64 | Random high-amplitude spikes across responders |
| Drift + stuck sensor | 70-114 | One satellite drifts persistently, another holds a stale value |
| Dropout + random events | 120-144 | Random responder dropouts plus large random faults |
| Recovery | 145-169 | Drifting satellite gradually returns to the true signal |

### Metrics

Cell format:

`steady_corr / gain / p95_corr / recovery_round_after_fault_end`

- `steady_corr`: average corrected error over the final third of the run.
- `gain`: steady-state raw error minus corrected error.
- `p95_corr`: 95th percentile corrected error across all rounds.
- `recovery_round_after_fault_end`: first round after the recovery phase begins where corrected error falls below the recovery threshold.

### Large-Constellation Results

| Satellites | weighted_median | kalman | nis_gated_kalman | hybrid | diwkcf | ransac_kalman | gossip_kalman |
|---|---|---|---|---|---|---|---|
| 3 | 1.92/+2.71/3.30/0 | 3.54/+1.09/5.77/0 | 4.47/+0.16/9.69/0 | 3.63/+1.00/6.04/0 | 4.09/+0.54/6.04/0 | 3.83/+0.80/6.86/0 | 6.37/-1.74/16.27/0 |
| 5 | 1.56/+3.02/4.24/0 | 3.38/+1.20/4.58/0 | 3.02/+1.56/4.38/0 | 3.36/+1.22/5.56/0 | 3.84/+0.74/4.53/0 | 3.14/+1.44/4.30/0 | 5.36/-0.78/10.73/0 |
| 8 | 1.24/+2.39/2.16/0 | 3.00/+0.62/3.36/0 | 2.73/+0.90/3.35/0 | 3.07/+0.55/4.06/0 | 3.31/+0.32/3.63/0 | 3.12/+0.50/3.26/0 | 4.38/-0.76/6.68/0 |

### Phase-Level Best Algorithm Results

In this larger constellation setting, `WeightedMedian` becomes the strongest method because the extra responders give it enough redundancy to reject bad satellites without needing temporal smoothing.

| Satellites | Best Algorithm | Burst Storm | Drift + Stuck | Dropout + Random | Nominal | Recovery |
|---:|---|---:|---:|---:|---:|---:|
| 3 | WeightedMedian | 2.12 | 1.81 | 1.70 | 1.65 | 2.19 |
| 5 | WeightedMedian | 1.89 | 2.23 | 1.81 | 1.26 | 1.46 |
| 8 | WeightedMedian | 1.29 | 1.49 | 1.35 | 1.05 | 1.25 |

### Updated Interpretation

The two-responder benchmark favors Kalman-family filters because temporal smoothing compensates for limited peer redundancy. The larger constellation benchmark changes the ranking: once 5-8 responders are available, robust spatial consensus becomes more valuable, and `WeightedMedian` wins across the injected random-event regime.

`NIS-Kalman` improves as the constellation grows, especially at 5 and 8 satellites, but its p95 error remains higher than `WeightedMedian` in the most fault-heavy phases.

`RANSAC-Kalman` becomes more competitive with 5-8 satellites, which confirms that it needs enough responders to form meaningful consensus sets.

`Gossip-Kalman` remains weak under persistent drift and stale-value faults because averaging can propagate corrupted values before the Kalman update.

### Updated Recommendation

For SISP correction in larger constellations:

1. Use `WeightedMedian` as the robust default when 5 or more responders are available.
2. Use `Hybrid` or `NIS-Kalman` when temporal continuity matters and the responder count is small.
3. Use `RANSAC-Kalman` only when there are enough responders to support true consensus sampling.
4. Avoid plain gossip averaging in adversarial or high-fault settings unless paired with stronger outlier rejection.

## DEGR Policy Sweep

A separate sweep is implemented in:

`all_tests/test_degr_policy_sweep.py`

This experiment asks whether the current DEGR-to-trust mapping should keep the existing 5% minimum trust floor or use a much higher floor such as 50%.

The tested policy family maps residual error to a target trust weight, then converts that weight back into the protocol DEGR scale:

`DEGR = round((1 - target_weight) * 15)`

The current C++ correction receiver still applies:

`w_i = max(0.05, 1 - DEGR_i/15)`

### Sweep Results

Scenario: 8-satellite data-driven benchmark using `data/raw/segments.csv`.

| Policy | Best Algorithm | steady_corr | gain | p95_corr | recovery |
|---|---|---:|---:|---:|---:|
| soft_sqrt_floor_5pct | WeightedMedian | 1.221 | +2.405 | 2.157 | 0 |
| linear_floor_5pct | WeightedMedian | 1.240 | +2.386 | 2.157 | 0 |
| wide_scale_floor_5pct | WeightedMedian | 1.252 | +2.374 | 2.199 | 0 |
| linear_floor_25pct | WeightedMedian | 1.264 | +2.361 | 2.298 | 0 |
| binary_2sigma_floor_5pct | WeightedMedian | 1.272 | +2.354 | 2.547 | 0 |
| aggressive_square_floor_5pct | WeightedMedian | 1.278 | +2.347 | 2.250 | 0 |
| linear_floor_50pct | WeightedMedian | 1.282 | +2.343 | 2.347 | 0 |
| binary_3sigma_floor_5pct | WeightedMedian | 1.335 | +2.291 | 2.342 | 0 |

Per-algorithm detail:

| Policy | WeightedMedian | Kalman | NIS-Kalman | Hybrid |
|---|---|---|---|---|
| soft_sqrt_floor_5pct | 1.22/+2.41 | 3.16/+0.47 | 2.85/+0.78 | 3.14/+0.49 |
| linear_floor_5pct | 1.24/+2.39 | 3.00/+0.62 | 2.73/+0.90 | 3.07/+0.55 |
| wide_scale_floor_5pct | 1.25/+2.37 | 3.14/+0.48 | 3.09/+0.53 | 3.04/+0.59 |
| linear_floor_25pct | 1.26/+2.36 | 3.46/+0.17 | 3.19/+0.43 | 3.07/+0.56 |
| binary_2sigma_floor_5pct | 1.27/+2.35 | 2.90/+0.73 | 2.58/+1.05 | 3.01/+0.61 |
| aggressive_square_floor_5pct | 1.28/+2.35 | 2.89/+0.74 | 2.68/+0.94 | 3.04/+0.58 |
| linear_floor_50pct | 1.28/+2.34 | 3.76/-0.13 | 3.58/+0.04 | 3.06/+0.57 |
| binary_3sigma_floor_5pct | 1.34/+2.29 | 2.92/+0.70 | 2.99/+0.63 | 2.94/+0.69 |

### DEGR Sweep Conclusion

A 50% trust floor is not best in this benchmark. It keeps faulty satellites too influential, especially for Kalman-family filters. In the 8-satellite random-fault scenario, the current 5% floor remains a strong choice.

The best overall tested policy is:

`soft_sqrt_floor_5pct`

This means keeping the 5% minimum trust floor, but using a softer square-root mapping from residual error to DEGR so moderately suspicious readings lose trust earlier:

`normalized = clamp(error / (3*sigma), 0, 1)`

`target_weight = 0.05 + 0.95 * (1 - sqrt(normalized))`

The current linear 5% floor is very close to the best result, so the existing protocol formula is defensible. The evidence does not support raising the minimum trust floor to 50%.
