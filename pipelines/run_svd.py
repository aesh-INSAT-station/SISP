"""Run SVD model fitting and anomaly scoring for each channel."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    ANOMALY_THRESHOLD_PCTILE,
    EXCLUDED_CHANNELS,
    METADATA_COLS,
    PARQUET_ENGINE,
    SVD_K_MAX,
    SVD_K_MIN,
    SVD_VARIANCE_TARGET,
)
from sisp.anomaly.evaluator import build_results, predict, report
from sisp.anomaly.scorer import compute_threshold, reconstruction_error
from sisp.anomaly.svd_model import fit_svd, select_rank
from sisp.io.writer import print_file_summary, save_parquet, save_pickle
from sisp.preprocessing.metadata import fit_mask
from sisp.utils.logger import get_logger
from sisp.utils.paths import (
    channel_from_scaled_feature_file,
    features_scaled_path,
    metadata_clean_path,
    results_path,
    scaled_feature_files,
    svd_path,
)
from sisp.utils.validation import assert_aligned

logger = get_logger()


def _validate_metadata_columns(meta: pd.DataFrame, channel_name: str) -> None:
    missing = set(METADATA_COLS).difference(meta.columns)
    if missing:
        missing_fmt = ", ".join(sorted(missing))
        raise KeyError(
            f"Metadata for channel '{channel_name}' is missing required columns: {missing_fmt}"
        )


def _load_channel_inputs(channel_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    feature_path = features_scaled_path(channel_name)
    metadata_path = metadata_clean_path(channel_name)

    if not feature_path.exists():
        raise FileNotFoundError(
            f"Missing scaled features for channel '{channel_name}': {feature_path}"
        )
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Missing clean metadata for channel '{channel_name}': {metadata_path}"
        )

    features_scaled = pd.read_parquet(feature_path, engine=PARQUET_ENGINE)
    metadata_clean = pd.read_parquet(metadata_path, engine=PARQUET_ENGINE)

    _validate_metadata_columns(metadata_clean, channel_name)
    assert_aligned(features_scaled, metadata_clean, context=f"{channel_name}-load")
    return features_scaled, metadata_clean


def main() -> None:
    """Execute SVD fit and score steps with unchanged output schema."""
    scaled_files = scaled_feature_files()
    if not scaled_files:
        raise FileNotFoundError(
            "No scaled feature files found in data/interim/by_channel matching '*_features_scaled.parquet'."
        )

    discovered_channels = [channel_from_scaled_feature_file(path) for path in scaled_files]
    channel_names = [
        channel_name
        for channel_name in discovered_channels
        if channel_name not in EXCLUDED_CHANNELS
    ]
    excluded_found = [
        channel_name
        for channel_name in discovered_channels
        if channel_name in EXCLUDED_CHANNELS
    ]

    logger.info(f"Discovered {len(discovered_channels)} channels: {discovered_channels}")
    for channel_name in excluded_found:
        logger.info(f"Skipping excluded channel: {channel_name}")

    if not channel_names:
        raise RuntimeError("No channels left to process after applying exclusion list.")

    logger.info(f"Channels selected for SVD pipeline ({len(channel_names)}): {channel_names}")
    written_files: list[Path] = []

    for channel_name in channel_names:
        features_scaled, meta_clean = _load_channel_inputs(channel_name)
        X_fit = features_scaled.loc[fit_mask(meta_clean)].reset_index(drop=True)

        if X_fit.empty:
            raise RuntimeError(
                f"Channel '{channel_name}' has zero rows where train=True AND anomaly=0; "
                "cannot fit TruncatedSVD."
            )

        logger.info(f"\nStep 5 - channel '{channel_name}'")
        logger.info(f"X_fit shape: {X_fit.shape}")

        k, variance = select_rank(
            X_fit,
            variance_target=SVD_VARIANCE_TARGET,
            k_min=SVD_K_MIN,
            k_max=SVD_K_MAX,
        )
        svd_model = fit_svd(X_fit, k)

        model_path = svd_path(channel_name)
        save_pickle(svd_model, model_path)
        written_files.append(model_path)

        ratios = pd.Series(svd_model.explained_variance_ratio_, dtype="float64")
        ratios_fmt = ", ".join(f"{value:.6f}" for value in ratios.tolist())

        logger.info(f"Chosen k: {k}")
        logger.info(f"Cumulative explained variance at k: {variance:.6f}")
        logger.info(f"Component explained variance ratios: [{ratios_fmt}]")

    for channel_name in channel_names:
        features_scaled, meta_clean = _load_channel_inputs(channel_name)
        model_path = svd_path(channel_name)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Expected fitted SVD model for channel '{channel_name}' at {model_path}"
            )

        from joblib import load

        svd_model = load(model_path)
        errors = reconstruction_error(svd_model, features_scaled.reset_index(drop=True))
        threshold = compute_threshold(errors, meta_clean.reset_index(drop=True), ANOMALY_THRESHOLD_PCTILE)
        predictions = predict(errors, threshold)

        results = build_results(meta_clean.reset_index(drop=True), errors, threshold, predictions)

        assert_aligned(results[["reconstruction_error"]], features_scaled, context=f"{channel_name}-results")

        output_path = results_path(channel_name)
        save_parquet(results, output_path)
        written_files.append(output_path)

        report(results, channel_name)

    print_file_summary(written_files, header="Final written files summary", base_dir=PROJECT_ROOT)
    logger.info("\nSVD pipeline (steps 5-6) completed successfully.")


if __name__ == "__main__":
    main()
