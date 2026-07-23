"""Rotating application logs for RZD / Telegram / checker."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_LOGGERS: dict[str, logging.Logger] = {}


def _make_logger(name: str, filename: str, max_bytes: int, backups: int) -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]
    logger = logging.getLogger(f"ct.{name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        path = LOG_DIR / filename
        handler = RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backups,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
    _LOGGERS[name] = logger
    return logger


def rzd_logger() -> logging.Logger:
    return _make_logger("rzd", "rzd.log", 5 * 1024 * 1024, 5)


def telegram_logger() -> logging.Logger:
    return _make_logger("telegram", "telegram.log", 2 * 1024 * 1024, 5)


def checker_logger() -> logging.Logger:
    return _make_logger("checker", "checker.log", 2 * 1024 * 1024, 5)


def log_path(source: str) -> Path:
    mapping = {
        "rzd": LOG_DIR / "rzd.log",
        "telegram": LOG_DIR / "telegram.log",
        "checker": LOG_DIR / "checker.log",
    }
    return mapping[source]


def read_log_tail(source: str, lines: int = 200) -> str:
    path = log_path(source)
    if not path.exists():
        return f"(файл {path.name} пока пуст)"
    lines = max(1, min(int(lines), 2000))
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            block = 8192
            data = b""
            while size > 0 and data.count(b"\n") <= lines:
                step = min(block, size)
                size -= step
                fh.seek(size)
                data = fh.read(step) + data
            text = data.decode("utf-8", errors="replace")
            parts = text.splitlines()
            return "\n".join(parts[-lines:])
    except Exception as exc:
        return f"(ошибка чтения: {exc})"
