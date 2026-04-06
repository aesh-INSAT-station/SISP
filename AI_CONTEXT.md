# SISP AI Context

This file is a quick handoff for future AI conversations about this repository.

## What The Top-Level Scripts Do

- ingest.py is a compatibility wrapper that only calls pipelines/run_ingest.py.
- preprocess.py is a compatibility wrapper that only calls pipelines/run_preprocess.py.
- svd_pipeline.py is a compatibility wrapper that only calls pipelines/run_svd.py.

The real logic is inside the pipelines and sisp package modules.

## Execution Order

Run in this order:

1. python pipelines/run_ingest.py
2. python pipelines/run_preprocess.py
3. python pipelines/run_svd.py

Each stage writes artifacts consumed by the next stage.

## Architecture Layers

Dependency flow is one-way:

pipelines -> sisp modules -> sisp/utils

- pipelines/: orchestration only (loops, function calls, summaries).
- sisp/io/: dataset download/load and artifact persistence.
- sisp/preprocessing/: splitting, metadata masks, imputation, variance handling, winsorization, scaling.
- sisp/anomaly/: SVD rank selection, reconstruction scoring, thresholding, evaluation.
- sisp/utils/: paths, logger, and validation helpers.
- config/settings.py: all constants and tunable parameters.

## Core Contracts

- Paths are centralized in sisp/utils/paths.py.
- Constants are centralized in config/settings.py.
- No bare print() in pipelines/package modules; use sisp/utils/logger.py.
- Fitting operations use train=True and anomaly=False rows.
- Feature and metadata row alignment must be preserved at every step.

## Key Artifact Locations

- Raw source: data/raw/
- Channel artifacts: data/interim/by_channel/
- Scalers: data/interim/scalers/
- SVD models + metadata: data/interim/svd/
- Final results: data/output/

## Practical Rule For Future AI Edits

When changing behavior, edit module files under sisp/. Keep pipelines thin.
When adding a new pipeline, create new modules first, then a thin entrypoint in pipelines/.


