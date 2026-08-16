from __future__ import annotations

import json
import logging
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Emit one JSON object per log record with structured context fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("run_id", "checkpoint", "authority_ref", "source", "decision_kind"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry, sort_keys=True, ensure_ascii=False)


def get_audit_logger(name: str = "taskcontroller.audit") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
