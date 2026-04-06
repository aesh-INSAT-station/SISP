# SISP

SISP is a modular satellite telemetry anomaly detection project for the OPSSAT-AD dataset, with a three-stage workflow that ingests raw data, performs channel-wise preprocessing, and applies an SVD reconstruction-error model to detect anomalous segments while preserving deterministic, reproducible outputs across runs.

## Installation

```bash
pip install -r requirements.txt
```

## Run Pipelines (in order)

```bash
python pipelines/run_ingest.py
python pipelines/run_preprocess.py
python pipelines/run_svd.py
```

## Pipeline Overview

- `pipelines/run_ingest.py`: downloads and validates the dataset, splits rows by channel, separates metadata/features, and writes base channel artifacts.
- `pipelines/run_preprocess.py`: audits and imputes missing values, applies zero-variance handling, winsorizes continuous features, scales continuous features, and saves preprocessing artifacts.
- `pipelines/run_svd.py`: fits per-channel TruncatedSVD models, computes reconstruction-error thresholds, generates anomaly predictions, and writes final channel result files.

## Architecture Notes

- Quick AI handoff: `AI_CONTEXT.md`
- Detailed architecture reference: `sisp/SISP_ARCHITECTURE.md`
