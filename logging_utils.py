#!/usr/bin/env python3
"""Logging helpers shared across PRA scripts."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUPS = 10


def _log_dir() -> Path:
    log_dir = Path(os.getenv("PRA_LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _log_path(name: str, run_id: Optional[str]) -> Path:
    prefix = run_id or os.getenv("PRA_RUN_ID")
    filename = f"{name}_{prefix}.log" if prefix else f"{name}.log"
    return _log_dir() / filename


def configure_logger(
    name: str,
    level: Optional[str] = None,
    run_id: Optional[str] = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    log_level = level or os.getenv("PRA_LOG_LEVEL", "INFO")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    log_file = _log_path(name, run_id)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=int(os.getenv("PRA_LOG_MAX_BYTES", DEFAULT_MAX_BYTES)),
        backupCount=int(os.getenv("PRA_LOG_BACKUPS", DEFAULT_BACKUPS)),
        encoding="utf-8",
    )
    formatter = logging.Formatter(LOG_FORMAT)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.debug("Logger configured: %s", log_file)
    return logger


def attach_stdout_logger(logger: logging.Logger) -> None:
    """Redirect built-in print statements to the structured logger."""
    import builtins

    def _logged_print(*args, **kwargs):  # noqa: ANN001
        sep = kwargs.pop("sep", " ")
        end = kwargs.pop("end", "\n")
        message = sep.join(str(arg) for arg in args) + end
        text = message.rstrip()

        normalized = text.upper()
        if normalized.startswith("[ERROR") or normalized.startswith("ERROR"):
            level = logging.ERROR
        elif normalized.startswith("[WARNING"):
            level = logging.WARNING
        elif normalized.startswith("[SKIP]"):
            level = logging.INFO
        elif normalized.startswith("[OK]"):
            level = logging.INFO
        elif normalized.startswith("[INFO]"):
            level = logging.INFO
        else:
            level = logging.DEBUG
        logger.log(level, text)

    builtins.print = _logged_print
    logger.debug("stdout redirected to %s", logger.name)
