"""Run the ingest pipeline from raw download to per-channel base artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import METADATA_COLS, RANDOM_STATE, SAMPLE_SIZE, ZENODO_URL
from sisp.io.loader import download_dataset, load_raw
from sisp.io.writer import print_file_summary, save_parquet, write_ingest_sample_csvs
from sisp.preprocessing.channel_splitter import (
    build_channel_file_map,
    report_split_summary,
    split_by_channel,
)
from sisp.preprocessing.metadata import coerce_numeric_features, report_channel_metadata, separate
from sisp.utils.logger import get_logger
from sisp.utils.paths import BY_CHANNEL_DIR, RAW_DIR, channel_full_path, ensure_dirs, features_path, metadata_path
from sisp.utils.validation import assert_aligned

logger = get_logger()


def main() -> None:
    """Execute ingest steps with unchanged behavior and artifact names."""
    ensure_dirs()
    written_files: list[Path] = []

    dataset_path = download_dataset(ZENODO_URL, RAW_DIR, written_files=written_files)
    df = load_raw(dataset_path)
    report_split_summary(df)

    channel_dfs = split_by_channel(df, excluded=set())
    channel_file_map = build_channel_file_map(list(channel_dfs.keys()))

    for channel_name, channel_df in channel_dfs.items():
        safe_channel_name = channel_file_map[channel_name]
        full_channel_path = channel_full_path(safe_channel_name)
        save_parquet(channel_df, full_channel_path)
        written_files.append(full_channel_path)

    logger.info(
        "\nSaved per-channel full DataFrames to "
        f"{BY_CHANNEL_DIR} ({len(channel_dfs)} files)."
    )

    for channel_name, channel_df in channel_dfs.items():
        metadata_df_label = channel_file_map[channel_name]

        X_df, metadata_df = separate(channel_df, METADATA_COLS)
        assert_aligned(X_df, metadata_df, context=f"{channel_name}-ingest-separate")
        X_df = coerce_numeric_features(X_df)
        report_channel_metadata(channel_name, X_df, metadata_df)

        channel_features_path = features_path(metadata_df_label)
        channel_metadata_path = metadata_path(metadata_df_label)

        save_parquet(X_df, channel_features_path)
        save_parquet(metadata_df, channel_metadata_path)

        written_files.append(channel_features_path)
        written_files.append(channel_metadata_path)

    if channel_file_map:
        example_channel = next(iter(channel_file_map.values()))
        write_ingest_sample_csvs(
            channel_name=example_channel,
            sample_size=SAMPLE_SIZE,
            random_state=RANDOM_STATE,
            written_files=written_files,
        )

    print_file_summary(written_files, header="Confirmation: files written", base_dir=PROJECT_ROOT)
    logger.info("\nIngestion and preprocessing (steps 0-2) completed successfully.")


if __name__ == "__main__":
    main()
