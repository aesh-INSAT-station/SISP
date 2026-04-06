"""Backward-compatible wrapper that runs the refactored ingest pipeline."""

from pipelines.run_ingest import main


if __name__ == "__main__":
    main()
