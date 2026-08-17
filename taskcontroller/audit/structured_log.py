"""Bounded structured-log projection for TaskController audit events.

The durable source of truth remains the Run Ledger. This module only projects a
small allow-listed event view to standard Python logging; it never serializes
before/after payloads, annotations, or conversation content.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from taskcontroller.audit.event import AuditEvent


_EXTRA_FIELDS = (
    "event_id",
    "event_timestamp",
    "run_id",
    "source",
    "decision_kind",
    "node_id",
    "authority_ref",
    "raw_payload_ref",
    "sequence",
)


class StructuredAuditFormatter(logging.Formatter):
    """Emit one bounded JSON object per standard logging record."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": getattr(record, "event_timestamp", None) or self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            if key == "event_timestamp":
                continue
            if hasattr(record, key):
                value = getattr(record, key)
                if value not in (None, ""):
                    entry[key] = value
        return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def audit_log_extra(event: AuditEvent) -> dict[str, Any]:
    """Return only bounded metadata safe for log projection."""
    return {
        "event_id": event.event_id,
        "event_timestamp": event.timestamp,
        "run_id": event.run_id,
        "source": event.source,
        "decision_kind": event.decision_kind,
        "node_id": event.node_id,
        "authority_ref": event.authority_ref,
        "raw_payload_ref": event.raw_payload_ref,
        "sequence": event.sequence,
    }


def log_audit_event(logger: logging.Logger, event: AuditEvent) -> None:
    """Project one persisted AuditEvent into an optional standard logger."""
    logger.info(event.payload_summary or event.decision_kind, extra=audit_log_extra(event))
