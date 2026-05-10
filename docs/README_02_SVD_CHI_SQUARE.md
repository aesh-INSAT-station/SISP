# SVD Anomaly Detection + Chi-Square Gating

**Source files:**
- `ARCHITECTURE.md` — Pipeline architecture and design rules
- `HOW_SVD_Works.md` — Mathematical explanation and intuition
- `data/raw/segments.csv` — OPSSAT-AD telemetry dataset (Zenodo 12588359)

---

## Purpose

Before a satellite's correction response is accepted into the Kalman filter, it is screened by an SVD-based anomaly detector. A reading that is statistically inconsistent with the sender's historical behaviour is excluded, preventing corrupted or faulty sensor data from biasing the distributed estimate.

---

## Dataset: OPSSAT-AD

The OPS-SAT anomaly detection dataset contains continuous telemetry from ESA's OPS-SAT CubeSat, organized by telemetry channel. Each segment is described by 19 aggregate features (mean, variance, slope, etc.) derived from a fixed time window. Labels (nominal / anomalous) are available for evaluation but are **not used during training** — the SVD is a purely unsupervised model.

Key columns in `segments.csv`:

| Column | Description |
|---|---|
| `channel` | Telemetry channel identifier (e.g., CADC0894) |
| `timestamp` | ISO 8601 segment start time |
| `value` | Scalar telemetry value |
| `label` | Ground truth (0=nominal, 1=anomalous) |
| `anomaly` | Anomaly indicator |
| `segment` | Segment index within the channel |
| `train` | 1 if in training split |

---

## Pipeline (Three Stages)

### Stage 1: Ingest
- Download Zenodo dataset, validate 19 features + metadata, group rows by channel.
- Output: per-channel DataFrames with aligned feature matrix.

### Stage 2: Preprocess
1. Drop rows with >50% NaN.
2. Median-impute remaining NaN values.
3. Drop zero-variance features.
4. Winsorize at 1st/99th percentile to remove extreme outliers.
5. StandardScale to zero mean and unit variance.

### Stage 3: SVD Model per Channel
1. **Fit on nominal training rows only** (label=0, train=1).
2. **Rank selection:** Increment $k$ until cumulative explained variance ≥ 90%, clamped to $k \in [2, 15]$.
3. **Reconstruction error baseline:** Compute $\epsilon_i = \|x_i - \hat{x}_i\|_2^2$ on all training nominal rows.
4. **Threshold:** $\tau_{95} = \text{percentile}_{95}(\{\epsilon_i\})$.

---

## The SVD Anomaly Detector

### Why SVD Works for Anomaly Detection

SVD of the nominal training matrix $X \in \mathbb{R}^{n \times p}$:

$$X = U \Sigma V^\top$$

With rank-$k$ truncation:

$$\hat{X} = U_k \Sigma_k V_k^\top$$

The row subspace $V_k$ represents the **$k$ directions of maximum variance in nominal data**. New observations are projected onto this subspace and reconstructed:

$$\hat{x} = V_k V_k^\top x$$

**Key insight:** $k \ll p$ means information is compressed. Nominal data reconstructs well (small $\epsilon$); anomalous data, which deviates from the nominal subspace, reconstructs poorly (large $\epsilon$). The compression is the detection mechanism — not the data itself.

**Why not $k = p$ (full rank)?** Full-rank SVD gives $\hat{x} = x$ for all inputs, so $\epsilon = 0$ always. The truncation that makes SVD useful as an anomaly detector is the same truncation that makes it lossy. This is why rank selection is the most critical hyperparameter.

### Rank Selection

The 90% cumulative variance rule:

$$k^* = \min\!\left\{k : \sum_{i=1}^{k} \sigma_i^2 \Big/ \sum_{i=1}^{p} \sigma_i^2 \geq 0.90\right\}$$

Clamped to $k \in [2, 15]$. Empirically, $k^* = 4$ for CADC0894. Achieved ROC-AUC: **0.84** on the held-out test split.

**Trade-off:** Higher $k$ → more nominal variance captured → fewer false positives but more false negatives. 90% is the recommended balance point.

---

## Chi-Square Gating

For readings that pass the SVD threshold, a second statistical gate applies the chi-square distribution.

Under the Gaussian model, the normalized reconstruction error follows a chi-square distribution with $k$ degrees of freedom:

$$\chi^2_{\text{obs}} = \frac{\epsilon}{\sigma_\epsilon^2} \sim \chi^2(k)$$

At confidence level 95%:

| $k$ | $\chi^2_{k,0.95}$ |
|---|---|
| 2 | 5.99 |
| 3 | 7.81 |
| 4 | 9.49 |
| 5 | 11.07 |

Readings with $\chi^2_{\text{obs}} > \chi^2_{k,0.95}$ are rejected before entering the correction filter.

This is the **NIS gate** used in the `NIS-gated Kalman` correction algorithm (see `README_03_CORRECTION_ALGORITHMS.md`). Test results show it adds robustness against persistent single-satellite bias at the cost of some sensitivity in Gaussian-noise scenarios.

---

## Integration with Correction Layer

```
Neighbour sends CORRECTION_RSP
        │
        ▼
SVD reconstruction error check
  ε > τ_95 ?  → reject (anomalous reading)
        │ no
        ▼
Chi-square gate
  χ² > χ²_{k,0.95} ? → reject (NIS-gated mode only)
        │ no
        ▼
Buffer into ctx.rsp_readings[rsp_count]
Set ctx.rsp_weights[rsp_count] from DEGR
rsp_count++
        │
(timer expires)
        ▼
Run correction filter on buffered readings
```

---

## Tuning Parameters

| Parameter | Location | Default | Effect |
|---|---|---|---|
| `TARGET_EXPLAINED_VARIANCE` | `config/settings.py` | 0.90 | Rank selection target |
| `MIN_COMPONENTS` | `config/settings.py` | 2 | Minimum rank |
| `MAX_COMPONENTS` | `config/settings.py` | 15 | Maximum rank |
| `THRESHOLD_PERCENTILE` | `config/settings.py` | 95 | Reconstruction error quantile |
| `CHI_SQUARE_CONFIDENCE` | `config/settings.py` | 0.95 | NIS gate confidence level |

---

## Design Rules (from ARCHITECTURE.md)

1. **No label leakage.** The SVD is fit only on `train=1, label=0` rows. Thresholds are computed on the training distribution.
2. **Row alignment.** Feature matrices and metadata DataFrames travel together; operations that reorder or drop rows must be applied to both.
3. **Determinism.** `random_state=42` is set on all stochastic operations. Given the same input, the pipeline produces identical output.
4. **Idempotent stages.** Each stage can be re-run without corrupting downstream artifacts.
5. **One source of truth.** All file paths are in `sisp/utils/paths.py`; all constants in `config/settings.py`.
