"""Run the ingest pipeline from raw download to per-channel base artifacts."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import METADATA_COLS, RANDOM_STATE, SAMPLE_SIZE, ZENODO_URL
from sisp.io.loader import download_dataset, load_raw
from sisp.io.writer import print_file_summary, save_parquet, write_ingest_sample_csvs
from sisp.preprocessing.metadata import coerce_numeric_features, report_channel_metadata, separate
from sisp.utils.helpers import assert_aligned, get_logger
from sisp.utils.paths import BY_CHANNEL_DIR, RAW_DIR, channel_full_path, ensure_dirs, features_path, metadata_path

logger = get_logger()


def _channel_label(value: object) -> str:
    return "<NA>" if pd.isna(value) else str(value)


def _sanitize_channel_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", name.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "unknown_channel"


def _make_unique_name(base_name: str, used_names: set[str]) -> str:
    candidate = base_name
    index = 2
    while candidate in used_names:
        candidate = f"{base_name}_{index}"
        index += 1
    used_names.add(candidate)
    return candidate


def split_by_channel(df: pd.DataFrame, excluded: set[str]) -> dict[str, pd.DataFrame]:
    channel_dfs: dict[str, pd.DataFrame] = {}
    for channel_value, channel_df in df.groupby("channel", dropna=False, sort=False):
        channel_name = _channel_label(channel_value)
        if channel_name in excluded:
            continue
        channel_dfs[channel_name] = channel_df.copy()
    return channel_dfs


def build_channel_file_map(channel_names: list[str]) -> dict[str, str]:
    used_names: set[str] = set()
    return {
        name: _make_unique_name(_sanitize_channel_name(name), used_names)
        for name in channel_names
    }


def report_split_summary(df: pd.DataFrame) -> None:
    unique_channels = [_channel_label(v) for v in df["channel"].drop_duplicates()]
    rows_per_channel = df["channel"].map(_channel_label).value_counts(dropna=False)
    logger.info("\nStep 1 summary")
    logger.info(f"Total rows: {len(df)}")
    logger.info(f"Unique channel values ({len(unique_channels)}): {unique_channels}")
    logger.info("Row count per channel:")
    for channel_name, row_count in rows_per_channel.items():
        logger.info(f"  - {channel_name}: {int(row_count)}")


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
