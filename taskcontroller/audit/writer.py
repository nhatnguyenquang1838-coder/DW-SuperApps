from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.structured_log import get_audit_logger


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class FileAuditWriter:
    """Append-only JSONL writer with structured log emission and log rotation."""

    def __init__(
        self,
        path: Path,
        max_size: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_size = max_size
        self._backup_count = backup_count
        self._logger = get_audit_logger("taskcontroller.audit.writer")

    def _rotate_if_needed(self) -> None:
        """Rotate log file when it exceeds max_size."""
        if not self._path.exists():
            return
        if self._path.stat().st_size < self._max_size:
            return
        # Rotate: shift existing backups up by one
        for i in range(self._backup_count - 1, 0, -1):
            old = self._path.with_suffix(self._path.suffix + f".{i}")
            new = self._path.with_suffix(self._path.suffix + f".{i + 1}")
            if old.exists():
                old.rename(new)
        # Move current file to .1
        backup = self._path.with_suffix(self._path.suffix + ".1")
        self._path.rename(backup)

    def emit(self, event: AuditEvent) -> None:
        self._rotate_if_needed()
        line = event.to_json() + "\n"
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)
        # Also emit structured log
        self._logger.info(
            "audit event %s",
            event.event_id,
            extra={
                "run_id": event.run_id,
                "source": event.source,
                "decision_kind": event.decision_kind,
                "authority_ref": event.authority_ref,
            },
        )

    def replay(self) -> list[AuditEvent]:
        if not self._path.exists():
            return []
        events: list[AuditEvent] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(AuditEvent.from_json(line))
        return events


class CheckpointAuditWriter:
    """CAS-versioned checkpoint writer (inspired by checkpoint_store.py).

    Each emit() increments the store revision and raises ValueError on
    expected_revision mismatch — identical CAS semantics to the GWC runtime.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _empty_store(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "artifact_type": "audit-checkpoint-store",
            "revision": 0,
            "events": [],
            "store_digest": "",
        }

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._empty_store()
        with self._path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in self._empty_store().items():
            data.setdefault(k, v)
        return data

    def _save(self, store: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def emit(self, event: AuditEvent, expected_revision: int | None = None) -> int:
        store = self._load()
        if expected_revision is not None and expected_revision != store["revision"]:
            raise ValueError(f"CAS_MISMATCH expected={expected_revision} actual={store['revision']}")
        next_revision = store["revision"] + 1
        record = event.to_dict()
        record["revision"] = next_revision
        record["event_digest"] = _digest(record)
        store["revision"] = next_revision
        store["events"].append(record)
        store["store_digest"] = _digest({"revision": store["revision"], "events": store["events"]})
        self._save(store)
        return next_revision

    def replay(self) -> list[dict[str, Any]]:
        return self._load().get("events", [])

    def store_digest(self) -> str:
        return self._load().get("store_digest", "")
