"""Prediction, result assembly, and evaluation reporting for anomaly outputs."""

from __future__ import annotations

import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, roc_auc_score

from config.settings import ANOMALY_THRESHOLD_PCTILE
from sisp.preprocessing.metadata import fit_mask, normalize_anomaly_flag, test_mask, train_mask
from sisp.utils.logger import get_logger

logger = get_logger()


def predict(errors, threshold: float) -> pd.Series:
    """Return anomaly predictions as int64 using thresholded reconstruction error."""
    error_series = pd.Series(errors, dtype="float64")
    return (error_series > threshold).astype("int64")


def build_results(
    meta: pd.DataFrame,
    errors,
    threshold: float,
    predictions: pd.Series,
) -> pd.DataFrame:
    """Build the per-row result table with metadata and anomaly scores."""
    error_series = pd.Series(errors, dtype="float64")
    return pd.DataFrame(
        {
            "segment": meta["segment"],
            "train": meta["train"],
            "anomaly": meta["anomaly"],
            "reconstruction_error": error_series,
            "threshold": float(threshold),
            "predicted_anomaly": predictions.astype("int64"),
        }
    )


def _compute_split_metrics(y_true: pd.Series, y_pred: pd.Series, scores: pd.Series) -> dict[str, float | int]:
    if len(y_true) == 0:
        return {
            "tp": 0,
            "fp": 0,
            "tn": 0,
            "fn": 0,
            "precision": float("nan"),
            "recall": float("nan"),
            "f1": float("nan"),
            "roc_auc": float("nan"),
            "n_rows": 0,
        }

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )

    if y_true.nunique() < 2:
        roc_auc = float("nan")
    else:
        roc_auc = float(roc_auc_score(y_true, scores))

    return {
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "roc_auc": roc_auc,
        "n_rows": int(len(y_true)),
    }


def _print_split_report(split_name: str, metrics: dict[str, float | int]) -> None:
    logger.info(f"{split_name} rows: {metrics['n_rows']}")
    logger.info(
        "Confusion matrix (TP, FP, TN, FN): "
        f"({metrics['tp']}, {metrics['fp']}, {metrics['tn']}, {metrics['fn']})"
    )
    logger.info(
        "Precision/Recall/F1: "
        f"{metrics['precision']:.6f} / {metrics['recall']:.6f} / {metrics['f1']:.6f}"
    )
    logger.info(f"ROC-AUC: {metrics['roc_auc']:.6f}")


def report(results: pd.DataFrame, channel: str) -> None:
    """Log threshold, split metrics, and class-wise error means for one channel."""
    threshold = float(results["threshold"].iloc[0])
    errors = pd.Series(results["reconstruction_error"], dtype="float64")
    predictions = results["predicted_anomaly"].astype("int64")

    anomaly_flag = normalize_anomaly_flag(results["anomaly"])
    if bool(anomaly_flag.isna().any()):
        raise RuntimeError(
            f"Channel '{channel}' contains unrecognized anomaly labels in metadata."
        )
    y_true = anomaly_flag.astype("int64")

    fit_errors = errors.loc[fit_mask(results)].reset_index(drop=True)
    if fit_errors.empty:
        raise RuntimeError(
            f"Channel '{channel}' has zero fitting rows while computing threshold."
        )

    test_metrics = _compute_split_metrics(
        y_true.loc[test_mask(results)].reset_index(drop=True),
        predictions.loc[test_mask(results)].reset_index(drop=True),
        errors.loc[test_mask(results)].reset_index(drop=True),
    )
    train_metrics = _compute_split_metrics(
        y_true.loc[train_mask(results)].reset_index(drop=True),
        predictions.loc[train_mask(results)].reset_index(drop=True),
        errors.loc[train_mask(results)].reset_index(drop=True),
    )

    nominal_mean = float(errors.loc[y_true == 0].mean())
    anomaly_mean = float(errors.loc[y_true == 1].mean())

    logger.info(f"\nStep 6 - channel '{channel}'")
    logger.info(
        f"Threshold T ({ANOMALY_THRESHOLD_PCTILE}th percentile of fit-row errors): "
        f"{threshold:.6f}"
    )
    logger.info(
        "Fit-row error mean/std: "
        f"{float(fit_errors.mean()):.6f} / {float(fit_errors.std(ddof=0)):.6f}"
    )
    _print_split_report("TEST (train=False)", test_metrics)
    _print_split_report("TRAIN (train=True)", train_metrics)
    logger.info(f"Mean reconstruction error for anomaly=0: {nominal_mean:.6f}")
    logger.info(f"Mean reconstruction error for anomaly=1: {anomaly_mean:.6f}")
