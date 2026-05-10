"""Inspect per-channel parquet artifacts and scaler metadata as tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sisp.utils.helpers import get_logger

logger = get_logger()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect per-channel parquet artifacts and scaler metadata as tables."
    )
    parser.add_argument(
        "--channel",
        default="CADC0872",
        help="Channel name prefix used in artifact filenames (default: CADC0872).",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=10,
        help="Rows to display per table. Use 0 or a negative value to display all rows.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Project root that contains the data/interim directory.",
    )
    return parser.parse_args()


def print_dataframe(title: str, df: pd.DataFrame, rows: int) -> None:
    logger.info(f"\n=== {title} ===")
    logger.info(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")

    preview_df = df if rows <= 0 else df.head(rows)
    if preview_df.empty:
        logger.info("[EMPTY TABLE]")
        return

    with pd.option_context(
        "display.max_columns", None,
        "display.width", 160,
        "display.max_colwidth", 60,
        "display.expand_frame_repr", False,
    ):
        logger.info(preview_df.to_string(index=False))


def print_missing(label: str, path: Path) -> None:
    logger.info(f"\n=== {label} ===")
    logger.info(f"[MISSING] {path}")


def load_and_print_parquet(label: str, path: Path, rows: int) -> None:
    if not path.exists():
        print_missing(label, path)
        return

    df = pd.read_parquet(path, engine="pyarrow")
    print_dataframe(f"{label} ({path.name})", df, rows)


def to_feature_names(scaler: Any, feature_count: int) -> list[str]:
    if hasattr(scaler, "feature_names_in_"):
        raw_names = list(getattr(scaler, "feature_names_in_"))
        if len(raw_names) == feature_count:
            return [str(name) for name in raw_names]
    return [f"feature_{index}" for index in range(feature_count)]


def load_and_print_scaler(label: str, path: Path, rows: int) -> None:
    if not path.exists():
        print_missing(label, path)
        return

    scaler = joblib.load(path)

    summary_rows: list[dict[str, Any]] = [
        {"attribute": "class", "value": scaler.__class__.__name__},
    ]
    for attribute in ["with_mean", "with_std", "n_features_in_", "n_samples_seen_"]:
        if hasattr(scaler, attribute):
            value = getattr(scaler, attribute)
            if hasattr(value, "tolist"):
                value = value.tolist()
            summary_rows.append({"attribute": attribute, "value": str(value)})

    summary_df = pd.DataFrame(summary_rows)
    print_dataframe(f"{label} summary ({path.name})", summary_df, rows=0)

    if not hasattr(scaler, "mean_") or not hasattr(scaler, "scale_"):
        logger.info("Scaler has no mean_/scale_ attributes to display.")
        return

    means = list(getattr(scaler, "mean_"))
    scales = list(getattr(scaler, "scale_"))
    variances = list(getattr(scaler, "var_")) if hasattr(scaler, "var_") else [None] * len(means)

    feature_count = min(len(means), len(scales), len(variances))
    feature_names = to_feature_names(scaler, feature_count)

    details_df = pd.DataFrame(
        {
            "feature": feature_names,
            "mean_": means[:feature_count],
            "scale_": scales[:feature_count],
            "var_": variances[:feature_count],
        }
    )
    print_dataframe(f"{label} feature stats ({path.name})", details_df, rows)


def main() -> None:
    args = parse_args()

    by_channel_dir = args.project_root / "data" / "interim" / "by_channel"
    scalers_dir = args.project_root / "data" / "interim" / "scalers"

    artifacts: list[tuple[str, Path, str]] = [
        ("Metadata", by_channel_dir / f"{args.channel}_metadata.parquet", "parquet"),
        ("Metadata Clean", by_channel_dir / f"{args.channel}_metadata_clean.parquet", "parquet"),
        ("Features", by_channel_dir / f"{args.channel}_features.parquet", "parquet"),
        ("Features Scaled", by_channel_dir / f"{args.channel}_features_scaled.parquet", "parquet"),
        ("Features Clean", by_channel_dir / f"{args.channel}_features_clean.parquet", "parquet"),
        ("Scaler", scalers_dir / f"{args.channel}_scaler.pkl", "scaler"),
    ]

    logger.info(f"Project root: {args.project_root}")
    logger.info(f"Channel: {args.channel}")
    logger.info(f"Rows shown per table: {'ALL' if args.rows <= 0 else args.rows}")

    for label, path, artifact_type in artifacts:
        if artifact_type == "parquet":
            load_and_print_parquet(label, path, args.rows)
        else:
            load_and_print_scaler(label, path, args.rows)


if __name__ == "__main__":
    main()
