"""Path helpers for all SISP input, interim, and output artifacts."""

from pathlib import Path

DATA_ROOT = Path("data")
RAW_DIR = DATA_ROOT / "raw"
BY_CHANNEL_DIR = DATA_ROOT / "interim" / "by_channel"
SCALERS_DIR = DATA_ROOT / "interim" / "scalers"
SVD_DIR = DATA_ROOT / "interim" / "svd"
OUTPUT_DIR = DATA_ROOT / "output"

_FEATURE_SUFFIX = "_features.parquet"
_FEATURE_SCALED_SUFFIX = "_features_scaled.parquet"


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    BY_CHANNEL_DIR.mkdir(parents=True, exist_ok=True)
    SCALERS_DIR.mkdir(parents=True, exist_ok=True)
    SVD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def raw_file_path(filename: str) -> Path:
    return RAW_DIR / filename


def extracted_dir(stem: str) -> Path:
    return RAW_DIR / "extracted" / stem


def channel_full_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}.parquet"


def features_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_features.parquet"


def metadata_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_metadata.parquet"


def features_clean_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_features_clean.parquet"


def metadata_clean_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_metadata_clean.parquet"


def features_winsor_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_features_winsorized.parquet"


def features_scaled_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_features_scaled.parquet"


def scaler_path(ch: str) -> Path:
    return SCALERS_DIR / f"{ch}_scaler.pkl"


def svd_path(ch: str) -> Path:
    return SVD_DIR / f"{ch}_svd.pkl"


def feature_names_path(ch: str) -> Path:
    return SVD_DIR / f"{ch}_feature_names.json"


def binary_features_path(ch: str) -> Path:
    return SVD_DIR / f"{ch}_binary_features.json"


def results_path(ch: str) -> Path:
    return OUTPUT_DIR / f"{ch}_results.parquet"


def sample_default_csv_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_sample_default.csv"


def sample_features_csv_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_sample_features.csv"


def sample_metadata_csv_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_sample_metadata.csv"


def sample_scaled_default_csv_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_sample_scaled_default.csv"


def sample_scaled_features_csv_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_sample_scaled_features.csv"


def sample_scaled_metadata_csv_path(ch: str) -> Path:
    return BY_CHANNEL_DIR / f"{ch}_sample_scaled_metadata.csv"


def feature_files() -> list[Path]:
    return sorted(BY_CHANNEL_DIR.glob(f"*{_FEATURE_SUFFIX}"))


def scaled_feature_files() -> list[Path]:
    return sorted(BY_CHANNEL_DIR.glob(f"*{_FEATURE_SCALED_SUFFIX}"))


def channel_from_feature_file(path: Path) -> str:
    if not path.name.endswith(_FEATURE_SUFFIX):
        raise ValueError(f"Invalid feature file name: {path.name}")
    return path.name[: -len(_FEATURE_SUFFIX)]


def channel_from_scaled_feature_file(path: Path) -> str:
    if not path.name.endswith(_FEATURE_SCALED_SUFFIX):
        raise ValueError(f"Invalid scaled feature file name: {path.name}")
    return path.name[: -len(_FEATURE_SCALED_SUFFIX)]
