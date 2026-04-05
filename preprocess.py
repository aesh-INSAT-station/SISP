from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.preprocessing import StandardScaler


FEATURE_FILE_SUFFIX = "_features.parquet"
METADATA_COLUMNS = ["segment", "anomaly", "train", "channel"]


def human_readable_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def channel_from_feature_file(feature_path: Path) -> str:
    if not feature_path.name.endswith(FEATURE_FILE_SUFFIX):
        raise ValueError(f"Invalid feature file name: {feature_path.name}")
    return feature_path.name[: -len(FEATURE_FILE_SUFFIX)]


def normalize_train_flag(series: pd.Series) -> pd.Series:
    true_tokens = {"1", "true", "t", "yes", "y", "train"}
    false_tokens = {"0", "false", "f", "no", "n", "test"}

    def convert(value: object) -> object:
        if pd.isna(value):
            return pd.NA
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False
        text_value = str(value).strip().lower()
        if text_value in true_tokens:
            return True
        if text_value in false_tokens:
            return False
        return pd.NA

    return series.map(convert).astype("boolean")


def assert_row_alignment(
    features_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    channel_name: str,
    stage_name: str,
) -> None:
    if len(features_df) != len(metadata_df):
        raise AssertionError(
            f"Row alignment failed for channel '{channel_name}' at {stage_name}: "
            f"features rows={len(features_df)}, metadata rows={len(metadata_df)}"
        )


def print_missing_value_audit(channel_name: str, features_df: pd.DataFrame) -> None:
    total_rows = len(features_df)
    nan_counts = features_df.isna().sum()
    columns_with_nan = nan_counts[nan_counts > 0]

    print(f"\nStep 3 audit for channel '{channel_name}'")
    print(f"Total rows: {total_rows}")

    if columns_with_nan.empty:
        print("No missing values found in this channel.")
        return

    report_df = pd.DataFrame(
        {
            "column": columns_with_nan.index,
            "nan_count": columns_with_nan.values.astype(int),
            "pct_rows": (columns_with_nan.values / max(total_rows, 1)) * 100,
        }
    )
    report_df["pct_rows"] = report_df["pct_rows"].map(lambda value: f"{value:.2f}%")
    print(report_df.to_string(index=False))


def impute_channel_features(
    channel_name: str,
    features_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
) -> pd.DataFrame:
    train_flag = normalize_train_flag(metadata_df["train"])
    train_mask = train_flag == True

    if int(train_mask.sum()) == 0:
        raise RuntimeError(
            f"Channel '{channel_name}' has zero train rows after filtering; "
            "cannot compute train-based medians."
        )

    medians: dict[str, float] = {}
    for column in features_df.columns:
        train_median = features_df.loc[train_mask, column].median(skipna=True)
        if pd.isna(train_median):
            overall_median = features_df[column].median(skipna=True)
            if pd.isna(overall_median):
                raise RuntimeError(
                    f"Channel '{channel_name}', column '{column}' has all NaN values "
                    "even after fallback."
                )
            medians[column] = float(overall_median)
            print(
                f"WARNING: channel '{channel_name}', column '{column}' train median "
                "is NaN; using overall median fallback."
            )
        else:
            medians[column] = float(train_median)

    imputed_df = features_df.fillna(value=medians)
    remaining_nans = int(imputed_df.isna().sum().sum())
    if remaining_nans != 0:
        remaining_per_col = imputed_df.isna().sum()
        remaining_per_col = remaining_per_col[remaining_per_col > 0].to_dict()
        raise RuntimeError(
            f"NaN imputation failed for channel '{channel_name}'. Remaining NaNs: "
            f"{remaining_per_col}"
        )
    return imputed_df


def print_scaling_validation(channel_name: str, scaled_df: pd.DataFrame, metadata_df: pd.DataFrame) -> None:
    train_flag = normalize_train_flag(metadata_df["train"])
    train_mask = train_flag == True
    test_mask = train_flag == False

    train_mean = scaled_df.loc[train_mask].mean()
    train_std = scaled_df.loc[train_mask].std(ddof=0)

    if int(test_mask.sum()) > 0:
        test_mean = scaled_df.loc[test_mask].mean()
        test_std = scaled_df.loc[test_mask].std(ddof=0)
    else:
        test_mean = pd.Series([float("nan")] * scaled_df.shape[1], index=scaled_df.columns)
        test_std = pd.Series([float("nan")] * scaled_df.shape[1], index=scaled_df.columns)

    validation_df = pd.DataFrame(
        {
            "train_mean": train_mean,
            "train_std": train_std,
            "test_mean": test_mean,
            "test_std": test_std,
        }
    )

    print(f"\nStep 4 validation for channel '{channel_name}'")
    print(validation_df.to_string(float_format=lambda value: f"{value: .6f}"))

    shifted_features = validation_df.index[validation_df["test_mean"].abs() > 3.0].tolist()
    if shifted_features:
        print(
            "Potential distribution shift (|test_mean| > 3.0): "
            + ", ".join(shifted_features)
        )
    else:
        print("No feature exceeded the |test_mean| > 3.0 shift threshold.")


def print_written_files_summary(project_root: Path, files: list[Path]) -> None:
    print("\nFinal written files summary")
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        relative_path = path.resolve().relative_to(project_root.resolve())
        print(f"  - {relative_path} ({human_readable_size(path.stat().st_size)})")


def main() -> None:
    project_root = Path(__file__).resolve().parent
    by_channel_dir = project_root / "data" / "interim" / "by_channel"
    scalers_dir = project_root / "data" / "interim" / "scalers"
    scalers_dir.mkdir(parents=True, exist_ok=True)

    feature_files = sorted(by_channel_dir.glob(f"*{FEATURE_FILE_SUFFIX}"))
    if not feature_files:
        raise FileNotFoundError(
            f"No per-channel feature files found in {by_channel_dir} with pattern "
            f"*{FEATURE_FILE_SUFFIX}"
        )

    channel_names = [channel_from_feature_file(path) for path in feature_files]
    print(f"Discovered {len(channel_names)} channels: {channel_names}")

    written_files: list[Path] = []

    # Step 3: missing value handling.
    for channel_name in channel_names:
        feature_path = by_channel_dir / f"{channel_name}_features.parquet"
        metadata_path = by_channel_dir / f"{channel_name}_metadata.parquet"

        if not metadata_path.exists():
            raise FileNotFoundError(f"Missing metadata file for channel '{channel_name}': {metadata_path}")

        features_df = pd.read_parquet(feature_path, engine="pyarrow")
        metadata_df = pd.read_parquet(metadata_path, engine="pyarrow")

        if set(METADATA_COLUMNS).difference(metadata_df.columns):
            raise KeyError(
                f"Metadata file for channel '{channel_name}' is missing required columns."
            )

        assert_row_alignment(features_df, metadata_df, channel_name, "step3-load")
        print_missing_value_audit(channel_name, features_df)

        nan_fraction_per_row = features_df.isna().mean(axis=1)
        keep_mask = nan_fraction_per_row <= 0.30
        dropped_count = int((~keep_mask).sum())
        print(f"Rows dropped (>30% NaN features): {dropped_count}")

        features_kept = features_df.loc[keep_mask].reset_index(drop=True)
        metadata_kept = metadata_df.loc[keep_mask].reset_index(drop=True)
        assert_row_alignment(features_kept, metadata_kept, channel_name, "step3-after-drop")

        features_clean = impute_channel_features(channel_name, features_kept, metadata_kept)
        assert_row_alignment(features_clean, metadata_kept, channel_name, "step3-before-save")

        clean_feature_path = by_channel_dir / f"{channel_name}_features_clean.parquet"
        clean_metadata_path = by_channel_dir / f"{channel_name}_metadata_clean.parquet"

        features_clean.to_parquet(clean_feature_path, index=False, engine="pyarrow")
        metadata_kept.to_parquet(clean_metadata_path, index=False, engine="pyarrow")

        written_files.append(clean_feature_path)
        written_files.append(clean_metadata_path)

    # Step 4: standardization from clean files.
    for channel_name in channel_names:
        clean_feature_path = by_channel_dir / f"{channel_name}_features_clean.parquet"
        clean_metadata_path = by_channel_dir / f"{channel_name}_metadata_clean.parquet"

        features_clean = pd.read_parquet(clean_feature_path, engine="pyarrow")
        metadata_clean = pd.read_parquet(clean_metadata_path, engine="pyarrow")

        assert_row_alignment(features_clean, metadata_clean, channel_name, "step4-load")

        train_flag = normalize_train_flag(metadata_clean["train"])
        train_mask = train_flag == True
        if int(train_mask.sum()) == 0:
            raise RuntimeError(
                f"Channel '{channel_name}' has zero train rows in clean metadata; "
                "cannot fit StandardScaler."
            )

        scaler = StandardScaler()
        scaler.fit(features_clean.loc[train_mask])
        scaled_array = scaler.transform(features_clean)
        scaled_df = pd.DataFrame(
            scaled_array,
            columns=features_clean.columns,
            index=features_clean.index,
        )

        assert_row_alignment(scaled_df, metadata_clean, channel_name, "step4-before-save")

        scaled_feature_path = by_channel_dir / f"{channel_name}_features_scaled.parquet"
        scaler_path = scalers_dir / f"{channel_name}_scaler.pkl"

        scaled_df.to_parquet(scaled_feature_path, index=False, engine="pyarrow")
        joblib.dump(scaler, scaler_path)

        written_files.append(scaled_feature_path)
        written_files.append(scaler_path)

        print_scaling_validation(channel_name, scaled_df, metadata_clean)

    print_written_files_summary(project_root, written_files)
    print("\nPreprocessing (steps 3-4) completed successfully.")


if __name__ == "__main__":
    main()