"""Artifact writer helpers for Parquet, pickle, JSON, and sample summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from config.settings import JSON_INDENT, PARQUET_ENGINE
from sisp.utils.helpers import assert_aligned, get_logger
from sisp.utils.paths import (
    channel_full_path,
    features_path,
    features_scaled_path,
    metadata_clean_path,
    metadata_path,
    sample_default_csv_path,
    sample_features_csv_path,
    sample_metadata_csv_path,
    sample_scaled_default_csv_path,
    sample_scaled_features_csv_path,
    sample_scaled_metadata_csv_path,
)
logger = get_logger()


def _human_readable_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def save_parquet(df: pd.DataFrame, path: Path) -> None:
    """Save a DataFrame to a Parquet file with the configured engine."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, engine=PARQUET_ENGINE)


def save_pickle(obj: Any, path: Path) -> None:
    """Serialize a Python object using joblib."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, path)


def save_json(data: Any, path: Path) -> None:
    """Save a JSON payload with deterministic indentation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=JSON_INDENT)


def load_json(path: Path) -> Any:
    """Load a JSON payload from disk."""
    with path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def print_file_summary(paths: list[Path], header: str, base_dir: Path | None = None) -> None:
    """Log an ordered unique file list with sizes."""
    logger.info(f"\n{header}")
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        size = _human_readable_size(path.stat().st_size)
        if base_dir is None:
            shown = path
        else:
            try:
                shown = path.resolve().relative_to(base_dir.resolve())
            except ValueError:
                shown = path
        logger.info(f"  - {shown} ({size})")


def write_ingest_sample_csvs(
    channel_name: str,
    sample_size: int,
    random_state: int,
    written_files: list[Path],
) -> None:
    """Write aligned default/features/metadata CSV samples for one channel."""
    default_df = pd.read_parquet(channel_full_path(channel_name), engine=PARQUET_ENGINE)
    features_df = pd.read_parquet(features_path(channel_name), engine=PARQUET_ENGINE)
    metadata_df = pd.read_parquet(metadata_path(channel_name), engine=PARQUET_ENGINE)

    assert_aligned(default_df, features_df, context="ingest-sample-load-default-features")
    assert_aligned(default_df, metadata_df, context="ingest-sample-load-default-metadata")

    if len(default_df) == 0:
        raise RuntimeError("Cannot sample rows from an empty channel DataFrame.")

    n_rows = min(sample_size, len(default_df))
    sampled_positions = default_df.sample(n=n_rows, random_state=random_state).index

    default_sample_df = default_df.loc[sampled_positions].reset_index(drop=True)
    features_sample_df = features_df.loc[sampled_positions].reset_index(drop=True)
    metadata_sample_df = metadata_df.loc[sampled_positions].reset_index(drop=True)

    default_csv = sample_default_csv_path(channel_name)
    features_csv = sample_features_csv_path(channel_name)
    metadata_csv = sample_metadata_csv_path(channel_name)

    default_sample_df.to_csv(default_csv, index=False)
    features_sample_df.to_csv(features_csv, index=False)
    metadata_sample_df.to_csv(metadata_csv, index=False)

    written_files.append(default_csv)
    written_files.append(features_csv)
    written_files.append(metadata_csv)

    logger.info(
        "\nSample CSVs written for one channel example "
        f"('{channel_name}', rows={n_rows})."
    )


def write_scaled_sample_csvs(
    channel_name: str,
    sample_size: int,
    random_state: int,
    written_files: list[Path],
) -> None:
    """Write aligned scaled default/features/metadata CSV samples for one channel."""
    features_scaled = pd.read_parquet(features_scaled_path(channel_name), engine=PARQUET_ENGINE)
    metadata_clean = pd.read_parquet(metadata_clean_path(channel_name), engine=PARQUET_ENGINE)

    assert_aligned(features_scaled, metadata_clean, context="scaled-sample-load")

    if len(features_scaled) == 0:
        raise RuntimeError(
            f"Cannot create scaled sample CSVs for channel '{channel_name}' because there are no rows."
        )

    n_rows = min(sample_size, len(features_scaled))
    sampled_index = features_scaled.sample(n=n_rows, random_state=random_state).index

    sample_features = features_scaled.loc[sampled_index].reset_index(drop=True)
    sample_metadata = metadata_clean.loc[sampled_index].reset_index(drop=True)
    assert_aligned(sample_features, sample_metadata, context="scaled-sample-selected")

    sample_default = pd.concat([sample_metadata, sample_features], axis=1)

    sample_default_path = sample_scaled_default_csv_path(channel_name)
    sample_features_path = sample_scaled_features_csv_path(channel_name)
    sample_metadata_path = sample_scaled_metadata_csv_path(channel_name)

    sample_default.to_csv(sample_default_path, index=False)
    sample_features.to_csv(sample_features_path, index=False)
    sample_metadata.to_csv(sample_metadata_path, index=False)

    written_files.append(sample_default_path)
    written_files.append(sample_features_path)
    written_files.append(sample_metadata_path)

    logger.info(
        f"\nScaled sample CSVs written for channel '{channel_name}' "
        f"(rows={n_rows})."
    )
