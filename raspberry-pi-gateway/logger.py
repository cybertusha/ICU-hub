"""
Structured logging utility for the Raspberry Pi IoT Gateway.
Logs both to stdout and to a persistent log file for diagnostics.
"""

import logging
import sys
from pathlib import Path

LOG_FILE = Path(__file__).parent / "gateway.log"


def get_logger(name: str = "icu-pi-gateway") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        pass

    return logger
