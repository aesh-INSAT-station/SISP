"""Shared logger factory and data-shape validation helpers."""

from __future__ import annotations

import logging

import pandas as pd


def get_logger(channel=None):
    name = f"sisp.{channel}" if channel else "sisp"
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = f"[{channel}] %(message)s" if channel else "%(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def assert_aligned(X: pd.DataFrame, meta: pd.DataFrame, context: str = "") -> None:
    """Raise ValueError if len(X) != len(meta)."""
    if len(X) != len(meta):
        raise ValueError(
            f"Alignment failed{f' ({context})' if context else ''}: "
            f"len(X)={len(X)} != len(meta)={len(meta)}"
        )


def assert_no_nulls(X: pd.DataFrame, context: str = "") -> None:
    """Raise ValueError if X contains any NaN."""
    null_count = int(X.isna().sum().sum())
    if null_count > 0:
        raise ValueError(
            f"Null check failed{f' ({context})' if context else ''}: "
            f"{null_count} NaN values remain"
        )


def assert_numeric_only(X: pd.DataFrame, context: str = "") -> None:
    """Raise ValueError if X contains non-numeric dtype columns."""
    bad = [col for col in X.columns if not pd.api.types.is_numeric_dtype(X[col])]
    if bad:
        raise ValueError(
            f"Non-numeric columns found{f' ({context})' if context else ''}: {bad}"
        )
