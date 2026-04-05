from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.preprocessing import StandardScaler


FEATURE_FILE_SUFFIX = "_features.parquet"
METADATA_COLUMNS = ["segment", "anomaly", "train", "channel"]
EXCLUDED_CHANNELS = {"CADC0886", "CADC0890"}
ZERO_VARIANCE_STD_EPS = 1e-8
BINARY_EQUALITY_EPS = 1e-8
WINSOR_LOWER_Q = 0.01
WINSOR_UPPER_Q = 0.99


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


def normalize_binary_series(
    series: pd.Series,
    true_tokens: set[str],
    false_tokens: set[str],
) -> pd.Series:

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


def normalize_train_flag(series: pd.Series) -> pd.Series:
    return normalize_binary_series(
        series,
        true_tokens={"1", "true", "t", "yes", "y", "train"},
        false_tokens={"0", "false", "f", "no", "n", "test"},
    )


def normalize_anomaly_flag(series: pd.Series) -> pd.Series:
    return normalize_binary_series(
        series,
        true_tokens={"1", "true", "t", "yes", "y", "anomaly", "anomalous"},
        false_tokens={"0", "false", "f", "no", "n", "nominal", "normal"},
    )


def get_fitting_mask(metadata_df: pd.DataFrame) -> pd.Series:
    train_flag = normalize_train_flag(metadata_df["train"])
    anomaly_flag = normalize_anomaly_flag(metadata_df["anomaly"])
    return ((train_flag == True) & (anomaly_flag == False)).fillna(False).astype(bool)


def get_test_mask(metadata_df: pd.DataFrame) -> pd.Series:
    train_flag = normalize_train_flag(metadata_df["train"])
    return (train_flag == False).fillna(False).astype(bool)


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
    fitting_mask: pd.Series,
) -> tuple[pd.DataFrame, int]:
    fitting_row_count = int(fitting_mask.sum())
    if fitting_row_count == 0:
        raise RuntimeError(
            f"Channel '{channel_name}' has zero fitting rows where "
            "train=True AND anomaly=0."
        )

    values_to_impute = int(features_df.isna().sum().sum())

    medians: dict[str, float] = {}
    for column in features_df.columns:
        fitting_median = features_df.loc[fitting_mask, column].median(skipna=True)
        if pd.isna(fitting_median):
            overall_median = features_df[column].median(skipna=True)
            if pd.isna(overall_median):
                raise RuntimeError(
                    f"Channel '{channel_name}', column '{column}' has all NaN values "
                    "even after fallback."
                )
            medians[column] = float(overall_median)
            print(
                f"WARNING: channel '{channel_name}', column '{column}' fitting median "
                "is NaN; using overall median fallback."
            )
        else:
            medians[column] = float(fitting_median)

    imputed_df = features_df.fillna(value=medians)
    remaining_nans = int(imputed_df.isna().sum().sum())
    if remaining_nans != 0:
        remaining_per_col = imputed_df.isna().sum()
        remaining_per_col = remaining_per_col[remaining_per_col > 0].to_dict()
        raise RuntimeError(
            f"NaN imputation failed for channel '{channel_name}'. Remaining NaNs: "
            f"{remaining_per_col}"
        )
    return imputed_df, values_to_impute


def print_step3_post_imputation(
    channel_name: str,
    dropped_count: int,
    imputed_count: int,
    fitting_row_count: int,
) -> None:
    print(f"Step 3 post-imputation for channel '{channel_name}'")
    print(f"Rows dropped (>30% NaN features): {dropped_count}")
    print(f"Values imputed: {imputed_count}")
    print(f"Remaining clean train=True AND anomaly=0 rows: {fitting_row_count}")


def write_json_file(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)


def read_json_string_list(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as file_handle:
        payload = json.load(file_handle)
    if not isinstance(payload, list) or any(not isinstance(item, str) for item in payload):
        raise RuntimeError(f"Invalid JSON list payload in {path}.")
    return payload


def apply_zero_variance_binary_transform(
    channel_name: str,
    features_df: pd.DataFrame,
    fitting_mask: pd.Series,
) -> tuple[pd.DataFrame, list[str], dict[str, float], dict[str, int]]:
    fitting_df = features_df.loc[fitting_mask]
    if fitting_df.empty:
        raise RuntimeError(
            f"Channel '{channel_name}' has zero fitting rows for zero-variance checks."
        )

    fitting_std = fitting_df.std(ddof=0)
    binary_columns = fitting_std.index[fitting_std <= ZERO_VARIANCE_STD_EPS].tolist()

    transformed_df = features_df.copy()
    constant_values: dict[str, float] = {}
    non_zero_counts: dict[str, int] = {}

    for column in binary_columns:
        constant_value = float(fitting_df[column].iloc[0])
        constant_values[column] = constant_value

        equal_mask = (transformed_df[column] - constant_value).abs() <= BINARY_EQUALITY_EPS
        binary_series = (~equal_mask).astype("int64")
        transformed_df[column] = binary_series
        non_zero_counts[column] = int(binary_series.sum())

    return transformed_df, binary_columns, constant_values, non_zero_counts


def print_binary_transform_report(
    channel_name: str,
    binary_columns: list[str],
    constant_values: dict[str, float],
    non_zero_counts: dict[str, int],
) -> None:
    print(f"Step 3.1 zero-variance handling for channel '{channel_name}'")
    if not binary_columns:
        print(f"{channel_name}: no zero-variance features needed binary transformation.")
        return

    constants_text = ", ".join(f"{constant_values[column]:.6g}" for column in binary_columns)
    print(
        f"{channel_name}: binary-transformed zero-variance features: {binary_columns} "
        f"(constant={constants_text})"
    )
    for column in binary_columns:
        print(
            f"  - {column}: non-zero rows across all train/test rows = "
            f"{non_zero_counts[column]}"
        )


def winsorize_non_binary_features(
    features_df: pd.DataFrame,
    fitting_mask: pd.Series,
    binary_columns: list[str],
) -> tuple[pd.DataFrame, dict[str, int]]:
    binary_set = set(binary_columns)
    non_binary_columns = [column for column in features_df.columns if column not in binary_set]

    winsorized_df = features_df.copy()
    clipped_counts: dict[str, int] = {}

    if not non_binary_columns:
        return winsorized_df, clipped_counts

    fitting_df = features_df.loc[fitting_mask, non_binary_columns]
    for column in non_binary_columns:
        p01 = float(fitting_df[column].quantile(WINSOR_LOWER_Q, interpolation="linear"))
        p99 = float(fitting_df[column].quantile(WINSOR_UPPER_Q, interpolation="linear"))
        if p01 > p99:
            p01, p99 = p99, p01

        column_values = winsorized_df[column]
        lower_hits = int((column_values < p01).sum())
        upper_hits = int((column_values > p99).sum())
        total_clipped = lower_hits + upper_hits
        if total_clipped > 0:
            clipped_counts[column] = total_clipped

        winsorized_df[column] = column_values.clip(lower=p01, upper=p99)

    return winsorized_df, clipped_counts


def print_winsorization_report(channel_name: str, clipped_counts: dict[str, int]) -> None:
    print(f"Step 3.2 winsorization for channel '{channel_name}'")
    if not clipped_counts:
        print("No non-binary feature values were clipped.")
        return

    print("Columns with clipped values (total clipped count):")
    for column, count in clipped_counts.items():
        print(f"  - {column}: {count}")


def print_continuous_scaling_validation(
    channel_name: str,
    scaled_continuous_df: pd.DataFrame,
    fitting_mask: pd.Series,
    test_mask: pd.Series,
) -> None:
    print(f"\nStep 4 validation for channel '{channel_name}' (continuous features)")
    if scaled_continuous_df.shape[1] == 0:
        print("No continuous features available for scaling validation.")
        return

    fit_mean = scaled_continuous_df.loc[fitting_mask].mean()
    fit_std = scaled_continuous_df.loc[fitting_mask].std(ddof=0)

    if int(test_mask.sum()) > 0:
        test_mean = scaled_continuous_df.loc[test_mask].mean()
        test_std = scaled_continuous_df.loc[test_mask].std(ddof=0)
    else:
        test_mean = pd.Series(
            [float("nan")] * scaled_continuous_df.shape[1],
            index=scaled_continuous_df.columns,
        )
        test_std = pd.Series(
            [float("nan")] * scaled_continuous_df.shape[1],
            index=scaled_continuous_df.columns,
        )

    validation_df = pd.DataFrame(
        {
            "fit_mean": fit_mean,
            "fit_std": fit_std,
            "test_mean": test_mean,
            "test_std": test_std,
        }
    )
    print(validation_df.to_string(float_format=lambda value: f"{value: .6f}"))

    mean_shift_features = validation_df.index[validation_df["test_mean"].abs() > 3.0].tolist()
    if mean_shift_features:
        print(
            "WARNING: continuous features with |test_mean| > 3.0: "
            + ", ".join(mean_shift_features)
        )
    else:
        print("No continuous feature exceeded |test_mean| > 3.0.")


def print_binary_test_value_counts(
    channel_name: str,
    scaled_df: pd.DataFrame,
    binary_columns: list[str],
    test_mask: pd.Series,
) -> None:
    print(f"Step 4 binary feature test counts for channel '{channel_name}'")
    if not binary_columns:
        print("No binary-transformed features for this channel.")
        return

    test_binary_df = scaled_df.loc[test_mask, binary_columns]
    for column in binary_columns:
        value_ones = int((test_binary_df[column] == 1).sum())
        value_zeros = int((test_binary_df[column] == 0).sum())
        print(f"  - {column}: value=1 -> {value_ones}, value=0 -> {value_zeros}")


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


def write_scaled_channel_csv_samples(
    by_channel_dir: Path,
    channel_name: str,
    written_files: list[Path],
    sample_size: int = 5,
    random_state: int = 42,
) -> None:
    scaled_feature_path = by_channel_dir / f"{channel_name}_features_scaled.parquet"
    clean_metadata_path = by_channel_dir / f"{channel_name}_metadata_clean.parquet"

    features_scaled = pd.read_parquet(scaled_feature_path, engine="pyarrow")
    metadata_clean = pd.read_parquet(clean_metadata_path, engine="pyarrow")
    assert_row_alignment(features_scaled, metadata_clean, channel_name, "scaled-sample-load")

    if len(features_scaled) == 0:
        raise RuntimeError(
            f"Cannot create scaled sample CSVs for channel '{channel_name}' because there are no rows."
        )

    n_rows = min(sample_size, len(features_scaled))
    sampled_index = features_scaled.sample(n=n_rows, random_state=random_state).index

    sample_features = features_scaled.loc[sampled_index].reset_index(drop=True)
    sample_metadata = metadata_clean.loc[sampled_index].reset_index(drop=True)
    assert_row_alignment(sample_features, sample_metadata, channel_name, "scaled-sample-selected")

    sample_default = pd.concat([sample_metadata, sample_features], axis=1)

    sample_default_path = by_channel_dir / f"{channel_name}_sample_scaled_default.csv"
    sample_features_path = by_channel_dir / f"{channel_name}_sample_scaled_features.csv"
    sample_metadata_path = by_channel_dir / f"{channel_name}_sample_scaled_metadata.csv"

    sample_default.to_csv(sample_default_path, index=False)
    sample_features.to_csv(sample_features_path, index=False)
    sample_metadata.to_csv(sample_metadata_path, index=False)

    written_files.append(sample_default_path)
    written_files.append(sample_features_path)
    written_files.append(sample_metadata_path)

    print(
        f"\nScaled sample CSVs written for channel '{channel_name}' "
        f"(rows={n_rows})."
    )


def main() -> None:
    project_root = Path(__file__).resolve().parent
    by_channel_dir = project_root / "data" / "interim" / "by_channel"
    scalers_dir = project_root / "data" / "interim" / "scalers"
    svd_dir = project_root / "data" / "interim" / "svd"
    scalers_dir.mkdir(parents=True, exist_ok=True)
    svd_dir.mkdir(parents=True, exist_ok=True)

    feature_files = sorted(by_channel_dir.glob(f"*{FEATURE_FILE_SUFFIX}"))
    if not feature_files:
        raise FileNotFoundError(
            f"No per-channel feature files found in {by_channel_dir} with pattern "
            f"*{FEATURE_FILE_SUFFIX}"
        )

    discovered_channels = [channel_from_feature_file(path) for path in feature_files]
    print(f"Discovered {len(discovered_channels)} channels: {discovered_channels}")

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
        print(f"Skipping excluded channel: {channel_name}")

    if not channel_names:
        raise RuntimeError("No channels left to process after exclusion filtering.")
    print(f"Channels selected for processing ({len(channel_names)}): {channel_names}")

    written_files: list[Path] = []

    # Step 3: missing value handling + binary transform + winsorization.
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

        features_kept = features_df.loc[keep_mask].reset_index(drop=True)
        metadata_kept = metadata_df.loc[keep_mask].reset_index(drop=True)
        assert_row_alignment(features_kept, metadata_kept, channel_name, "step3-after-drop")

        fitting_mask = get_fitting_mask(metadata_kept)

        features_imputed, imputed_count = impute_channel_features(
            channel_name,
            features_kept,
            fitting_mask,
        )
        fitting_row_count = int(fitting_mask.sum())
        print_step3_post_imputation(
            channel_name,
            dropped_count,
            imputed_count,
            fitting_row_count,
        )

        (
            features_clean,
            binary_columns,
            constant_values,
            non_zero_counts,
        ) = apply_zero_variance_binary_transform(
            channel_name,
            features_imputed,
            fitting_mask,
        )
        print_binary_transform_report(
            channel_name,
            binary_columns,
            constant_values,
            non_zero_counts,
        )

        assert_row_alignment(features_clean, metadata_kept, channel_name, "step3-before-save")

        clean_feature_path = by_channel_dir / f"{channel_name}_features_clean.parquet"
        clean_metadata_path = by_channel_dir / f"{channel_name}_metadata_clean.parquet"
        winsorized_feature_path = by_channel_dir / f"{channel_name}_features_winsorized.parquet"

        feature_names_path = svd_dir / f"{channel_name}_feature_names.json"
        binary_features_path = svd_dir / f"{channel_name}_binary_features.json"

        write_json_file(feature_names_path, features_clean.columns.tolist())
        write_json_file(binary_features_path, binary_columns)

        features_clean.to_parquet(clean_feature_path, index=False, engine="pyarrow")
        metadata_kept.to_parquet(clean_metadata_path, index=False, engine="pyarrow")

        winsorized_df, clipped_counts = winsorize_non_binary_features(
            features_clean,
            fitting_mask,
            binary_columns,
        )
        print_winsorization_report(channel_name, clipped_counts)
        winsorized_df.to_parquet(winsorized_feature_path, index=False, engine="pyarrow")

        written_files.append(clean_feature_path)
        written_files.append(clean_metadata_path)
        written_files.append(winsorized_feature_path)
        written_files.append(feature_names_path)
        written_files.append(binary_features_path)

    # Step 4: standardization from winsorized features (continuous only).
    for channel_name in channel_names:
        winsorized_feature_path = by_channel_dir / f"{channel_name}_features_winsorized.parquet"
        clean_metadata_path = by_channel_dir / f"{channel_name}_metadata_clean.parquet"
        feature_names_path = svd_dir / f"{channel_name}_feature_names.json"
        binary_features_path = svd_dir / f"{channel_name}_binary_features.json"

        features_winsorized = pd.read_parquet(winsorized_feature_path, engine="pyarrow")
        metadata_clean = pd.read_parquet(clean_metadata_path, engine="pyarrow")

        assert_row_alignment(features_winsorized, metadata_clean, channel_name, "step4-load")

        expected_feature_names = read_json_string_list(feature_names_path)
        if features_winsorized.columns.tolist() != expected_feature_names:
            raise AssertionError(
                f"Feature order mismatch for channel '{channel_name}' between winsorized data "
                f"and {feature_names_path.name}."
            )

        binary_columns = read_json_string_list(binary_features_path)
        missing_binary_columns = [
            column for column in binary_columns if column not in features_winsorized.columns
        ]
        if missing_binary_columns:
            raise KeyError(
                f"Channel '{channel_name}' has missing binary feature columns: "
                f"{missing_binary_columns}"
            )

        feature_columns = features_winsorized.columns.tolist()
        binary_set = set(binary_columns)
        continuous_columns = [column for column in feature_columns if column not in binary_set]
        if not continuous_columns:
            raise RuntimeError(
                f"Channel '{channel_name}' has no continuous features to scale after binary "
                "transformation."
            )

        fitting_mask = get_fitting_mask(metadata_clean)
        fitting_row_count = int(fitting_mask.sum())
        if fitting_row_count == 0:
            raise RuntimeError(
                f"Channel '{channel_name}' has zero fitting rows in clean metadata; "
                "cannot fit StandardScaler."
            )
        test_mask = get_test_mask(metadata_clean)

        scaler = StandardScaler()
        scaler.fit(features_winsorized.loc[fitting_mask, continuous_columns])
        scaled_continuous_array = scaler.transform(features_winsorized[continuous_columns])
        scaled_continuous_df = pd.DataFrame(
            scaled_continuous_array,
            columns=continuous_columns,
            index=features_winsorized.index,
        )

        combined_columns: dict[str, pd.Series] = {}
        for column in feature_columns:
            if column in binary_set:
                combined_columns[column] = features_winsorized[column]
            else:
                combined_columns[column] = scaled_continuous_df[column]
        scaled_df = pd.DataFrame(combined_columns, index=features_winsorized.index)

        assert_row_alignment(scaled_df, metadata_clean, channel_name, "step4-before-save")

        scaled_feature_path = by_channel_dir / f"{channel_name}_features_scaled.parquet"
        scaler_path = scalers_dir / f"{channel_name}_scaler.pkl"

        scaled_df.to_parquet(scaled_feature_path, index=False, engine="pyarrow")
        joblib.dump(scaler, scaler_path)

        written_files.append(scaled_feature_path)
        written_files.append(scaler_path)

        print_continuous_scaling_validation(
            channel_name,
            scaled_df[continuous_columns],
            fitting_mask,
            test_mask,
        )
        print_binary_test_value_counts(channel_name, scaled_df, binary_columns, test_mask)

    # Create one scaled sample after scaling is complete.
    sample_channel = channel_names[0]
    write_scaled_channel_csv_samples(
        by_channel_dir=by_channel_dir,
        channel_name=sample_channel,
        written_files=written_files,
        sample_size=5,
        random_state=42,
    )

    print_written_files_summary(project_root, written_files)
    print("\nPreprocessing (steps 3-4) completed successfully.")


if __name__ == "__main__":
    main()