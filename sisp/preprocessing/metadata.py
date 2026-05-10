"""Metadata and split-mask helpers shared across preprocessing and anomaly stages."""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from config.settings import (
    ANOMALY_FALSE_TOKENS,
    ANOMALY_TRUE_TOKENS,
    FEATURE_COLS,
    METADATA_COLS,
    TRAIN_FALSE_TOKENS,
    TRAIN_TRUE_TOKENS,
)
from sisp.utils.helpers import assert_aligned, assert_numeric_only, get_logger

logger = get_logger()


def normalize_binary_series(
    series: pd.Series,
    true_tokens: Iterable[str],
    false_tokens: Iterable[str],
) -> pd.Series:
    """Normalize mixed binary labels into pandas nullable booleans."""
    true_set = {token.lower() for token in true_tokens}
    false_set = {token.lower() for token in false_tokens}

    def convert(value: object) -> object:
        if pd.isna(value):
            return pd.NA
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False
        text_value = str(value).strip().lower()
        if text_value in true_set:
            return True
        if text_value in false_set:
            return False
        return pd.NA

    return series.map(convert).astype("boolean")


def normalize_train_flag(series: pd.Series) -> pd.Series:
    """Normalize train labels to nullable booleans."""
    return normalize_binary_series(
        series,
        true_tokens=TRAIN_TRUE_TOKENS,
        false_tokens=TRAIN_FALSE_TOKENS,
    )


def normalize_anomaly_flag(series: pd.Series) -> pd.Series:
    """Normalize anomaly labels to nullable booleans."""
    return normalize_binary_series(
        series,
        true_tokens=ANOMALY_TRUE_TOKENS,
        false_tokens=ANOMALY_FALSE_TOKENS,
    )


def separate(df: pd.DataFrame, meta_cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a channel dataframe into features and metadata tables."""
    metadata_df = df[meta_cols].copy()
    features_df = df[FEATURE_COLS].copy()
    assert_aligned(features_df, metadata_df, context="separate")
    return features_df, metadata_df


def coerce_numeric_features(X: pd.DataFrame) -> pd.DataFrame:
    """Convert feature columns to int64 or float64 as in the original ingest script."""
    X = X.copy()
    for column in X.columns:
        if not pd.api.types.is_numeric_dtype(X[column]):
            X[column] = pd.to_numeric(X[column], errors="raise")

        if pd.api.types.is_bool_dtype(X[column]):
            X[column] = X[column].astype("int64")
        elif pd.api.types.is_integer_dtype(X[column]):
            X[column] = X[column].astype("int64")
        else:
            X[column] = X[column].astype("float64")

    disallowed = {
        column: str(dtype)
        for column, dtype in X.dtypes.items()
        if str(dtype) not in {"int64", "float64"}
    }
    if disallowed:
        raise TypeError(f"Feature matrix has non-numeric dtypes: {disallowed}")

    leaked_metadata = sorted(set(METADATA_COLS).intersection(X.columns))
    if leaked_metadata:
        raise AssertionError(f"Metadata columns leaked into feature matrix: {leaked_metadata}")

    assert_numeric_only(X, context="coerce_numeric_features")
    return X


def fit_mask(meta: pd.DataFrame) -> pd.Series:
    """Return mask for rows where train=True and anomaly=False."""
    train_flag = normalize_train_flag(meta["train"])
    anomaly_flag = normalize_anomaly_flag(meta["anomaly"])
    return ((train_flag == True) & (anomaly_flag == False)).fillna(False).astype(bool)


def train_mask(meta: pd.DataFrame) -> pd.Series:
    """Return mask for train rows."""
    train_flag = normalize_train_flag(meta["train"])
    return (train_flag == True).fillna(False).astype(bool)


def test_mask(meta: pd.DataFrame) -> pd.Series:
    """Return mask for test rows."""
    train_flag = normalize_train_flag(meta["train"])
    return (train_flag == False).fillna(False).astype(bool)


def report_channel_metadata(channel: str, X: pd.DataFrame, meta: pd.DataFrame) -> None:
    """Log the per-channel shape, split labels, and NaN feature counts."""
    train_normalized = normalize_train_flag(meta["train"])
    anomaly_normalized = normalize_anomaly_flag(meta["anomaly"])

    train_count = int((train_normalized == True).sum())
    test_count = int((train_normalized == False).sum())
    train_unknown = int(train_normalized.isna().sum())

    anomaly_count = int((anomaly_normalized == True).sum())
    nominal_count = int((anomaly_normalized == False).sum())
    anomaly_unknown = int(anomaly_normalized.isna().sum())

    nan_counts = X.isna().sum()

    logger.info(f"\nStep 2 report for channel '{channel}'")
    logger.info(f"  X shape: {X.shape[0]} x {X.shape[1]}")
    logger.info(
        "  train/test segments: "
        f"train={train_count}, test={test_count}, unknown={train_unknown}"
    )
    logger.info(
        "  anomalous/nominal segments: "
        f"anomalous={anomaly_count}, nominal={nominal_count}, unknown={anomaly_unknown}"
    )
    logger.info("  NaN values per feature column:")
    for column, nan_count in nan_counts.items():
        logger.info(f"    - {column}: {int(nan_count)}")
