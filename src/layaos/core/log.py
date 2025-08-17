
from __future__ import annotations

import logging
import os
import sys
import json
from typing import Optional

_configured = False
_seen_debug = False   # <--- เพิ่มบรรทัดนี้

def _maybe_load_dotenv() -> None:
    try:
        # Optional: load .env if python-dotenv is installed
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except Exception:
        pass


class JsonHandler(logging.StreamHandler):
    """Lightweight JSON logger for stdout."""
    def __init__(self):
        super().__init__(stream=sys.stdout)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            obj = {
                "ts": record.created,
                "lvl": record.levelname,
                "name": record.name,
                "msg": record.getMessage(),
            }
            # Include extras if present (safe subset)
            for k in ("filename", "lineno", "funcName"):
                obj[k] = getattr(record, k, None)
            self.stream.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.flush()
        except Exception:  # pragma: no cover
            self.handleError(record)


def setup(level: Optional[str] = None, json_mode: Optional[bool] = None, *, force: bool = False) -> None:
    """Configure root logger.
    - Reads LOG_LEVEL, LOG_JSON from env if args are None
    - If already configured, do nothing unless force=True
    """
    global _configured
    if _configured and not force:
        return

    _maybe_load_dotenv()

    lvl = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    try:
        py_level = getattr(logging, lvl)
    except AttributeError:
        py_level = logging.INFO

    json_flag = json_mode if json_mode is not None else (os.getenv("LOG_JSON", "0") == "1")

    root = logging.getLogger()
    # Reset handlers to avoid duplicate logs (pytest re-runs etc.)
    root.handlers.clear()
    root.setLevel(py_level)

    if json_flag:
        handler = JsonHandler()
        root.addHandler(handler)
    else:
        fmt = "[%(asctime)s] %(levelname)s %(name)s | %(message)s"
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter(fmt=fmt))
        root.addHandler(handler)

    _configured = True


def get(name: str) -> logging.Logger:
    """Helper to get a namespaced logger."""
    return logging.getLogger(name)


def set_level(level: str) -> None:
    """Dynamically adjust root log level (e.g., during tests)."""
    lvl = level.upper()
    try:
        logging.getLogger().setLevel(getattr(logging, lvl))
    except AttributeError:
        logging.getLogger().setLevel(logging.INFO)
