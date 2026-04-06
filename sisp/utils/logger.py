"""Logger factory for consistent SISP console output."""

import logging


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
