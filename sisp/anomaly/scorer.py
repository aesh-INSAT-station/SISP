"""Reconstruction scoring and threshold computation for SVD anomalies."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD

from sisp.preprocessing.metadata import fit_mask


def reconstruction_error(svd: TruncatedSVD, X: pd.DataFrame) -> np.ndarray:
    """Return per-row squared reconstruction error from a fitted SVD model."""
    projected = svd.transform(X)
    reconstructed = svd.inverse_transform(projected)
    residual = X.to_numpy(copy=False) - reconstructed
    return (residual * residual).sum(axis=1)


def compute_threshold(errors: np.ndarray, meta: pd.DataFrame, percentile: float) -> float:
    """Compute fit-row threshold from reconstruction errors at the given percentile."""
    fitting = fit_mask(meta)
    fit_errors = pd.Series(errors, dtype="float64").loc[fitting].reset_index(drop=True)
    if fit_errors.empty:
        raise RuntimeError("Channel has zero fitting rows while computing threshold.")

    quantile = percentile / 100.0
    return float(fit_errors.quantile(quantile, interpolation="linear"))
