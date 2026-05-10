"""Missing-value handling, zero-variance binary transforms, and winsorization."""

from __future__ import annotations

import pandas as pd

from config.settings import BINARY_EQUALITY_EPSILON, NAN_DROP_THRESHOLD, WINSOR_HIGH, WINSOR_LOW, ZERO_VAR_EPSILON
from sisp.preprocessing.metadata import fit_mask
from sisp.utils.helpers import assert_aligned, assert_no_nulls, get_logger

logger = get_logger()


# ---------------------------------------------------------------------------
# Imputation
# ---------------------------------------------------------------------------

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
    threshold: float = NAN_DROP_THRESHOLD,
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


# ---------------------------------------------------------------------------
# Zero-variance binary transform
# ---------------------------------------------------------------------------

def detect_zero_variance(X: pd.DataFrame, meta: pd.DataFrame) -> dict[str, float]:
    """Detect zero-variance columns on fit rows and return their constants."""
    fitting_mask = fit_mask(meta)
    fitting_df = X.loc[fitting_mask]
    if fitting_df.empty:
        raise RuntimeError("Channel has zero fitting rows for zero-variance checks.")

    fitting_std = fitting_df.std(ddof=0)
    zero_var_columns = fitting_std.index[fitting_std <= ZERO_VAR_EPSILON].tolist()
    return {column: float(fitting_df[column].iloc[0]) for column in zero_var_columns}


def apply_binary_transform(
    X: pd.DataFrame,
    zero_var_cols: dict[str, float],
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Transform zero-variance columns into binary deviation indicators."""
    transformed_df = X.copy()
    non_zero_counts: dict[str, int] = {}

    for column, constant_value in zero_var_cols.items():
        equal_mask = (transformed_df[column] - constant_value).abs() <= BINARY_EQUALITY_EPSILON
        binary_series = (~equal_mask).astype("int64")
        transformed_df[column] = binary_series
        non_zero_counts[column] = int(binary_series.sum())

    return transformed_df, non_zero_counts


def report_binary_transform(
    channel: str,
    zero_var_cols: dict[str, float],
    non_zero_counts: dict[str, int],
) -> None:
    """Log binary transformation details for one channel."""
    logger.info(f"Step 3.1 zero-variance handling for channel '{channel}'")
    if not zero_var_cols:
        logger.info(f"{channel}: no zero-variance features needed binary transformation.")
        return

    binary_columns = list(zero_var_cols.keys())
    constants_text = ", ".join(f"{zero_var_cols[column]:.6g}" for column in binary_columns)
    logger.info(
        f"{channel}: binary-transformed zero-variance features: {binary_columns} "
        f"(constant={constants_text})"
    )
    for column in binary_columns:
        logger.info(
            f"  - {column}: non-zero rows across all train/test rows = "
            f"{non_zero_counts[column]}"
        )


# ---------------------------------------------------------------------------
# Winsorization
# ---------------------------------------------------------------------------

def fit_caps(
    X: pd.DataFrame,
    meta: pd.DataFrame,
    continuous_cols: list[str],
) -> dict[str, tuple[float, float]]:
    """Fit lower and upper winsorization caps from fit rows only."""
    fitting_df = X.loc[fit_mask(meta), continuous_cols]
    caps: dict[str, tuple[float, float]] = {}

    for column in continuous_cols:
        lower = float(fitting_df[column].quantile(WINSOR_LOW, interpolation="linear"))
        upper = float(fitting_df[column].quantile(WINSOR_HIGH, interpolation="linear"))
        if lower > upper:
            lower, upper = upper, lower
        caps[column] = (lower, upper)

    return caps


def apply_caps(
    X: pd.DataFrame,
    caps: dict[str, tuple[float, float]],
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply fitted caps and track clipped value counts per column."""
    winsorized_df = X.copy()
    clipped_counts: dict[str, int] = {}

    for column, (lower, upper) in caps.items():
        column_values = winsorized_df[column]
        lower_hits = int((column_values < lower).sum())
        upper_hits = int((column_values > upper).sum())
        total_clipped = lower_hits + upper_hits
        if total_clipped > 0:
            clipped_counts[column] = total_clipped
        winsorized_df[column] = column_values.clip(lower=lower, upper=upper)

    return winsorized_df, clipped_counts


def report_winsorization(channel: str, clipped_counts: dict[str, int]) -> None:
    """Log winsorization clipping counts for one channel."""
    logger.info(f"Step 3.2 winsorization for channel '{channel}'")
    if not clipped_counts:
        logger.info("No non-binary feature values were clipped.")
        return

    logger.info("Columns with clipped values (total clipped count):")
    for column, count in clipped_counts.items():
        logger.info(f"  - {column}: {count}")
