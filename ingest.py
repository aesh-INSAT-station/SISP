from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests


ZENODO_RECORD_ID = "12588359"
ZENODO_RECORD_API = f"https://zenodo.org/api/records/{ZENODO_RECORD_ID}"

METADATA_COLUMNS = ["segment", "anomaly", "train", "channel"]
FEATURE_COLUMNS = [
    "sampling",
    "duration",
    "len",
    "mean",
    "var",
    "std",
    "skew",
    "kurtosis",
    "n_peaks",
    "smooth10_n_peaks",
    "smooth20_n_peaks",
    "diff_peaks",
    "diff2_peaks",
    "diff_var",
    "diff2_var",
    "gaps_squared",
    "len_weighted",
    "var_div_duration",
    "var_div_len",
]


def sanitize_channel_name(channel_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", channel_name.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "unknown_channel"


def make_unique_name(base_name: str, used_names: set[str]) -> str:
    candidate = base_name
    index = 2
    while candidate in used_names:
        candidate = f"{base_name}_{index}"
        index += 1
    used_names.add(candidate)
    return candidate


def human_readable_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def pick_best_zenodo_file(files: list[dict]) -> dict:
    def score(file_info: dict) -> tuple[int, str]:
        filename = str(file_info.get("key") or file_info.get("filename") or "")
        suffix = Path(filename).suffix.lower()
        if suffix == ".parquet":
            priority = 0
        elif suffix == ".csv":
            priority = 1
        elif suffix == ".zip":
            priority = 2
        else:
            priority = 3
        return priority, filename.lower()

    return sorted(files, key=score)[0]


def download_opssat_dataset(raw_dir: Path, written_files: list[Path]) -> Path:
    token = os.getenv("ZENODO_TOKEN")
    params = {"access_token": token} if token else None

    record_response = requests.get(ZENODO_RECORD_API, params=params, timeout=60)
    record_response.raise_for_status()
    record = record_response.json()

    files = record.get("files", [])
    if not files:
        raise RuntimeError("Zenodo record contains no downloadable files.")

    selected_file = pick_best_zenodo_file(files)
    filename = selected_file.get("key") or selected_file.get("filename")
    if not filename:
        raise RuntimeError("Could not determine dataset filename from Zenodo metadata.")

    links = selected_file.get("links", {})
    download_url = links.get("download") or links.get("self") or links.get("content")
    if not download_url:
        raise RuntimeError("Could not find a download URL in Zenodo metadata.")

    raw_path = raw_dir / filename
    print(f"Downloading Zenodo file: {filename}")
    with requests.get(download_url, params=params, stream=True, timeout=120) as response:
        response.raise_for_status()
        with raw_path.open("wb") as file_handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_handle.write(chunk)

    written_files.append(raw_path)
    print(f"Saved raw file to: {raw_path}")
    return raw_path


def extract_dataset_table(raw_zip_path: Path, raw_dir: Path, written_files: list[Path]) -> Path:
    extract_dir = raw_dir / "extracted" / sanitize_channel_name(raw_zip_path.stem)
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(raw_zip_path, "r") as zip_handle:
        candidates = [
            member
            for member in zip_handle.namelist()
            if not member.endswith("/")
            and Path(member).suffix.lower() in {".csv", ".parquet"}
        ]

        if not candidates:
            raise RuntimeError(
                "ZIP archive does not contain a CSV or Parquet dataset file."
            )

        def candidate_score(member: str) -> tuple[int, str]:
            suffix = Path(member).suffix.lower()
            priority = 0 if suffix == ".parquet" else 1
            return priority, member.lower()

        selected_member = sorted(candidates, key=candidate_score)[0]
        extracted_path = extract_dir / Path(selected_member).name

        with zip_handle.open(selected_member) as src, extracted_path.open("wb") as dst:
            shutil.copyfileobj(src, dst)

    written_files.append(extracted_path)
    print(f"Extracted dataset file from ZIP: {extracted_path}")
    return extracted_path


def resolve_dataset_path(raw_path: Path, raw_dir: Path, written_files: list[Path]) -> Path:
    suffix = raw_path.suffix.lower()
    if suffix in {".csv", ".parquet"}:
        return raw_path
    if suffix == ".zip":
        return extract_dataset_table(raw_path, raw_dir, written_files)

    raise RuntimeError(
        f"Unsupported raw dataset format '{raw_path.suffix}'. Expected CSV, Parquet, or ZIP."
    )


def load_dataset(dataset_path: Path) -> pd.DataFrame:
    suffix = dataset_path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(dataset_path, engine="pyarrow")
    if suffix == ".csv":
        return pd.read_csv(dataset_path, low_memory=False)
    raise RuntimeError(f"Unsupported dataset file format: {dataset_path}")


def validate_required_columns(df: pd.DataFrame) -> None:
    required_columns = METADATA_COLUMNS + FEATURE_COLUMNS
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        missing_formatted = ", ".join(missing_columns)
        raise KeyError(f"Dataset is missing required columns: {missing_formatted}")


def channel_label(value: object) -> str:
    return "<NA>" if pd.isna(value) else str(value)


def normalize_binary_series(
    series: pd.Series,
    true_tokens: Iterable[str],
    false_tokens: Iterable[str],
) -> pd.Series:
    true_set = {token.lower() for token in true_tokens}
    false_set = {token.lower() for token in false_tokens}

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
        if text_value in true_set:
            return True
        if text_value in false_set:
            return False
        return pd.NA

    return series.map(convert).astype("boolean")


def ensure_numeric_features(x_df: pd.DataFrame) -> pd.DataFrame:
    x_df = x_df.copy()
    for column in x_df.columns:
        if not pd.api.types.is_numeric_dtype(x_df[column]):
            x_df[column] = pd.to_numeric(x_df[column], errors="raise")

        if pd.api.types.is_bool_dtype(x_df[column]):
            x_df[column] = x_df[column].astype("int64")
        elif pd.api.types.is_integer_dtype(x_df[column]):
            x_df[column] = x_df[column].astype("int64")
        else:
            x_df[column] = x_df[column].astype("float64")

    disallowed = {
        column: str(dtype)
        for column, dtype in x_df.dtypes.items()
        if str(dtype) not in {"int64", "float64"}
    }
    if disallowed:
        raise TypeError(f"Feature matrix has non-numeric dtypes: {disallowed}")

    leaked_metadata = sorted(set(METADATA_COLUMNS).intersection(x_df.columns))
    if leaked_metadata:
        raise AssertionError(f"Metadata columns leaked into feature matrix: {leaked_metadata}")

    return x_df


def print_step_1_summary(df: pd.DataFrame) -> None:
    unique_channels = [channel_label(value) for value in df["channel"].drop_duplicates()]
    rows_per_channel = df["channel"].map(channel_label).value_counts(dropna=False)

    print("\nStep 1 summary")
    print(f"Total rows: {len(df)}")
    print(f"Unique channel values ({len(unique_channels)}): {unique_channels}")
    print("Row count per channel:")
    for channel_name, row_count in rows_per_channel.items():
        print(f"  - {channel_name}: {int(row_count)}")


def print_step_2_report(channel_name: str, x_df: pd.DataFrame, metadata_df: pd.DataFrame) -> None:
    train_normalized = normalize_binary_series(
        metadata_df["train"],
        true_tokens=["1", "true", "t", "yes", "y", "train"],
        false_tokens=["0", "false", "f", "no", "n", "test"],
    )
    anomaly_normalized = normalize_binary_series(
        metadata_df["anomaly"],
        true_tokens=["1", "true", "t", "yes", "y", "anomaly", "anomalous"],
        false_tokens=["0", "false", "f", "no", "n", "nominal", "normal"],
    )

    train_count = int((train_normalized == True).sum())
    test_count = int((train_normalized == False).sum())
    train_unknown = int(train_normalized.isna().sum())

    anomaly_count = int((anomaly_normalized == True).sum())
    nominal_count = int((anomaly_normalized == False).sum())
    anomaly_unknown = int(anomaly_normalized.isna().sum())

    nan_counts = x_df.isna().sum()

    print(f"\nStep 2 report for channel '{channel_name}'")
    print(f"  X shape: {x_df.shape[0]} x {x_df.shape[1]}")
    print(
        "  train/test segments: "
        f"train={train_count}, test={test_count}, unknown={train_unknown}"
    )
    print(
        "  anomalous/nominal segments: "
        f"anomalous={anomaly_count}, nominal={nominal_count}, unknown={anomaly_unknown}"
    )
    print("  NaN values per feature column:")
    for column, nan_count in nan_counts.items():
        print(f"    - {column}: {int(nan_count)}")


def print_written_files_confirmation(base_dir: Path, files: list[Path]) -> None:
    seen: set[Path] = set()
    ordered_unique: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered_unique.append(path)

    print("\nConfirmation: files written")
    for path in ordered_unique:
        if not path.exists():
            continue
        size = human_readable_size(path.stat().st_size)
        try:
            relative_path = path.resolve().relative_to(base_dir.resolve())
        except ValueError:
            relative_path = path
        print(f"  - {relative_path} ({size})")


def main() -> None:
    project_root = Path(__file__).resolve().parent
    raw_dir = project_root / "data" / "raw"
    by_channel_dir = project_root / "data" / "interim" / "by_channel"

    raw_dir.mkdir(parents=True, exist_ok=True)
    by_channel_dir.mkdir(parents=True, exist_ok=True)

    written_files: list[Path] = []

    raw_path = download_opssat_dataset(raw_dir=raw_dir, written_files=written_files)
    dataset_path = resolve_dataset_path(
        raw_path=raw_path,
        raw_dir=raw_dir,
        written_files=written_files,
    )

    df = load_dataset(dataset_path)
    validate_required_columns(df)
    print_step_1_summary(df)

    channel_dfs: dict[str, pd.DataFrame] = {}
    channel_file_map: dict[str, str] = {}
    used_names: set[str] = set()

    for channel_value, channel_df in df.groupby("channel", dropna=False, sort=False):
        channel_name = channel_label(channel_value)
        safe_channel_name = make_unique_name(
            sanitize_channel_name(channel_name),
            used_names,
        )

        channel_dfs[channel_name] = channel_df.copy()
        channel_file_map[channel_name] = safe_channel_name

        full_channel_path = by_channel_dir / f"{safe_channel_name}.parquet"
        channel_df.to_parquet(full_channel_path, index=False, engine="pyarrow")
        written_files.append(full_channel_path)

    print(
        "\nSaved per-channel full DataFrames to "
        f"{by_channel_dir} ({len(channel_dfs)} files)."
    )

    for channel_name, channel_df in channel_dfs.items():
        metadata_df = channel_df[METADATA_COLUMNS].copy()
        x_df = channel_df[FEATURE_COLUMNS].copy()

        if not metadata_df.index.equals(x_df.index):
            raise AssertionError(
                f"Index mismatch for channel '{channel_name}'. "
                "Feature and metadata row order must be identical."
            )

        x_df = ensure_numeric_features(x_df)

        print_step_2_report(channel_name=channel_name, x_df=x_df, metadata_df=metadata_df)

        safe_channel_name = channel_file_map[channel_name]
        features_path = by_channel_dir / f"{safe_channel_name}_features.parquet"
        metadata_path = by_channel_dir / f"{safe_channel_name}_metadata.parquet"

        x_df.to_parquet(features_path, index=False, engine="pyarrow")
        metadata_df.to_parquet(metadata_path, index=False, engine="pyarrow")

        written_files.append(features_path)
        written_files.append(metadata_path)

    print_written_files_confirmation(base_dir=project_root, files=written_files)
    print("\nIngestion and preprocessing (steps 0-2) completed successfully.")


if __name__ == "__main__":
    main()