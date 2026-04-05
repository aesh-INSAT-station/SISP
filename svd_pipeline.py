from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics import (
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)


FEATURE_SCALED_SUFFIX = "_features_scaled.parquet"
METADATA_COLUMNS = ["segment", "anomaly", "train", "channel"]
EXCLUDED_CHANNELS = {"CADC0886", "CADC0890"}

TARGET_EXPLAINED_VARIANCE = 0.90
MIN_COMPONENTS = 2
MAX_COMPONENTS = 15
THRESHOLD_PERCENTILE = 0.95
RANDOM_STATE = 42


def human_readable_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def channel_from_feature_file(feature_path: Path) -> str:
    if not feature_path.name.endswith(FEATURE_SCALED_SUFFIX):
        raise ValueError(f"Invalid scaled feature file name: {feature_path.name}")
    return feature_path.name[: -len(FEATURE_SCALED_SUFFIX)]


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


def get_train_mask(metadata_df: pd.DataFrame) -> pd.Series:
    train_flag = normalize_train_flag(metadata_df["train"])
    return (train_flag == True).fillna(False).astype(bool)


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


def validate_metadata_columns(metadata_df: pd.DataFrame, channel_name: str) -> None:
    missing = set(METADATA_COLUMNS).difference(metadata_df.columns)
    if missing:
        missing_fmt = ", ".join(sorted(missing))
        raise KeyError(
            f"Metadata for channel '{channel_name}' is missing required columns: {missing_fmt}"
        )


def select_rank_k(x_fit: pd.DataFrame) -> tuple[int, float, pd.Series]:
    n_fit_rows = x_fit.shape[0]
    n_features = x_fit.shape[1]
    max_full_components = min(n_features, n_fit_rows - 1)

    if max_full_components < MIN_COMPONENTS:
        raise RuntimeError(
            "Cannot satisfy rank constraints with current fitting set: "
            f"n_fit_rows={n_fit_rows}, n_features={n_features}, "
            f"max_components={max_full_components}, required_min_k={MIN_COMPONENTS}."
        )

    svd_probe = TruncatedSVD(n_components=max_full_components, random_state=RANDOM_STATE)
    svd_probe.fit(x_fit)

    explained_ratio = pd.Series(svd_probe.explained_variance_ratio_, dtype="float64").fillna(0.0)
    cumulative = explained_ratio.cumsum()

    meets_target = cumulative >= TARGET_EXPLAINED_VARIANCE
    if bool(meets_target.any()):
        k_target = int(meets_target.idxmax()) + 1
    else:
        k_target = int(len(cumulative))

    upper_bound = min(MAX_COMPONENTS, max_full_components)
    k_selected = min(max(k_target, MIN_COMPONENTS), upper_bound)
    cumulative_at_k = float(cumulative.iloc[k_selected - 1])

    return k_selected, cumulative_at_k, explained_ratio


def fit_and_save_svd(
    channel_name: str,
    features_scaled: pd.DataFrame,
    metadata_clean: pd.DataFrame,
    svd_dir: Path,
    written_files: list[Path],
) -> dict[str, object]:
    fitting_mask = get_fitting_mask(metadata_clean)
    x_fit = features_scaled.loc[fitting_mask].reset_index(drop=True)

    if x_fit.empty:
        raise RuntimeError(
            f"Channel '{channel_name}' has zero rows where train=True AND anomaly=0; "
            "cannot fit TruncatedSVD."
        )

    print(f"\nStep 5 - channel '{channel_name}'")
    print(f"X_fit shape: {x_fit.shape}")

    k_selected, cumulative_at_k, probe_ratio = select_rank_k(x_fit)

    final_svd = TruncatedSVD(n_components=k_selected, random_state=RANDOM_STATE)
    final_svd.fit(x_fit)

    svd_path = svd_dir / f"{channel_name}_svd.pkl"
    joblib.dump(final_svd, svd_path)
    written_files.append(svd_path)

    component_ratios = pd.Series(final_svd.explained_variance_ratio_, dtype="float64")
    component_ratios_fmt = ", ".join(f"{value:.6f}" for value in component_ratios.tolist())

    print(f"Chosen k: {k_selected}")
    print(f"Cumulative explained variance at k: {cumulative_at_k:.6f}")
    print(f"Component explained variance ratios: [{component_ratios_fmt}]")

    return {
        "channel": channel_name,
        "x_fit_shape": x_fit.shape,
        "k": k_selected,
        "cum_var_at_k": cumulative_at_k,
        "probe_ratio": probe_ratio,
    }


def compute_split_metrics(
    y_true: pd.Series,
    y_pred: pd.Series,
    scores: pd.Series,
) -> dict[str, float | int]:
    if len(y_true) == 0:
        return {
            "tp": 0,
            "fp": 0,
            "tn": 0,
            "fn": 0,
            "precision": float("nan"),
            "recall": float("nan"),
            "f1": float("nan"),
            "roc_auc": float("nan"),
            "n_rows": 0,
        }

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )

    if y_true.nunique() < 2:
        roc_auc = float("nan")
    else:
        roc_auc = float(roc_auc_score(y_true, scores))

    return {
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "roc_auc": roc_auc,
        "n_rows": int(len(y_true)),
    }


def print_split_report(split_name: str, metrics: dict[str, float | int]) -> None:
    print(f"{split_name} rows: {metrics['n_rows']}")
    print(
        "Confusion matrix (TP, FP, TN, FN): "
        f"({metrics['tp']}, {metrics['fp']}, {metrics['tn']}, {metrics['fn']})"
    )
    print(
        "Precision/Recall/F1: "
        f"{metrics['precision']:.6f} / {metrics['recall']:.6f} / {metrics['f1']:.6f}"
    )
    print(f"ROC-AUC: {metrics['roc_auc']:.6f}")


def score_channel_and_write_results(
    channel_name: str,
    features_scaled: pd.DataFrame,
    metadata_clean: pd.DataFrame,
    svd_model_path: Path,
    output_dir: Path,
    written_files: list[Path],
) -> None:
    svd_model = joblib.load(svd_model_path)

    x_full = features_scaled.reset_index(drop=True)
    metadata_clean = metadata_clean.reset_index(drop=True)
    assert_row_alignment(x_full, metadata_clean, channel_name, "step6-score-load")

    x_projected = svd_model.transform(x_full)
    x_reconstructed = svd_model.inverse_transform(x_projected)

    residual = x_full.to_numpy(copy=False) - x_reconstructed
    reconstruction_error = pd.Series((residual * residual).sum(axis=1), dtype="float64")

    fitting_mask = get_fitting_mask(metadata_clean)
    fit_errors = reconstruction_error.loc[fitting_mask].reset_index(drop=True)
    if fit_errors.empty:
        raise RuntimeError(
            f"Channel '{channel_name}' has zero fitting rows while computing threshold."
        )

    threshold = float(fit_errors.quantile(THRESHOLD_PERCENTILE, interpolation="linear"))
    fit_error_mean = float(fit_errors.mean())
    fit_error_std = float(fit_errors.std(ddof=0))

    predicted_anomaly = (reconstruction_error > threshold).astype("int64")

    anomaly_flag = normalize_anomaly_flag(metadata_clean["anomaly"])
    if bool(anomaly_flag.isna().any()):
        raise RuntimeError(
            f"Channel '{channel_name}' contains unrecognized anomaly labels in metadata."
        )
    y_true = anomaly_flag.astype("int64")

    train_mask = get_train_mask(metadata_clean)
    test_mask = get_test_mask(metadata_clean)

    results_df = pd.DataFrame(
        {
            "segment": metadata_clean["segment"],
            "train": metadata_clean["train"],
            "anomaly": metadata_clean["anomaly"],
            "reconstruction_error": reconstruction_error,
            "threshold": threshold,
            "predicted_anomaly": predicted_anomaly,
        }
    )

    if len(results_df) != len(x_full):
        raise AssertionError(
            f"Results row count mismatch for channel '{channel_name}': "
            f"results={len(results_df)}, features={len(x_full)}"
        )

    output_path = output_dir / f"{channel_name}_results.parquet"
    results_df.to_parquet(output_path, index=False, engine="pyarrow")
    written_files.append(output_path)

    test_metrics = compute_split_metrics(
        y_true.loc[test_mask].reset_index(drop=True),
        predicted_anomaly.loc[test_mask].reset_index(drop=True),
        reconstruction_error.loc[test_mask].reset_index(drop=True),
    )
    train_metrics = compute_split_metrics(
        y_true.loc[train_mask].reset_index(drop=True),
        predicted_anomaly.loc[train_mask].reset_index(drop=True),
        reconstruction_error.loc[train_mask].reset_index(drop=True),
    )

    nominal_mean = float(reconstruction_error.loc[y_true == 0].mean())
    anomaly_mean = float(reconstruction_error.loc[y_true == 1].mean())

    print(f"\nStep 6 - channel '{channel_name}'")
    print(f"Threshold T (95th percentile of fit-row errors): {threshold:.6f}")
    print(f"Fit-row error mean/std: {fit_error_mean:.6f} / {fit_error_std:.6f}")
    print_split_report("TEST (train=False)", test_metrics)
    print_split_report("TRAIN (train=True)", train_metrics)
    print(f"Mean reconstruction error for anomaly=0: {nominal_mean:.6f}")
    print(f"Mean reconstruction error for anomaly=1: {anomaly_mean:.6f}")


def print_written_files_summary(project_root: Path, files: list[Path]) -> None:
    print("\nFinal written files summary")
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        relative_path = resolved.relative_to(project_root.resolve())
        print(f"  - {relative_path} ({human_readable_size(path.stat().st_size)})")


def load_channel_inputs(by_channel_dir: Path, channel_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    feature_path = by_channel_dir / f"{channel_name}_features_scaled.parquet"
    metadata_path = by_channel_dir / f"{channel_name}_metadata_clean.parquet"

    if not feature_path.exists():
        raise FileNotFoundError(f"Missing scaled features for channel '{channel_name}': {feature_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing clean metadata for channel '{channel_name}': {metadata_path}")

    features_scaled = pd.read_parquet(feature_path, engine="pyarrow")
    metadata_clean = pd.read_parquet(metadata_path, engine="pyarrow")

    validate_metadata_columns(metadata_clean, channel_name)
    assert_row_alignment(features_scaled, metadata_clean, channel_name, "load")
    return features_scaled, metadata_clean


def main() -> None:
    project_root = Path(__file__).resolve().parent
    by_channel_dir = project_root / "data" / "interim" / "by_channel"
    svd_dir = project_root / "data" / "interim" / "svd"
    output_dir = project_root / "data" / "output"

    svd_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    feature_files = sorted(by_channel_dir.glob(f"*{FEATURE_SCALED_SUFFIX}"))
    if not feature_files:
        raise FileNotFoundError(
            f"No scaled feature files found in {by_channel_dir} matching '*{FEATURE_SCALED_SUFFIX}'."
        )

    discovered_channels = [channel_from_feature_file(path) for path in feature_files]
    channel_names = [
        channel_name
        for channel_name in discovered_channels
        if channel_name not in EXCLUDED_CHANNELS
    ]
    excluded_found = [
        channel_name
        for channel_name in discovered_channels
        if channel_name in EXCLUDED_CHANNELS
    ]

    print(f"Discovered {len(discovered_channels)} channels: {discovered_channels}")
    for channel_name in excluded_found:
        print(f"Skipping excluded channel: {channel_name}")

    if not channel_names:
        raise RuntimeError("No channels left to process after applying exclusion list.")

    print(f"Channels selected for SVD pipeline ({len(channel_names)}): {channel_names}")

    written_files: list[Path] = []

    # Step 5: fit and persist per-channel SVD models.
    for channel_name in channel_names:
        features_scaled, metadata_clean = load_channel_inputs(by_channel_dir, channel_name)
        fit_and_save_svd(
            channel_name=channel_name,
            features_scaled=features_scaled,
            metadata_clean=metadata_clean,
            svd_dir=svd_dir,
            written_files=written_files,
        )

    # Step 6: score full channel data with reconstruction errors and write outputs.
    for channel_name in channel_names:
        features_scaled, metadata_clean = load_channel_inputs(by_channel_dir, channel_name)
        svd_model_path = svd_dir / f"{channel_name}_svd.pkl"
        if not svd_model_path.exists():
            raise FileNotFoundError(
                f"Expected fitted SVD model for channel '{channel_name}' at {svd_model_path}"
            )
        score_channel_and_write_results(
            channel_name=channel_name,
            features_scaled=features_scaled,
            metadata_clean=metadata_clean,
            svd_model_path=svd_model_path,
            output_dir=output_dir,
            written_files=written_files,
        )

    print_written_files_summary(project_root, written_files)
    print("\nSVD pipeline (steps 5-6) completed successfully.")


if __name__ == "__main__":
    main()
