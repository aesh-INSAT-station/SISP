"""Missing-value auditing, row dropping, and median imputation helpers."""

from __future__ import annotations

import pandas as pd

from sisp.preprocessing.metadata import fit_mask
from sisp.utils.logger import get_logger
from sisp.utils.validation import assert_aligned, assert_no_nulls

logger = get_logger()


def audit_nulls(X: pd.DataFrame, channel: str) -> None:
    """Log per-column NaN counts and percentages for one channel."""
    total_rows = len(X)
    nan_counts = X.isna().sum()
    columns_with_nan = nan_counts[nan_counts > 0]

    logger.info(f"\nStep 3 audit for channel '{channel}'")
    logger.info(f"Total rows: {total_rows}")

    if columns_with_nan.empty:
        logger.info("No missing values found in this channel.")
        return

    report_df = pd.DataFrame(
        {
            "column": columns_with_nan.index,
            "nan_count": columns_with_nan.values.astype(int),
            "pct_rows": (columns_with_nan.values / max(total_rows, 1)) * 100,
        }
    )
    report_df["pct_rows"] = report_df["pct_rows"].map(lambda value: f"{value:.2f}%")
    logger.info(report_df.to_string(index=False))


def drop_high_null_rows(
    X: pd.DataFrame,
    meta: pd.DataFrame,
    threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Drop rows with NaN fraction above threshold in feature columns."""
    assert_aligned(X, meta, context="drop_high_null_rows-input")
    nan_fraction_per_row = X.isna().mean(axis=1)
    keep_mask = nan_fraction_per_row <= threshold
    dropped_count = int((~keep_mask).sum())

    X_kept = X.loc[keep_mask].reset_index(drop=True)
    meta_kept = meta.loc[keep_mask].reset_index(drop=True)
    assert_aligned(X_kept, meta_kept, context="drop_high_null_rows-output")
    return X_kept, meta_kept, dropped_count


def impute(
    X: pd.DataFrame,
    meta: pd.DataFrame,
    channel: str,
) -> tuple[pd.DataFrame, int, int]:
    """Median-impute missing feature values using fit rows with safe fallback."""
    assert_aligned(X, meta, context="impute-input")
    fitting_mask = fit_mask(meta)
    fitting_row_count = int(fitting_mask.sum())

    if fitting_row_count == 0:
        raise RuntimeError(
            f"Channel '{channel}' has zero fitting rows where "
            "train=True AND anomaly=0."
        )

    values_to_impute = int(X.isna().sum().sum())

    medians: dict[str, float] = {}
    for column in X.columns:
        fitting_median = X.loc[fitting_mask, column].median(skipna=True)
        if pd.isna(fitting_median):
            overall_median = X[column].median(skipna=True)
            if pd.isna(overall_median):
                raise RuntimeError(
                    f"Channel '{channel}', column '{column}' has all NaN values "
                    "even after fallback."
                )
            medians[column] = float(overall_median)
            logger.info(
                f"WARNING: channel '{channel}', column '{column}' fitting median "
                "is NaN; using overall median fallback."
            )
        else:
            medians[column] = float(fitting_median)

    imputed_df = X.fillna(value=medians)
    assert_no_nulls(imputed_df, context=f"impute-{channel}")
    return imputed_df, values_to_impute, fitting_row_count


def report_post_imputation(
    channel: str,
    dropped_count: int,
    imputed_count: int,
    fitting_row_count: int,
) -> None:
    """Log post-imputation row and value counts."""
    logger.info(f"Step 3 post-imputation for channel '{channel}'")
    logger.info(f"Rows dropped (>30% NaN features): {dropped_count}")
    logger.info(f"Values imputed: {imputed_count}")
    logger.info(f"Remaining clean train=True AND anomaly=0 rows: {fitting_row_count}")
