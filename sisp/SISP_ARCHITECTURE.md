# SISP project architecture

## Overview

This document describes the modular structure of the SISP (Satellite Inter-Service Protocol) project. The codebase is organized so that each concern — data ingestion, preprocessing, anomaly detection, and shared utilities — lives in its own well-defined layer. New pipelines (Kalman correction, cross-calibration, inter-satellite messaging) can be added without touching existing modules.

---

## Directory structure

```
SISP/
├── README.md
├── requirements.txt
├── config/
│   └── settings.py                  ← all constants and tunable parameters
│
├── sisp/                            ← main package (importable as `from sisp.x import y`)
│   ├── __init__.py
│   │
│   ├── io/                          ← data input/output layer
│   │   ├── __init__.py
│   │   ├── loader.py                ← download and load raw dataset
│   │   └── writer.py                ← save parquet, pkl, json with consistent paths
│   │
│   ├── preprocessing/               ← data cleaning and feature preparation
│   │   ├── __init__.py
│   │   ├── channel_splitter.py      ← split dataset by channel, enforce exclusions
│   │   ├── metadata.py              ← separate and manage metadata columns
│   │   ├── imputer.py               ← NaN audit, row dropping, train-only median imputation
│   │   ├── variance_handler.py      ← zero-variance detection and binary transformation
│   │   ├── winsorizer.py            ← train-only percentile clipping
│   │   └── scaler.py                ← train-only StandardScaler fit/transform/persist
│   │
│   ├── anomaly/                     ← anomaly detection pipeline
│   │   ├── __init__.py
│   │   ├── svd_model.py             ← TruncatedSVD fit, rank selection, persist
│   │   ├── scorer.py                ← reconstruction error computation
│   │   └── evaluator.py             ← threshold, predictions, metrics, reports
│   │
│   └── utils/                       ← shared helpers used across all pipelines
│       ├── __init__.py
│       ├── logger.py                ← structured console logging with channel context
│       ├── paths.py                 ← all Path objects derived from a single root
│       └── validation.py            ← alignment assertions, dtype checks, shape checks
│
├── pipelines/                       ← executable end-to-end scripts (one per pipeline)
│   ├── run_ingest.py                ← wraps sisp.io: download + split + save raw files
│   ├── run_preprocess.py            ← wraps sisp.preprocessing: steps 3–4 end-to-end
│   └── run_svd.py                   ← wraps sisp.anomaly: steps 5–6 end-to-end
│
└── data/                            ← generated data (never committed to git)
    ├── raw/
    ├── interim/
    │   ├── by_channel/
    │   ├── scalers/
    │   └── svd/
    └── output/
```

---

## Design principles

### 1. One responsibility per module

Each `.py` file in `sisp/` does exactly one thing. `imputer.py` handles NaN logic. `scaler.py` handles scaling. Neither knows about the other. This means you can test, replace, or extend any single step without reading the rest of the codebase.

### 2. Pipelines are thin orchestrators

Files in `pipelines/` contain no business logic — they import from `sisp/`, loop over channels, call functions in order, and print summaries. If a pipeline file is growing beyond ~80 lines, logic is leaking into it that belongs in a module.

### 3. All paths flow from one root

`sisp/utils/paths.py` defines every directory and file path as a function of a single `DATA_ROOT` variable (defaulting to `./data`). No other file ever constructs a path string manually. This makes the entire project relocatable with one config change.

### 4. All tunable values live in `config/settings.py`

Constants like `EXCLUDED_CHANNELS`, `NAN_DROP_THRESHOLD`, `WINSOR_LOW`, `WINSOR_HIGH`, `SVD_VARIANCE_TARGET`, `ANOMALY_THRESHOLD_PERCENTILE` are defined once in `settings.py` and imported wherever needed. Changing a parameter means editing one line in one file.

### 5. The fitting rule is enforced at the module boundary

The mask `train == True AND anomaly == 0` is computed inside each fitting function (imputer, scaler, SVD), not in the pipeline script. This prevents accidental data leakage when pipelines are extended or reordered.

### 6. Metadata and features are always passed together

Every function that transforms the feature matrix also receives (and returns) the aligned metadata frame. Alignment is asserted (`len(X) == len(meta)`) at module entry and exit. Row order is never assumed — it is verified.

---

## Module reference

### `config/settings.py`

```python
EXCLUDED_CHANNELS = {'CADC0886', 'CADC0890'}
METADATA_COLS = ['segment', 'anomaly', 'train', 'channel']
NAN_DROP_THRESHOLD = 0.30          # drop rows with > 30% NaN features
WINSOR_LOW  = 0.01                 # 1st percentile lower cap
WINSOR_HIGH = 0.99                 # 99th percentile upper cap
ZERO_VAR_EPSILON = 1e-8            # std below this → zero-variance
SVD_VARIANCE_TARGET = 0.90         # cumulative variance to explain
SVD_K_MIN = 2
SVD_K_MAX = 15
ANOMALY_THRESHOLD_PERCENTILE = 95  # percentile of fit-row errors → threshold T
```

---

### `sisp/utils/paths.py`

Single source of truth for all file paths. Every other module imports from here.

```python
from pathlib import Path

DATA_ROOT = Path("data")

RAW_DIR          = DATA_ROOT / "raw"
BY_CHANNEL_DIR   = DATA_ROOT / "interim" / "by_channel"
SCALERS_DIR      = DATA_ROOT / "interim" / "scalers"
SVD_DIR          = DATA_ROOT / "interim" / "svd"
OUTPUT_DIR       = DATA_ROOT / "output"

def features_path(channel):        return BY_CHANNEL_DIR / f"{channel}_features.parquet"
def metadata_path(channel):        return BY_CHANNEL_DIR / f"{channel}_metadata.parquet"
def features_clean_path(channel):  return BY_CHANNEL_DIR / f"{channel}_features_clean.parquet"
def features_winsor_path(channel): return BY_CHANNEL_DIR / f"{channel}_features_winsorized.parquet"
def features_scaled_path(channel): return BY_CHANNEL_DIR / f"{channel}_features_scaled.parquet"
def metadata_clean_path(channel):  return BY_CHANNEL_DIR / f"{channel}_metadata_clean.parquet"
def scaler_path(channel):          return SCALERS_DIR / f"{channel}_scaler.pkl"
def svd_path(channel):             return SVD_DIR / f"{channel}_svd.pkl"
def feature_names_path(channel):   return SVD_DIR / f"{channel}_feature_names.json"
def binary_features_path(channel): return SVD_DIR / f"{channel}_binary_features.json"
def results_path(channel):         return OUTPUT_DIR / f"{channel}_results.parquet"
```

---

### `sisp/utils/validation.py`

```python
def assert_aligned(X, meta, context=""):
    """Raise ValueError if X and meta row counts differ."""

def assert_no_nulls(X, context=""):
    """Raise ValueError if X contains any NaN."""

def assert_numeric_only(X, context=""):
    """Raise ValueError if X contains non-numeric columns."""
```

---

### `sisp/utils/logger.py`

Thin wrapper around Python's `logging` module. Adds channel context to every message.

```python
def get_logger(channel=None) -> logging.Logger:
    """Return a logger prefixed with [channel] if provided."""
```

---

### `sisp/io/loader.py`

```python
def download_dataset(zenodo_url: str, dest_dir: Path) -> Path:
    """Download and extract the dataset. Return path to the CSV/Parquet file."""

def load_raw(path: Path) -> pd.DataFrame:
    """Load raw dataset, validate required columns, return DataFrame."""
```

---

### `sisp/io/writer.py`

```python
def save_parquet(df: pd.DataFrame, path: Path) -> None:
def save_pickle(obj, path: Path) -> None:
def save_json(data, path: Path) -> None:
def print_file_summary(paths: list[Path]) -> None:
    """Print name and size of each file. Call at end of every pipeline."""
```

---

### `sisp/preprocessing/channel_splitter.py`

```python
def split_by_channel(df: pd.DataFrame, excluded: set) -> dict[str, pd.DataFrame]:
    """
    Split df by channel column.
    Skip excluded channels with a logged notice.
    Return {channel_name: sub_dataframe}.
    """
```

---

### `sisp/preprocessing/metadata.py`

```python
def separate(df: pd.DataFrame, meta_cols: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split df into (features_df, metadata_df).
    Asserts meta_cols are present and no metadata col leaked into features.
    """

def fit_mask(meta: pd.DataFrame) -> pd.Series:
    """Return boolean mask: train==True AND anomaly==0."""
```

---

### `sisp/preprocessing/imputer.py`

```python
def audit_nulls(X: pd.DataFrame, channel: str) -> None:
    """Print NaN counts and percentages per column."""

def drop_high_null_rows(X: pd.DataFrame, meta: pd.DataFrame, threshold: float) -> tuple:
    """
    Drop rows where NaN fraction > threshold.
    Apply same drop to meta. Assert alignment. Return (X, meta).
    """

def impute(X: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """
    Impute NaNs using per-column median computed on fit_mask rows only.
    Falls back to overall median with warning if fit rows are all NaN.
    Assert zero NaNs after imputation.
    """
```

---

### `sisp/preprocessing/variance_handler.py`

```python
def detect_zero_variance(X: pd.DataFrame, meta: pd.DataFrame) -> list[str]:
    """Return list of column names with std < ZERO_VAR_EPSILON on fit rows."""

def apply_binary_transform(X: pd.DataFrame, zero_var_cols: list) -> tuple[pd.DataFrame, dict]:
    """
    For each zero-variance column:
      - record the constant training value c
      - set all rows: 0 if value==c else 1
    Return (transformed_X, {col: constant_value}).
    Print per-channel summary including non-zero row counts.
    """
```

---

### `sisp/preprocessing/winsorizer.py`

```python
def fit_caps(X: pd.DataFrame, meta: pd.DataFrame, continuous_cols: list) -> dict:
    """
    Compute (p01, p99) for each continuous column using fit rows only.
    Return {col: (lower, upper)}.
    """

def apply_caps(X: pd.DataFrame, caps: dict) -> pd.DataFrame:
    """
    Clip all rows to pre-computed caps.
    Print which columns were affected and how many values were clipped.
    """
```

---

### `sisp/preprocessing/scaler.py`

```python
def fit_scaler(X: pd.DataFrame, meta: pd.DataFrame, continuous_cols: list) -> StandardScaler:
    """Fit StandardScaler on fit_mask rows of continuous columns only."""

def apply_scaler(X: pd.DataFrame, scaler: StandardScaler,
                 continuous_cols: list, binary_cols: list) -> pd.DataFrame:
    """
    Scale continuous columns. Pass binary columns through unchanged.
    Concatenate and preserve original column order.
    """

def validate_scaling(X_scaled: pd.DataFrame, meta: pd.DataFrame,
                     continuous_cols: list, binary_cols: list, channel: str) -> None:
    """
    Print fit/test mean+std table for continuous cols.
    Flag |test_mean| > 3.0 or |test_std - 1| > 2.0.
    Print binary col value counts on test rows.
    """
```

---

### `sisp/anomaly/svd_model.py`

```python
def select_rank(X_fit: np.ndarray, variance_target: float, k_min: int, k_max: int) -> tuple[int, float]:
    """
    Fit full SVD, compute cumulative explained variance.
    Return (k, cumulative_variance_at_k).
    """

def fit_svd(X_fit: np.ndarray, k: int) -> TruncatedSVD:
    """Fit TruncatedSVD with chosen k on X_fit. Return fitted model."""
```

---

### `sisp/anomaly/scorer.py`

```python
def reconstruction_error(svd: TruncatedSVD, X: np.ndarray) -> np.ndarray:
    """
    Project X onto k-subspace, reconstruct, return ||x - x_hat||^2 per row.
    """

def compute_threshold(errors: np.ndarray, meta: pd.DataFrame,
                      percentile: float) -> float:
    """
    Compute threshold T as the given percentile of fit-row errors.
    """
```

---

### `sisp/anomaly/evaluator.py`

```python
def predict(errors: np.ndarray, threshold: float) -> np.ndarray:
    """Return binary predictions: 1 if error > threshold else 0."""

def build_results(meta: pd.DataFrame, errors: np.ndarray,
                  threshold: float, predictions: np.ndarray) -> pd.DataFrame:
    """
    Assemble results DataFrame:
    segment, train, anomaly, reconstruction_error, threshold, predicted_anomaly.
    """

def report(results: pd.DataFrame, channel: str) -> None:
    """
    Print per-channel evaluation:
    - Threshold T
    - Test-set confusion matrix, Precision, Recall, F1, ROC-AUC
    - Train-set same metrics (sanity check)
    - Mean error for anomaly=0 vs anomaly=1 rows
    """
```

---

## How to add a new pipeline

When you build the next part of SISP (e.g. the Kalman correction pipeline or the inter-satellite messaging protocol), follow this pattern:

1. Create a new package under `sisp/` — e.g. `sisp/kalman/` with its own `__init__.py`
2. Add modules inside it following the single-responsibility rule
3. Add any new constants to `config/settings.py`
4. Add any new path builders to `sisp/utils/paths.py`
5. Create a `pipelines/run_kalman.py` that orchestrates the new modules
6. The existing preprocessing outputs (`_features_scaled.parquet`, `_metadata_clean.parquet`) are stable inputs — the new pipeline reads them directly without re-running preprocessing

No existing file needs to be modified to add new functionality. Each pipeline is fully additive.

---

## Running the pipelines

```bash
# Step 1 — download and split by channel
python pipelines/run_ingest.py

# Step 2 — clean, transform, scale
python pipelines/run_preprocess.py

# Step 3 — SVD anomaly detection
python pipelines/run_svd.py
```

Each script is self-contained and re-runnable. Intermediate files are always overwritten, never appended to.

---

## What not to do

- Never import from `pipelines/` into `sisp/` — the dependency goes one way only: pipelines → sisp modules
- Never construct a file path with string concatenation outside `paths.py`
- Never fit a statistical model (scaler, imputer, SVD) on rows that are not in the `train==True AND anomaly==0` mask
- Never assume a fixed number of features — channels have different column counts after zero-variance handling
- Never commit the `data/` directory — add it to `.gitignore`
