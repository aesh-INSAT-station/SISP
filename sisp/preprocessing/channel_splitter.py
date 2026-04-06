"""Channel splitting helpers used by the ingest and preprocessing pipelines."""

from __future__ import annotations

import re

import pandas as pd

from sisp.utils.logger import get_logger

logger = get_logger()


def channel_label(value: object) -> str:
    """Convert channel values to a stable printable label."""
    return "<NA>" if pd.isna(value) else str(value)


def sanitize_channel_name(channel_name: str) -> str:
    """Sanitize a channel label for use in file names."""
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", channel_name.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "unknown_channel"


def make_unique_name(base_name: str, used_names: set[str]) -> str:
    """Ensure each channel filename stem is unique."""
    candidate = base_name
    index = 2
    while candidate in used_names:
        candidate = f"{base_name}_{index}"
        index += 1
    used_names.add(candidate)
    return candidate


def split_by_channel(df: pd.DataFrame, excluded: set[str]) -> dict[str, pd.DataFrame]:
    """Split a full dataframe by channel with optional exclusions."""
    channel_dfs: dict[str, pd.DataFrame] = {}
    for channel_value, channel_df in df.groupby("channel", dropna=False, sort=False):
        channel_name = channel_label(channel_value)
        if channel_name in excluded:
            continue
        channel_dfs[channel_name] = channel_df.copy()
    return channel_dfs


def build_channel_file_map(channel_names: list[str]) -> dict[str, str]:
    """Build original channel label to safe filename stem mapping."""
    used_names: set[str] = set()
    channel_file_map: dict[str, str] = {}
    for channel_name in channel_names:
        channel_file_map[channel_name] = make_unique_name(
            sanitize_channel_name(channel_name),
            used_names,
        )
    return channel_file_map


def report_split_summary(df: pd.DataFrame) -> None:
    """Log a summary of the source dataset channels and row counts."""
    unique_channels = [channel_label(value) for value in df["channel"].drop_duplicates()]
    rows_per_channel = df["channel"].map(channel_label).value_counts(dropna=False)

    logger.info("\nStep 1 summary")
    logger.info(f"Total rows: {len(df)}")
    logger.info(f"Unique channel values ({len(unique_channels)}): {unique_channels}")
    logger.info("Row count per channel:")
    for channel_name, row_count in rows_per_channel.items():
        logger.info(f"  - {channel_name}: {int(row_count)}")
