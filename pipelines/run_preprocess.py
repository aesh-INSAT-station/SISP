"""Run preprocessing steps from missing-value handling through scaling."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import EXCLUDED_CHANNELS, METADATA_COLS, NAN_DROP_THRESHOLD, RANDOM_STATE, SAMPLE_SIZE
from config.settings import PARQUET_ENGINE
from sisp.io.writer import (
    load_json,
    print_file_summary,
    save_json,
    save_parquet,
    save_pickle,
    write_scaled_sample_csvs,
)
from sisp.preprocessing.imputer import audit_nulls, drop_high_null_rows, impute, report_post_imputation
from sisp.preprocessing.scaler import apply_scaler, fit_scaler, validate_scaling
from sisp.preprocessing.variance_handler import (
    apply_binary_transform,
    detect_zero_variance,
    report_binary_transform,
)
from sisp.preprocessing.winsorizer import apply_caps, fit_caps, report_winsorization
from sisp.utils.logger import get_logger
from sisp.utils.paths import (
    binary_features_path,
    channel_from_feature_file,
    feature_files,
    feature_names_path,
    features_clean_path,
    features_path,
    features_scaled_path,
    features_winsor_path,
    metadata_clean_path,
    metadata_path,
    scaler_path,
)
from sisp.utils.validation import assert_aligned

logger = get_logger()


def _read_json_string_list(path: Path) -> list[str]:
    payload = load_json(path)
    if not isinstance(payload, list) or any(not isinstance(item, str) for item in payload):
        raise RuntimeError(f"Invalid JSON list payload in {path}.")
    return payload


def main() -> None:
    """Execute preprocessing with unchanged transforms and artifact outputs."""
    feature_parquet_files = feature_files()
    if not feature_parquet_files:
        raise FileNotFoundError(
            "No per-channel feature files found in data/interim/by_channel with pattern *_features.parquet"
        )

    discovered_channels = [channel_from_feature_file(path) for path in feature_parquet_files]
    logger.info(f"Discovered {len(discovered_channels)} channels: {discovered_channels}")

    channel_names = [
        channel_name
        for channel_name in discovered_channels
        if channel_name not in EXCLUDED_CHANNELS
    ]
    excluded_detected = [
        channel_name
        for channel_name in discovered_channels
        if channel_name in EXCLUDED_CHANNELS
    ]
    for channel_name in excluded_detected:
        logger.info(f"Skipping excluded channel: {channel_name}")

    if not channel_names:
        raise RuntimeError("No channels left to process after exclusion filtering.")

    logger.info(f"Channels selected for processing ({len(channel_names)}): {channel_names}")
    written_files: list[Path] = []

    for channel_name in channel_names:
        X = pd.read_parquet(features_path(channel_name), engine=PARQUET_ENGINE)
        meta = pd.read_parquet(metadata_path(channel_name), engine=PARQUET_ENGINE)

        if set(METADATA_COLS).difference(meta.columns):
            raise KeyError(
                f"Metadata file for channel '{channel_name}' is missing required columns."
            )

        assert_aligned(X, meta, context=f"{channel_name}-step3-load")
        audit_nulls(X, channel_name)

        X_kept, meta_kept, dropped_count = drop_high_null_rows(X, meta, NAN_DROP_THRESHOLD)
        X_imputed, imputed_count, fitting_row_count = impute(X_kept, meta_kept, channel_name)
        report_post_imputation(channel_name, dropped_count, imputed_count, fitting_row_count)

        zero_var_cols = detect_zero_variance(X_imputed, meta_kept)
        X_clean, non_zero_counts = apply_binary_transform(X_imputed, zero_var_cols)
        report_binary_transform(channel_name, zero_var_cols, non_zero_counts)

        assert_aligned(X_clean, meta_kept, context=f"{channel_name}-step3-before-save")

        clean_feature_path = features_clean_path(channel_name)
        clean_metadata_path = metadata_clean_path(channel_name)
        winsorized_feature_path = features_winsor_path(channel_name)

        save_json(X_clean.columns.tolist(), feature_names_path(channel_name))
        save_json(list(zero_var_cols.keys()), binary_features_path(channel_name))

        save_parquet(X_clean, clean_feature_path)
        save_parquet(meta_kept, clean_metadata_path)

        written_files.append(clean_feature_path)
        written_files.append(clean_metadata_path)
        written_files.append(feature_names_path(channel_name))
        written_files.append(binary_features_path(channel_name))

        binary_columns = list(zero_var_cols.keys())
        binary_set = set(binary_columns)
        continuous_columns = [column for column in X_clean.columns if column not in binary_set]

        caps = fit_caps(X_clean, meta_kept, continuous_columns)
        X_winsor, clipped_counts = apply_caps(X_clean, caps)
        report_winsorization(channel_name, clipped_counts)

        save_parquet(X_winsor, winsorized_feature_path)
        written_files.append(winsorized_feature_path)

    for channel_name in channel_names:
        X_winsor = pd.read_parquet(features_winsor_path(channel_name), engine=PARQUET_ENGINE)
        meta_clean = pd.read_parquet(metadata_clean_path(channel_name), engine=PARQUET_ENGINE)

        assert_aligned(X_winsor, meta_clean, context=f"{channel_name}-step4-load")

        expected_feature_names = _read_json_string_list(feature_names_path(channel_name))
        if X_winsor.columns.tolist() != expected_feature_names:
            raise AssertionError(
                f"Feature order mismatch for channel '{channel_name}' between winsorized data "
                f"and {feature_names_path(channel_name).name}."
            )

        binary_columns = _read_json_string_list(binary_features_path(channel_name))
        missing_binary = [column for column in binary_columns if column not in X_winsor.columns]
        if missing_binary:
            raise KeyError(
                f"Channel '{channel_name}' has missing binary feature columns: {missing_binary}"
            )

        feature_columns = X_winsor.columns.tolist()
        binary_set = set(binary_columns)
        continuous_columns = [column for column in feature_columns if column not in binary_set]
        if not continuous_columns:
            raise RuntimeError(
                f"Channel '{channel_name}' has no continuous features to scale after binary "
                "transformation."
            )

        scaler = fit_scaler(X_winsor, meta_clean, continuous_columns)
        X_scaled = apply_scaler(X_winsor, scaler, continuous_columns, binary_columns)

        assert_aligned(X_scaled, meta_clean, context=f"{channel_name}-step4-before-save")

        scaled_feature_path = features_scaled_path(channel_name)
        channel_scaler_path = scaler_path(channel_name)

        save_parquet(X_scaled, scaled_feature_path)
        save_pickle(scaler, channel_scaler_path)

        written_files.append(scaled_feature_path)
        written_files.append(channel_scaler_path)

        validate_scaling(
            X_scaled,
            meta_clean,
            continuous_columns,
            binary_columns,
            channel_name,
        )

    sample_channel = channel_names[0]
    write_scaled_sample_csvs(
        channel_name=sample_channel,
        sample_size=SAMPLE_SIZE,
        random_state=RANDOM_STATE,
        written_files=written_files,
    )

    print_file_summary(written_files, header="Final written files summary", base_dir=PROJECT_ROOT)
    logger.info("\nPreprocessing (steps 3-4) completed successfully.")


if __name__ == "__main__":
    main()
