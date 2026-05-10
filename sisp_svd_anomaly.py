"""
SISP SVD Anomaly Detection Pipeline
=====================================
Single-file, self-contained implementation.
Loads OPSSAT-AD segments.csv, preprocesses per channel,
fits a per-channel TruncatedSVD anomaly model, and evaluates it.

Usage
-----
    python sisp_svd_anomaly.py                          # all channels, default data path
    python sisp_svd_anomaly.py --channel CADC0894       # single channel
    python sisp_svd_anomaly.py --data data/raw/segments.csv --plot
    python sisp_svd_anomaly.py --list-channels          # show available channels

Parameters (edit the CONFIG block below or pass --help)
"""

import argparse
import sys
import os
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG — change here or override via CLI
# ══════════════════════════════════════════════════════════════════════════════
CONFIG = {
    # Data
    "data_path": "data/raw/segments.csv",

    # SVD rank selection
    "target_variance": 0.90,       # cumulative explained variance target
    "min_components": 2,           # minimum rank k
    "max_components": 15,          # maximum rank k

    # Anomaly threshold
    "threshold_percentile": 95,    # percentile of training errors → anomaly cutoff

    # Chi-square NIS gate (applied at inference if use_chi_square=True)
    "use_chi_square": True,
    "chi_square_confidence": 0.95,

    # Preprocessing
    "nan_drop_threshold": 0.50,    # drop rows with > 50% NaN
    "winsorize_pct": 1.0,          # clip at [1st, 99th] percentile

    # Output
    "verbose": True,
    "random_state": 42,
}

# ══════════════════════════════════════════════════════════════════════════════
#  FEATURE COLUMNS — aggregate features extracted from each segment
# ══════════════════════════════════════════════════════════════════════════════
FEATURE_COLS = [
    "mean", "std", "min", "max", "median",
    "q25", "q75", "iqr", "skewness", "kurtosis",
    "slope", "n_crossings", "energy", "autocorr_1", "autocorr_2",
    "range", "variance", "rms", "abs_mean",
]

META_COLS = ["channel", "segment", "label", "anomaly", "train"]


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def log(msg: str, verbose: bool = True):
    if verbose:
        print(msg)


def chi_square_threshold(k: int, confidence: float) -> float:
    """Chi-square critical value for k degrees of freedom at given confidence.
    Uses a simple asymptotic approximation (Wilson-Hilferty).
    """
    from scipy.stats import chi2
    return float(chi2.ppf(confidence, df=k))


# ══════════════════════════════════════════════════════════════════════════════
#  DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_data(path: str, verbose: bool = True) -> pd.DataFrame:
    """Load segments.csv and derive features from raw time-series if needed."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Data file not found: {path}\n"
                                f"Expected: data/raw/segments.csv")

    log(f"Loading {path} ...", verbose)
    df = pd.read_csv(path)
    log(f"  Loaded {len(df):,} rows, columns: {list(df.columns)}", verbose)

    # If data is in raw (channel, timestamp, value) format, derive features
    if "value" in df.columns and "mean" not in df.columns:
        log("  Raw format detected — deriving segment features ...", verbose)
        df = _derive_features(df, verbose)

    return df


def _derive_features(df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
    """Convert raw (channel, timestamp, value, label, segment, train) to feature rows."""
    required = {"channel", "value", "segment"}
    if not required.issubset(df.columns):
        raise ValueError(f"Expected columns {required}, got {set(df.columns)}")

    rows = []
    for (ch, seg), grp in df.groupby(["channel", "segment"]):
        v = grp["value"].values.astype(float)
        if len(v) < 4:
            continue

        # Slope via linear regression
        x = np.arange(len(v))
        slope = np.polyfit(x, v, 1)[0] if len(v) >= 2 else 0.0

        # Zero crossings
        n_cross = int(np.sum(np.diff(np.sign(v - np.mean(v))) != 0))

        # Autocorrelation
        def _autocorr(s, lag):
            if len(s) <= lag:
                return 0.0
            c = np.corrcoef(s[:-lag], s[lag:])[0, 1]
            return float(c) if np.isfinite(c) else 0.0

        q25, q75 = np.percentile(v, [25, 75])
        row = {
            "channel": ch, "segment": seg,
            "mean": np.mean(v), "std": np.std(v),
            "min": np.min(v), "max": np.max(v), "median": np.median(v),
            "q25": q25, "q75": q75, "iqr": q75 - q25,
            "skewness": float(pd.Series(v).skew()),
            "kurtosis": float(pd.Series(v).kurtosis()),
            "slope": slope,
            "n_crossings": n_cross,
            "energy": float(np.sum(v ** 2)),
            "autocorr_1": _autocorr(v, 1),
            "autocorr_2": _autocorr(v, 2),
            "range": np.max(v) - np.min(v),
            "variance": np.var(v),
            "rms": float(np.sqrt(np.mean(v ** 2))),
            "abs_mean": float(np.mean(np.abs(v))),
        }
        # Carry over meta
        for col in ["label", "anomaly", "train"]:
            if col in grp.columns:
                row[col] = grp[col].iloc[0]
        rows.append(row)

    result = pd.DataFrame(rows)
    log(f"  Derived {len(result):,} segment feature rows from {df['channel'].nunique()} channels",
        verbose)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  PREPROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def preprocess(df: pd.DataFrame, cfg: dict, verbose: bool = True) -> pd.DataFrame:
    """Clean and scale features. Returns the same DataFrame with a new 'X_scaled' matrix."""
    feat_cols = [c for c in FEATURE_COLS if c in df.columns]
    log(f"  Feature columns found: {len(feat_cols)}/{len(FEATURE_COLS)}", verbose)

    X = df[feat_cols].copy().astype(float)

    # 1. Drop rows with too many NaN
    nan_frac = X.isnull().mean(axis=1)
    keep = nan_frac <= cfg["nan_drop_threshold"]
    df = df[keep].copy()
    X = X[keep]
    log(f"  After NaN drop (>{cfg['nan_drop_threshold']*100:.0f}%): {len(df):,} rows", verbose)

    # 2. Median impute remaining NaN
    for col in feat_cols:
        med = X[col].median()
        X[col] = X[col].fillna(med if np.isfinite(med) else 0.0)

    # 3. Drop zero-variance features
    variances = X.var()
    valid = variances[variances > 0].index.tolist()
    if len(valid) < len(feat_cols):
        dropped = set(feat_cols) - set(valid)
        log(f"  Dropped zero-variance: {dropped}", verbose)
    X = X[valid]

    # 4. Winsorize at [p, 100-p]
    p = cfg["winsorize_pct"]
    for col in X.columns:
        lo, hi = np.percentile(X[col], [p, 100 - p])
        X[col] = X[col].clip(lo, hi)

    # 5. StandardScale
    mu = X.mean()
    sigma = X.std().replace(0, 1)
    X_scaled = (X - mu) / sigma

    df["_feat_cols"] = [valid] * len(df)   # carry column list
    df["_X_scaled"] = list(X_scaled.values)
    df["_mu"] = [mu.values] * len(df)
    df["_sigma"] = [sigma.values] * len(df)
    df["_valid_feats"] = [valid] * len(df)
    return df, X_scaled.values, valid, mu.values, sigma.values


# ══════════════════════════════════════════════════════════════════════════════
#  SVD MODEL
# ══════════════════════════════════════════════════════════════════════════════

class SVDAnomalyModel:
    """Per-channel TruncatedSVD anomaly detector.

    Fit on nominal training data. Score new observations by reconstruction error.
    Threshold at the 95th percentile of training errors (configurable).
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.k: int = 0
        self.Vk: np.ndarray = None          # right singular vectors (k × p)
        self.threshold_: float = float("inf")
        self.train_errors_: np.ndarray = None
        self.explained_variance_ratio_: np.ndarray = None
        self.chi_threshold_: float = float("inf")
        self.error_std_: float = 1.0

    def fit(self, X_train: np.ndarray) -> "SVDAnomalyModel":
        """Fit on nominal (non-anomalous) training rows."""
        n, p = X_train.shape
        if n < 2:
            raise ValueError(f"Need ≥2 training rows, got {n}")

        # Full SVD to select rank
        U, s, Vt = np.linalg.svd(X_train, full_matrices=False)
        var_total = float(np.sum(s ** 2))
        cumvar = np.cumsum(s ** 2) / (var_total + 1e-12)

        k = max(self.cfg["min_components"], int(np.searchsorted(cumvar, self.cfg["target_variance"]) + 1))
        k = min(k, self.cfg["max_components"], p, n)

        self.k = k
        self.Vk = Vt[:k]                   # (k, p)
        self.explained_variance_ratio_ = (s[:k] ** 2) / (var_total + 1e-12)

        # Compute reconstruction errors on training data
        errs = self._reconstruction_errors(X_train)
        self.train_errors_ = errs
        self.threshold_ = float(np.percentile(errs, self.cfg["threshold_percentile"]))
        self.error_std_ = float(np.std(errs)) if np.std(errs) > 0 else 1.0

        # Chi-square threshold: NIS = error / error_variance
        if self.cfg["use_chi_square"]:
            self.chi_threshold_ = chi_square_threshold(k, self.cfg["chi_square_confidence"])

        return self

    def _reconstruction_errors(self, X: np.ndarray) -> np.ndarray:
        """‖x − V_k V_k^T x‖² for each row."""
        proj = X @ self.Vk.T @ self.Vk     # project into k-dim subspace and back
        return np.sum((X - proj) ** 2, axis=1)

    def score(self, X: np.ndarray) -> np.ndarray:
        """Return reconstruction error for each row."""
        return self._reconstruction_errors(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return 1 (anomalous) or 0 (nominal) for each row."""
        errs = self.score(X)
        anomalous = errs > self.threshold_

        if self.cfg["use_chi_square"]:
            nis = errs / (self.error_std_ ** 2 + 1e-12)
            anomalous |= nis > self.chi_threshold_

        return anomalous.astype(int)

    def summary(self) -> dict:
        return {
            "rank_k": self.k,
            "cumulative_variance": float(np.sum(self.explained_variance_ratio_)),
            "reconstruction_threshold": self.threshold_,
            "chi_threshold": self.chi_threshold_ if self.cfg["use_chi_square"] else None,
            "train_error_mean": float(np.mean(self.train_errors_)),
            "train_error_std": self.error_std_,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def evaluate(y_true: np.ndarray, y_pred: np.ndarray, scores: np.ndarray) -> dict:
    """Compute precision, recall, F1, ROC-AUC."""
    from sklearn.metrics import (
        precision_score, recall_score, f1_score, roc_auc_score,
        average_precision_score,
    )
    if y_true.sum() == 0 or y_true.sum() == len(y_true):
        return {"warning": "Only one class in test set — metrics undefined"}

    return {
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall":    round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1":        round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc":   round(float(roc_auc_score(y_true, scores)), 4),
        "avg_prec":  round(float(average_precision_score(y_true, scores)), 4),
        "n_anomalous": int(y_true.sum()),
        "n_total": len(y_true),
        "predicted_anomalous": int(y_pred.sum()),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  PER-CHANNEL PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run_channel(ch_df: pd.DataFrame, cfg: dict, verbose: bool = True) -> dict:
    """Full pipeline for one channel. Returns result dict."""
    channel = ch_df["channel"].iloc[0] if "channel" in ch_df.columns else "unknown"
    log(f"\n  Channel: {channel}  ({len(ch_df)} segments)", verbose)

    feat_cols = [c for c in FEATURE_COLS if c in ch_df.columns]
    if len(feat_cols) < cfg["min_components"]:
        return {"channel": channel, "error": f"Too few features ({len(feat_cols)})"}

    X = ch_df[feat_cols].astype(float).values
    has_label = "label" in ch_df.columns and ch_df["label"].notna().any()
    has_train = "train" in ch_df.columns and ch_df["train"].notna().any()

    # Split train / test
    if has_train:
        train_mask = ch_df["train"].fillna(0).astype(int) == 1
    else:
        rng = np.random.default_rng(cfg["random_state"])
        train_mask = rng.random(len(ch_df)) < 0.7

    if has_label:
        nominal_mask = ch_df["label"].fillna(1).astype(int) == 0
    else:
        nominal_mask = np.ones(len(ch_df), dtype=bool)

    train_idx = np.where(train_mask & nominal_mask)[0]
    test_idx  = np.where(~train_mask)[0]

    if len(train_idx) < 4:
        return {"channel": channel, "error": f"Too few nominal training rows ({len(train_idx)})"}
    if len(test_idx) < 2:
        return {"channel": channel, "error": f"Too few test rows ({len(test_idx)})"}

    # Preprocess (scale on training nominal data only)
    X_train = X[train_idx]
    mu = np.nanmean(X_train, axis=0)
    sigma = np.nanstd(X_train, axis=0)
    sigma[sigma == 0] = 1.0

    # Median impute
    for j in range(X.shape[1]):
        nan_mask = ~np.isfinite(X[:, j])
        if nan_mask.any():
            X[nan_mask, j] = mu[j]

    X_norm = (X - mu) / sigma

    X_tr = X_norm[train_idx]
    X_te = X_norm[test_idx]

    # Fit SVD model
    model = SVDAnomalyModel(cfg)
    try:
        model.fit(X_tr)
    except Exception as ex:
        return {"channel": channel, "error": str(ex)}

    # Score and predict on test set
    scores_te = model.score(X_te)
    preds_te  = model.predict(X_te)

    result = {"channel": channel, **model.summary(),
              "n_train": len(train_idx), "n_test": len(test_idx)}

    if has_label:
        y_true = ch_df["label"].fillna(0).astype(int).values[test_idx]
        try:
            metrics = evaluate(y_true, preds_te, scores_te)
            result.update(metrics)
        except Exception as ex:
            result["eval_error"] = str(ex)

    if verbose:
        print(f"    k={result['rank_k']}  "
              f"var={result['cumulative_variance']:.3f}  "
              f"threshold={result['reconstruction_threshold']:.5f}", end="")
        if "roc_auc" in result:
            print(f"  ROC-AUC={result['roc_auc']:.3f}  F1={result['f1']:.3f}", end="")
        print()

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="SISP SVD Anomaly Detection Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--data", default=CONFIG["data_path"], help="Path to segments.csv")
    parser.add_argument("--channel", default=None, help="Run on a single channel (e.g. CADC0894)")
    parser.add_argument("--list-channels", action="store_true", help="List all channels and exit")
    parser.add_argument("--target-variance", type=float, default=CONFIG["target_variance"])
    parser.add_argument("--min-k", type=int, default=CONFIG["min_components"])
    parser.add_argument("--max-k", type=int, default=CONFIG["max_components"])
    parser.add_argument("--threshold-pct", type=int, default=CONFIG["threshold_percentile"])
    parser.add_argument("--no-chi-square", action="store_true")
    parser.add_argument("--plot", action="store_true", help="Show ROC / error distribution plots")
    parser.add_argument("--out", default=None, help="Save results CSV to this path")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    cfg = {**CONFIG}
    cfg["data_path"]            = args.data
    cfg["target_variance"]      = args.target_variance
    cfg["min_components"]       = args.min_k
    cfg["max_components"]       = args.max_k
    cfg["threshold_percentile"] = args.threshold_pct
    cfg["use_chi_square"]       = not args.no_chi_square
    verbose = not args.quiet

    df = load_data(cfg["data_path"], verbose)

    if args.list_channels:
        channels = sorted(df["channel"].unique()) if "channel" in df.columns else ["(no channel col)"]
        print("\nAvailable channels:")
        for ch in channels:
            n = len(df[df["channel"] == ch])
            print(f"  {ch}  ({n} segments)")
        return

    channels = [args.channel] if args.channel else (
        sorted(df["channel"].unique()) if "channel" in df.columns else [None]
    )

    log(f"\nRunning on {len(channels)} channel(s) ...", verbose)
    results = []
    for ch in channels:
        ch_df = df[df["channel"] == ch].copy() if ch else df.copy()
        res = run_channel(ch_df, cfg, verbose)
        results.append(res)

    # Summary table
    results_df = pd.DataFrame(results)
    print("\n" + "=" * 72)
    print("RESULTS SUMMARY")
    print("=" * 72)

    display_cols = ["channel", "rank_k", "cumulative_variance",
                    "n_train", "n_test", "roc_auc", "f1", "precision", "recall"]
    display_cols = [c for c in display_cols if c in results_df.columns]

    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 120)
    print(results_df[display_cols].to_string(index=False))

    if "roc_auc" in results_df.columns:
        valid = results_df["roc_auc"].dropna()
        if len(valid):
            print(f"\nMean ROC-AUC: {valid.mean():.4f}  (n={len(valid)} channels with labels)")

    if args.out:
        results_df.to_csv(args.out, index=False)
        print(f"\nResults saved to: {args.out}")

    if args.plot:
        _plot_results(results_df, df, cfg, channels)


def _plot_results(results_df, df, cfg, channels):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping plots")
        return

    has_roc = "roc_auc" in results_df.columns and results_df["roc_auc"].notna().any()

    n_plots = min(len(channels), 4)
    fig, axes = plt.subplots(1, n_plots, figsize=(5 * n_plots, 4))
    if n_plots == 1:
        axes = [axes]

    for i, (ch, ax) in enumerate(zip(channels[:n_plots], axes)):
        ch_df = df[df["channel"] == ch].copy() if ch else df.copy()
        feat_cols = [c for c in FEATURE_COLS if c in ch_df.columns]
        if len(feat_cols) < 2:
            continue

        X = ch_df[feat_cols].astype(float).values
        mu = np.nanmean(X, axis=0)
        sigma = np.nanstd(X, axis=0)
        sigma[sigma == 0] = 1.0
        X_norm = (X - mu) / sigma

        model = SVDAnomalyModel(cfg)
        train_mask = ch_df["train"].fillna(0).astype(int) == 1 if "train" in ch_df else np.ones(len(ch_df), bool)
        nominal_mask = ch_df["label"].fillna(1).astype(int) == 0 if "label" in ch_df else np.ones(len(ch_df), bool)
        train_idx = np.where(train_mask & nominal_mask)[0]
        if len(train_idx) < 4:
            continue
        try:
            model.fit(X_norm[train_idx])
        except Exception:
            continue

        scores = model.score(X_norm)
        has_label = "label" in ch_df.columns
        if has_label:
            labels = ch_df["label"].fillna(0).astype(int).values
            ax.hist(scores[labels == 0], bins=30, alpha=0.6, color="#00a2ff", label="Nominal")
            ax.hist(scores[labels == 1], bins=30, alpha=0.6, color="#ff4466", label="Anomalous")
            ax.legend(fontsize=8)
        else:
            ax.hist(scores, bins=30, alpha=0.7, color="#00a2ff")
        ax.axvline(model.threshold_, color="#ffcc00", ls="--", lw=1.5,
                   label=f"τ₉₅={model.threshold_:.3f}")
        ax.set(xlabel="Reconstruction error", title=f"{ch or 'all'}  k={model.k}")
        ax.legend(fontsize=7)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
