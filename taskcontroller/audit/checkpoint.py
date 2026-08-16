from __future__ import annotations

"""Audit checkpoint store — CAS pattern from checkpoint_store.py.

Pure library. No external imports. Replay-safe after crash/restart.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from taskcontroller.audit.event import AuditEvent


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class AuditCheckpointStore:
    """CAS-versioned audit checkpoint store.

    Append-only event log with optimistic revision binding.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _empty(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "artifact_type": "audit-checkpoint-store",
            "revision": 0,
            "events": [],
            "store_digest": "",
        }

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._empty()
        with self._path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in self._empty().items():
            data.setdefault(k, v)
        return data

    def _save(self, store: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def append(self, event: AuditEvent, expected_revision: int | None = None) -> int:
        """Append one event, returning the new revision.

        Raises ValueError on CAS mismatch.
        """
        store = self._load()
        if expected_revision is not None and expected_revision != store["revision"]:
            raise ValueError(
                f"CAS_MISMATCH expected={expected_revision} actual={store['revision']}"
            )
        next_revision = store["revision"] + 1
        record = event.to_dict()
        record["revision"] = next_revision
        record["event_digest"] = _digest(record)
        store["revision"] = next_revision
        store["events"].append(record)
        store["store_digest"] = _digest(
            {"revision": store["revision"], "events": store["events"]}
        )
        self._save(store)
        return next_revision

    def replay(self) -> list[dict[str, Any]]:
        """Read back all events without mutating."""
        return list(self._load().get("events", []))

    def current_revision(self) -> int:
        return self._load().get("revision", 0)

    def store_digest(self) -> str:
        return self._load().get("store_digest", "")

    def last_event(self) -> dict[str, Any] | None:
        events = self.replay()
        return events[-1] if events else None
