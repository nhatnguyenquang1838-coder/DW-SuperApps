"""Append-only, tamper-detecting certification event store."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .certification_models import (
    SourceRevision,
    TestRun,
    _deep_freeze,
    _plain,
)


class CertificationStoreError(ValueError):
    """Raised when durable certification evidence is invalid or inconsistent."""


def _canonical(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _record_digest(
    *,
    schema_version: int,
    event_seq: int,
    event_type: str,
    aggregate_id: str,
    payload: Mapping[str, Any],
    previous_digest: str,
) -> str:
    content = {
        "schema_version": schema_version,
        "event_seq": event_seq,
        "event_type": event_type,
        "aggregate_id": aggregate_id,
        "payload": _plain(payload),
        "previous_digest": previous_digest,
    }
    return hashlib.sha256(_canonical(content)).hexdigest()


@dataclass(frozen=True)
class CertificationEvent:
    schema_version: int
    event_seq: int
    event_type: str
    aggregate_id: str
    payload: Mapping[str, object] = field(default_factory=dict)
    previous_digest: str = "GENESIS"
    record_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise CertificationStoreError(
                f"unsupported certification event schema {self.schema_version!r}"
            )
        if not isinstance(self.event_seq, int) or self.event_seq < 1:
            raise CertificationStoreError("event_seq must be a positive integer")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise CertificationStoreError("event_type is required")
        if not isinstance(self.aggregate_id, str) or not self.aggregate_id.strip():
            raise CertificationStoreError("aggregate_id is required")
        if self.previous_digest != "GENESIS" and len(self.previous_digest) != 64:
            raise CertificationStoreError("previous_digest must be GENESIS or a 64-hex digest")
        if len(self.record_digest) != 64:
            raise CertificationStoreError("record_digest must be a 64-hex digest")
        if not isinstance(self.payload, Mapping):
            raise CertificationStoreError("payload must be a mapping")
        object.__setattr__(self, "payload", _deep_freeze(dict(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_seq": self.event_seq,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "payload": _plain(self.payload),
            "previous_digest": self.previous_digest,
            "record_digest": self.record_digest,
        }


class CertificationStore:
    """Durable JSONL event store with a single append-only hash chain."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._events = tuple(self._read_events())

    def _read_events(self) -> list[CertificationEvent]:
        if not self.path.exists():
            return []
        events: list[CertificationEvent] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise CertificationStoreError(f"cannot read certification store: {exc}") from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CertificationStoreError(
                    f"invalid JSON at event line {line_number}"
                ) from exc
            if not isinstance(raw, Mapping):
                raise CertificationStoreError(f"event line {line_number} is not an object")
            try:
                event = CertificationEvent(
                    schema_version=raw["schema_version"],
                    event_seq=raw["event_seq"],
                    event_type=raw["event_type"],
                    aggregate_id=raw["aggregate_id"],
                    payload=raw.get("payload", {}),
                    previous_digest=raw["previous_digest"],
                    record_digest=raw["record_digest"],
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise CertificationStoreError(
                    f"invalid certification event at line {line_number}: {exc}"
                ) from exc
            expected_seq = len(events) + 1
            if event.event_seq != expected_seq:
                raise CertificationStoreError(
                    f"event_seq {event.event_seq} is not the expected sequence {expected_seq}"
                )
            expected_previous = events[-1].record_digest if events else "GENESIS"
            if event.previous_digest != expected_previous:
                raise CertificationStoreError(
                    f"previous_digest chain mismatch at event {event.event_seq}"
                )
            expected_digest = _record_digest(
                schema_version=event.schema_version,
                event_seq=event.event_seq,
                event_type=event.event_type,
                aggregate_id=event.aggregate_id,
                payload=event.payload,
                previous_digest=event.previous_digest,
            )
            if event.record_digest != expected_digest:
                raise CertificationStoreError(
                    f"record digest mismatch at event {event.event_seq}"
                )
            events.append(event)
        return events

    def replay(self) -> tuple[CertificationEvent, ...]:
        """Return the validated event chain, re-reading the durable file."""
        self._events = tuple(self._read_events())
        return self._events

    def append(
        self,
        event_type: str,
        aggregate_id: str,
        payload: Mapping[str, object],
    ) -> CertificationEvent:
        """Append one event and fsync it before returning the immutable record."""
        current = self.replay()
        event_seq = len(current) + 1
        previous_digest = current[-1].record_digest if current else "GENESIS"
        digest = _record_digest(
            schema_version=1,
            event_seq=event_seq,
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
            previous_digest=previous_digest,
        )
        event = CertificationEvent(
            schema_version=1,
            event_seq=event_seq,
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
            previous_digest=previous_digest,
            record_digest=digest,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise CertificationStoreError(f"cannot append certification event: {exc}") from exc
        self._events = (*current, event)
        return event

    def load_legacy_runs(self, legacy_path: str | Path) -> tuple[TestRun, ...]:
        """Load old W7 JSONL records as explicitly marked immutable evidence.

        Legacy records predate separate runtime/subject/GWC bindings. Their old
        base/head pair is retained for both source revisions and an all-zero GWC
        sentinel is recorded only with ``legacy=True`` plus provenance evidence.
        New TestRuns never use this compatibility path.
        """
        source = Path(legacy_path)
        if not source.exists():
            raise CertificationStoreError(f"legacy store does not exist: {source}")
        runs: list[TestRun] = []
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise CertificationStoreError(f"cannot read legacy store: {exc}") from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CertificationStoreError(
                    f"invalid legacy JSON at line {line_number}"
                ) from exc
            if not isinstance(raw, Mapping):
                raise CertificationStoreError(f"legacy line {line_number} is not an object")
            supplied_hash = raw.get("_sha256")
            content = {key: value for key, value in raw.items() if key != "_sha256"}
            if supplied_hash is not None:
                expected_hash = hashlib.sha256(
                    json.dumps(content, sort_keys=True).encode("utf-8")
                ).hexdigest()
                if supplied_hash != expected_hash:
                    raise CertificationStoreError(
                        f"legacy record hash mismatch at line {line_number}"
                    )
            try:
                run_id = str(raw["run_id"])
                base_sha = str(raw["base_sha"])
                head_sha = str(raw["head_sha"])
                runtime_plan_ref = str(raw.get("runtime_plan_ref") or f"legacy://plan/{run_id}")
                runtime_plan_digest = str(
                    raw.get("runtime_plan_digest")
                    or "sha256:" + hashlib.sha256(runtime_plan_ref.encode()).hexdigest()
                )
                evidence = dict(raw.get("evidence") or {})
                evidence["legacy_import"] = {
                    "schema_version": 1,
                    "source_path": str(source),
                    "source_line": line_number,
                    "source_binding": "legacy-v1-no-separate-gwc-binding",
                }
                runtime = SourceRevision(
                    repository=str(raw.get("repository") or "legacy/W7"),
                    branch=str(raw["branch"]),
                    start_sha=base_sha,
                    end_sha=head_sha,
                )
                subject = SourceRevision(
                    repository=str(raw.get("repository") or "legacy/W7"),
                    branch=str(raw["branch"]),
                    start_sha=base_sha,
                    end_sha=head_sha,
                )
                run = TestRun(
                    run_id=run_id,
                    campaign_id=str(raw.get("campaign_id") or "legacy-w7"),
                    case_id=str(raw["case_id"]),
                    case_revision=str(raw.get("case_revision") or "legacy-v1"),
                    runtime=runtime,
                    subject=subject,
                    gwc_sha=str(raw.get("gwc_sha") or "0" * 40),
                    runtime_plan_ref=runtime_plan_ref,
                    runtime_plan_revision=str(raw.get("runtime_plan_revision") or "legacy-v1"),
                    runtime_plan_digest=runtime_plan_digest,
                    executor=str(raw["executor"]),
                    model=str(raw["model"]),
                    verdict=str(raw.get("verdict") or "PENDING"),
                    evidence=evidence,
                    legacy=True,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise CertificationStoreError(
                    f"incompatible legacy W7 record at line {line_number}: {exc}"
                ) from exc
            runs.append(run)
        return tuple(runs)


__all__ = ["CertificationEvent", "CertificationStore", "CertificationStoreError"]
