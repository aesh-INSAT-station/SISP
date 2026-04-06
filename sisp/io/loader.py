"""Dataset download and raw table loading helpers for SISP."""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

import pandas as pd
import requests

from config.settings import (
    FEATURE_COLS,
    METADATA_COLS,
    PARQUET_ENGINE,
    ZENODO_DOWNLOAD_CHUNK_BYTES,
    ZENODO_DOWNLOAD_TIMEOUT_SEC,
    ZENODO_RECORD_TIMEOUT_SEC,
    ZENODO_TOKEN_ENV_VAR,
)
from sisp.preprocessing.channel_splitter import sanitize_channel_name
from sisp.utils.logger import get_logger
from sisp.utils.paths import extracted_dir, raw_file_path

logger = get_logger()


def _pick_best_zenodo_file(files: list[dict]) -> dict:
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


def _extract_dataset_table(raw_zip_path: Path, written_files: list[Path] | None = None) -> Path:
    extract_root = extracted_dir(sanitize_channel_name(raw_zip_path.stem))
    extract_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(raw_zip_path, "r") as zip_handle:
        candidates = [
            member
            for member in zip_handle.namelist()
            if not member.endswith("/") and Path(member).suffix.lower() in {".csv", ".parquet"}
        ]
        if not candidates:
            raise RuntimeError("ZIP archive does not contain a CSV or Parquet dataset file.")

        def candidate_score(member: str) -> tuple[int, str]:
            suffix = Path(member).suffix.lower()
            priority = 0 if suffix == ".parquet" else 1
            return priority, member.lower()

        selected_member = sorted(candidates, key=candidate_score)[0]
        extracted_path = extract_root / Path(selected_member).name
        with zip_handle.open(selected_member) as source_handle, extracted_path.open("wb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle)

    if written_files is not None:
        written_files.append(extracted_path)

    logger.info(f"Extracted dataset file from ZIP: {extracted_path}")
    return extracted_path


def _resolve_dataset_path(raw_path: Path, written_files: list[Path] | None = None) -> Path:
    suffix = raw_path.suffix.lower()
    if suffix in {".csv", ".parquet"}:
        return raw_path
    if suffix == ".zip":
        return _extract_dataset_table(raw_path, written_files=written_files)
    raise RuntimeError(
        f"Unsupported raw dataset format '{raw_path.suffix}'. Expected CSV, Parquet, or ZIP."
    )


def download_dataset(zenodo_url: str, dest_dir: Path, written_files: list[Path] | None = None) -> Path:
    """Download and resolve the raw dataset to a CSV or Parquet path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    token = os.getenv(ZENODO_TOKEN_ENV_VAR)
    params = {"access_token": token} if token else None

    record_response = requests.get(zenodo_url, params=params, timeout=ZENODO_RECORD_TIMEOUT_SEC)
    record_response.raise_for_status()
    record = record_response.json()

    files = record.get("files", [])
    if not files:
        raise RuntimeError("Zenodo record contains no downloadable files.")

    selected_file = _pick_best_zenodo_file(files)
    filename = selected_file.get("key") or selected_file.get("filename")
    if not filename:
        raise RuntimeError("Could not determine dataset filename from Zenodo metadata.")

    links = selected_file.get("links", {})
    download_url = links.get("download") or links.get("self") or links.get("content")
    if not download_url:
        raise RuntimeError("Could not find a download URL in Zenodo metadata.")

    raw_path = raw_file_path(filename)
    logger.info(f"Downloading Zenodo file: {filename}")
    with requests.get(download_url, params=params, stream=True, timeout=ZENODO_DOWNLOAD_TIMEOUT_SEC) as response:
        response.raise_for_status()
        with raw_path.open("wb") as file_handle:
            for chunk in response.iter_content(chunk_size=ZENODO_DOWNLOAD_CHUNK_BYTES):
                if chunk:
                    file_handle.write(chunk)

    if written_files is not None:
        written_files.append(raw_path)

    logger.info(f"Saved raw file to: {raw_path}")
    return _resolve_dataset_path(raw_path, written_files=written_files)


def _validate_required_columns(df: pd.DataFrame) -> None:
    required_columns = METADATA_COLS + FEATURE_COLS
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        missing_formatted = ", ".join(missing_columns)
        raise KeyError(f"Dataset is missing required columns: {missing_formatted}")


def load_raw(path: Path) -> pd.DataFrame:
    """Load a CSV or Parquet dataset and validate required columns."""
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(path, engine=PARQUET_ENGINE)
    elif suffix == ".csv":
        df = pd.read_csv(path, low_memory=False)
    else:
        raise RuntimeError(f"Unsupported dataset file format: {path}")

    _validate_required_columns(df)
    return df
