# SISP — Architecture & Pipeline

## Goal

Detect anomalous segments in satellite telemetry from the **OPSSAT-AD** dataset (Zenodo record `12588359`).

Each segment is a fixed-length slice of one telemetry channel, already reduced to **19 hand-engineered features** (mean, var, skew, peaks, etc.). Each row is labeled with `train` (split) and `anomaly` (truth). The model learns what "nominal training" segments look like per channel and flags segments that deviate from that profile.

## Approach

**Per-channel TruncatedSVD reconstruction error.** For each channel:

1. Fit a low-rank SVD on **nominal training rows only** (`train=True AND anomaly=False`).
2. Project every row through SVD and reconstruct it.
3. Score = squared L2 distance between row and its reconstruction.
4. Threshold = 95th percentile of fit-row scores. Anything above is predicted anomalous.

Why this works: a low-rank basis fit on nominal data captures the dominant patterns of normal behavior. Anomalies don't lie in that subspace, so they reconstruct poorly.

Why per-channel: telemetry channels have very different scales and dynamics. One global model would dilute channel-specific signal.

## The fit-mask rule

Every quantity learned from data — column medians, winsorization caps, the StandardScaler, the SVD basis, the anomaly threshold — is fit **exclusively on `train=True AND anomaly=False` rows**. This is the `fit_mask` defined in [sisp/preprocessing/metadata.py:107](sisp/preprocessing/metadata.py#L107). All other rows (test rows, training-but-anomalous rows) are transformed using the fitted parameters but never influence them. This prevents label leakage end-to-end.

## Pipeline (3 stages, run in order)

Each stage is a thin orchestration script in [pipelines/](pipelines/). Business logic lives in [sisp/](sisp/). Stages communicate only through files on disk under `data/`.

### Stage 1 — Ingest ([pipelines/run_ingest.py](pipelines/run_ingest.py))

1. Download the dataset from Zenodo into `data/raw/`.
2. Validate that all 19 features + 4 metadata columns are present.
3. Group rows by `channel`, write one parquet per channel.
4. For each channel, split into `*_features.parquet` (numeric only) and `*_metadata.parquet` (segment/anomaly/train/channel).
5. Coerce features to int64/float64 only — fail loudly on anything else.

**Output:** per-channel raw features + metadata in `data/interim/by_channel/`.

### Stage 2 — Preprocess ([pipelines/run_preprocess.py](pipelines/run_preprocess.py))

For each channel, run a fixed sequence of cleaning steps. All fitting uses fit-mask rows; transforms apply to all rows.

| Step | What | Why |
|---|---|---|
| Audit | Log NaN counts per column | Visibility |
| Drop rows | Drop rows with >30% NaN features | Mostly-empty rows are unrecoverable |
| Impute | Median-impute remaining NaNs (fit-row median, fallback to overall) | Need a complete matrix |
| Zero-variance | Detect features with std≈0 on fit rows; convert to binary "deviates from constant?" indicator | A constant feature is uninformative as continuous, but a deviation from it is a strong anomaly signal |
| Winsorize | Clip continuous features to [1st, 99th] percentile from fit rows | Cap extreme values without dropping rows |
| Scale | StandardScaler on continuous features (binary cols passed through unchanged) | SVD assumes centered, comparable scales |

All the cleaning logic lives in [sisp/preprocessing/cleaner.py](sisp/preprocessing/cleaner.py). Scaling lives in [sisp/preprocessing/scaler.py](sisp/preprocessing/scaler.py).

**Output:** `*_features_clean.parquet`, `*_features_winsorized.parquet`, `*_features_scaled.parquet`, `*_metadata_clean.parquet`, fitted scaler pickle, and JSON sidecars listing column order and which features were binary-transformed.

### Stage 3 — SVD & Anomaly Detection ([pipelines/run_svd.py](pipelines/run_svd.py))

For each channel:

1. **Select rank `k`** — fit a probe SVD, pick smallest `k` reaching 90% cumulative variance, clamped to `[2, 15]`.
2. **Fit SVD** — `TruncatedSVD(n_components=k)` on fit-mask rows of scaled features.
3. **Score all rows** — reconstruction error = ‖x − SVD⁻¹(SVD(x))‖².
4. **Compute threshold** — 95th percentile of fit-row errors.
5. **Predict** — `error > threshold → anomaly`.
6. **Report** — confusion matrix, precision/recall/F1, ROC-AUC, on both train and test splits.

SVD logic in [sisp/anomaly/svd.py](sisp/anomaly/svd.py). Reporting in [sisp/anomaly/evaluator.py](sisp/anomaly/evaluator.py).

**Output:** per-channel `data/output/<channel>_results.parquet` with columns `segment, train, anomaly, reconstruction_error, threshold, predicted_anomaly`.

## Project layout

```
SISP/
├── config/settings.py        all tunable constants (thresholds, k bounds, percentiles, RNG seed)
├── pipelines/
│   ├── run_ingest.py
│   ├── run_preprocess.py
│   └── run_svd.py
├── sisp/
│   ├── io/
│   │   ├── loader.py         Zenodo download + raw read
│   │   └── writer.py         parquet/pickle/json saves + sample CSVs
│   ├── preprocessing/
│   │   ├── metadata.py       feature/metadata separation, train/test/fit masks
│   │   ├── cleaner.py        impute + zero-var binary + winsorize
│   │   └── scaler.py         StandardScaler fit/apply/validate
│   ├── anomaly/
│   │   ├── svd.py            rank selection, fit, reconstruction error, threshold
│   │   └── evaluator.py      predictions, confusion matrix, metrics report
│   └── utils/
│       ├── paths.py          single source of truth for every artifact path
│       └── helpers.py        logger factory + alignment/null/dtype assertions
├── scripts/
│   └── inspect_artifacts.py  CLI to dump intermediate parquets for one channel
└── data/                     all generated artifacts (gitignored)
    ├── raw/
    ├── interim/by_channel/   per-channel feature/metadata parquets
    ├── interim/scalers/      per-channel pickled StandardScaler
    ├── interim/svd/          per-channel pickled SVD + JSON sidecars
    └── output/               per-channel result parquets
```

## Design rules

- **Thin pipelines, fat modules.** Pipeline scripts only orchestrate I/O and call sequence. All transforms live in `sisp/`.
- **One source of truth for paths.** Every read/write goes through `sisp/utils/paths.py`. No string-concatenated paths anywhere else.
- **One source of truth for constants.** Thresholds, percentiles, k bounds, `RANDOM_STATE=42` all in `config/settings.py`.
- **Features and metadata travel together.** Any function that mutates rows takes both and asserts `len(X) == len(meta)` at entry and exit (`assert_aligned`).
- **Determinism.** Every random component uses `RANDOM_STATE=42`. Re-runs produce byte-identical artifacts.
- **Idempotent stages.** Re-running a stage overwrites its outputs, never appends.

## Run

```bash
pip install -r requirements.txt
python pipelines/run_ingest.py
python pipelines/run_preprocess.py
python pipelines/run_svd.py
```

To inspect intermediate artifacts for one channel:

```bash
python scripts/inspect_artifacts.py --channel CADC0872 --rows 10
```
