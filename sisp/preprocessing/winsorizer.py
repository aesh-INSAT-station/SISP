"""Winsorization helpers for continuous feature capping."""

from __future__ import annotations

import pandas as pd

from config.settings import WINSOR_HIGH, WINSOR_LOW
from sisp.preprocessing.metadata import fit_mask
from sisp.utils.logger import get_logger

logger = get_logger()


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
