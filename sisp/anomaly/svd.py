"""SVD rank selection, model fitting, and reconstruction error scoring."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD

from config.settings import RANDOM_STATE
from sisp.preprocessing.metadata import fit_mask


def select_rank(
    X_fit: pd.DataFrame,
    variance_target: float,
    k_min: int,
    k_max: int,
) -> tuple[int, float]:
    """Select rank k based on cumulative explained variance with bounds."""
    n_fit_rows = X_fit.shape[0]
    n_features = X_fit.shape[1]
    max_full_components = min(n_features, n_fit_rows - 1)

    if max_full_components < k_min:
        raise RuntimeError(
            "Cannot satisfy rank constraints with current fitting set: "
            f"n_fit_rows={n_fit_rows}, n_features={n_features}, "
            f"max_components={max_full_components}, required_min_k={k_min}."
        )

    svd_probe = TruncatedSVD(n_components=max_full_components, random_state=RANDOM_STATE)
    svd_probe.fit(X_fit)

    explained_ratio = pd.Series(svd_probe.explained_variance_ratio_, dtype="float64").fillna(0.0)
    cumulative = explained_ratio.cumsum()

    meets_target = cumulative >= variance_target
    if bool(meets_target.any()):
        k_target = int(meets_target.idxmax()) + 1
    else:
        k_target = int(len(cumulative))

    upper_bound = min(k_max, max_full_components)
    k_selected = min(max(k_target, k_min), upper_bound)
    cumulative_at_k = float(cumulative.iloc[k_selected - 1])

    return k_selected, cumulative_at_k


def fit_svd(X_fit: pd.DataFrame, k: int) -> TruncatedSVD:
    """Fit and return a TruncatedSVD model with deterministic random state."""
    model = TruncatedSVD(n_components=k, random_state=RANDOM_STATE)
    model.fit(X_fit)
    return model


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
