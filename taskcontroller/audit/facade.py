"""AuditFacade — no-op compatible interface for audit foundation.

MVP injection keeps persistence authority in SQLiteRunLedger.
This facade provides the contract surface later MVP code will call.
"""
from __future__ import annotations

import logging
from pathlib import Path

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.manifest import RunManifest
from taskcontroller.audit.sqlite_writer import SQLiteRunLedger
from taskcontroller.audit.structured_log import log_audit_event
from taskcontroller.audit.summary import RunSummary


class AuditFacade:
    def __init__(self, db_path: Path | str, logger: logging.Logger | None = None) -> None:
        self._ledger = SQLiteRunLedger(db_path)
        self._logger = logger

    def record(self, run_id: str, event: AuditEvent) -> int:
        revision = self._ledger.append(run_id, event)
        if self._logger is not None:
            try:
                log_audit_event(self._logger, event)
            except Exception:
                # Structured logging is a best-effort projection only. A logger
                # failure must never roll back or invalidate durable audit state.
                pass
        return revision

    def events(self, run_id: str) -> list[AuditEvent]:
        return self._ledger.events(run_id)

    def save_manifest(self, manifest: RunManifest) -> None:
        self._ledger.upsert_manifest(manifest)

    def load_manifest(self, run_id: str, manifest_kind: str) -> RunManifest | None:
        return self._ledger.manifest(run_id, manifest_kind)

    def list_manifests(self, run_id: str) -> list[RunManifest]:
        return self._ledger.manifests(run_id)

    def save_summary(self, summary: RunSummary) -> None:
        self._ledger.upsert_summary(summary)

    def load_summary(self, run_id: str) -> RunSummary | None:
        return self._ledger.summary(run_id)

    def close(self) -> None:
        self._ledger.close()


class NoOpAuditFacade:
    """No-op facade for dry-run / test paths."""

    def record(self, run_id: str, event: AuditEvent) -> int:
        return 0

    def events(self, run_id: str) -> list[AuditEvent]:
        return []

    def save_manifest(self, manifest: RunManifest) -> None:
        return None

    def load_manifest(self, run_id: str, manifest_kind: str) -> RunManifest | None:
        return None

    def list_manifests(self, run_id: str) -> list[RunManifest]:
        return []

    def save_summary(self, summary: RunSummary) -> None:
        return None

    def load_summary(self, run_id: str) -> RunSummary | None:
        return None

    def close(self) -> None:
        return None
