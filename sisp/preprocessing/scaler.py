"""Standard scaling and post-scale validation for channel features."""

from __future__ import annotations

import pandas as pd
from sklearn.preprocessing import StandardScaler

from config.settings import TEST_MEAN_WARNING_ABS
from sisp.preprocessing.metadata import fit_mask, test_mask
from sisp.utils.logger import get_logger

logger = get_logger()


def fit_scaler(
    X: pd.DataFrame,
    meta: pd.DataFrame,
    continuous_cols: list[str],
) -> StandardScaler:
    """Fit a StandardScaler on fit-row continuous features only."""
    fitting = fit_mask(meta)
    fitting_row_count = int(fitting.sum())
    if fitting_row_count == 0:
        raise RuntimeError(
            "Channel has zero fitting rows in clean metadata; cannot fit StandardScaler."
        )

    scaler = StandardScaler()
    scaler.fit(X.loc[fitting, continuous_cols])
    return scaler


def apply_scaler(
    X: pd.DataFrame,
    scaler: StandardScaler,
    continuous_cols: list[str],
    binary_cols: list[str],
) -> pd.DataFrame:
    """Scale continuous columns and preserve binary columns and column order."""
    scaled_continuous_array = scaler.transform(X[continuous_cols])
    scaled_continuous_df = pd.DataFrame(
        scaled_continuous_array,
        columns=continuous_cols,
        index=X.index,
    )

    binary_set = set(binary_cols)
    combined_columns: dict[str, pd.Series] = {}
    for column in X.columns.tolist():
        if column in binary_set:
            combined_columns[column] = X[column]
        else:
            combined_columns[column] = scaled_continuous_df[column]
    return pd.DataFrame(combined_columns, index=X.index)


def validate_scaling(
    X_scaled: pd.DataFrame,
    meta: pd.DataFrame,
    continuous_cols: list[str],
    binary_cols: list[str],
    channel: str,
) -> None:
    """Log continuous feature moments and binary test counts after scaling."""
    logger.info(f"\nStep 4 validation for channel '{channel}' (continuous features)")
    if not continuous_cols:
        logger.info("No continuous features available for scaling validation.")
    else:
        fitting = fit_mask(meta)
        testing = test_mask(meta)

        scaled_continuous_df = X_scaled[continuous_cols]
        fit_mean = scaled_continuous_df.loc[fitting].mean()
        fit_std = scaled_continuous_df.loc[fitting].std(ddof=0)

        if int(testing.sum()) > 0:
            test_mean = scaled_continuous_df.loc[testing].mean()
            test_std = scaled_continuous_df.loc[testing].std(ddof=0)
        else:
            test_mean = pd.Series(
                [float("nan")] * len(continuous_cols),
                index=continuous_cols,
            )
            test_std = pd.Series(
                [float("nan")] * len(continuous_cols),
                index=continuous_cols,
            )

        validation_df = pd.DataFrame(
            {
                "fit_mean": fit_mean,
                "fit_std": fit_std,
                "test_mean": test_mean,
                "test_std": test_std,
            }
        )
        logger.info(validation_df.to_string(float_format=lambda value: f" {value:.6f}"))

        mean_shift_features = validation_df.index[
            validation_df["test_mean"].abs() > TEST_MEAN_WARNING_ABS
        ].tolist()
        if mean_shift_features:
            logger.info(
                "WARNING: continuous features with |test_mean| > 3.0: "
                + ", ".join(mean_shift_features)
            )
        else:
            logger.info("No continuous feature exceeded |test_mean| > 3.0.")

    logger.info(f"Step 4 binary feature test counts for channel '{channel}'")
    if not binary_cols:
        logger.info("No binary-transformed features for this channel.")
        return

    testing = test_mask(meta)
    test_binary_df = X_scaled.loc[testing, binary_cols]
    for column in binary_cols:
        value_ones = int((test_binary_df[column] == 1).sum())
        value_zeros = int((test_binary_df[column] == 0).sum())
        logger.info(f"  - {column}: value=1 -> {value_ones}, value=0 -> {value_zeros}")
