"""Zero-variance detection and binary transformation for channel features."""

from __future__ import annotations

import pandas as pd

from config.settings import BINARY_EQUALITY_EPSILON, ZERO_VAR_EPSILON
from sisp.preprocessing.metadata import fit_mask
from sisp.utils.logger import get_logger

logger = get_logger()


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
