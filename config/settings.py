"""Central configuration constants for the SISP pipelines."""

EXCLUDED_CHANNELS = {"CADC0886", "CADC0890"}

METADATA_COLS = ["segment", "anomaly", "train", "channel"]
FEATURE_COLS = [
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

NAN_DROP_THRESHOLD = 0.30
WINSOR_LOW = 0.01
WINSOR_HIGH = 0.99
ZERO_VAR_EPSILON = 1e-8
BINARY_EQUALITY_EPSILON = 1e-8
TEST_MEAN_WARNING_ABS = 3.0

SVD_VARIANCE_TARGET = 0.90
SVD_K_MIN = 2
SVD_K_MAX = 15
ANOMALY_THRESHOLD_PCTILE = 95

RANDOM_STATE = 42
SAMPLE_SIZE = 5

PARQUET_ENGINE = "pyarrow"
JSON_INDENT = 2

ZENODO_URL = "https://zenodo.org/api/records/12588359"
ZENODO_TOKEN_ENV_VAR = "ZENODO_TOKEN"
ZENODO_RECORD_TIMEOUT_SEC = 60
ZENODO_DOWNLOAD_TIMEOUT_SEC = 120
ZENODO_DOWNLOAD_CHUNK_BYTES = 1024 * 1024

TRAIN_TRUE_TOKENS = ("1", "true", "t", "yes", "y", "train")
TRAIN_FALSE_TOKENS = ("0", "false", "f", "no", "n", "test")
ANOMALY_TRUE_TOKENS = ("1", "true", "t", "yes", "y", "anomaly", "anomalous")
ANOMALY_FALSE_TOKENS = ("0", "false", "f", "no", "n", "nominal", "normal")
