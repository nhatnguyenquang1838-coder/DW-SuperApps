"""Bounded semantic audit events for TaskController runs.

The semantic recorder is an additive projection over the existing AuditFacade.
It stores event identity, stable stage names, bounded scalar metadata and
references; it never stores prompts, transcripts or reasoning content.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Protocol, TypeAlias

from taskcontroller.audit.event import AuditEvent


JSONScalar: TypeAlias = str | int | bool | None


class SemanticAuditError(ValueError):
    """Fail-closed validation error for the bounded semantic audit contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class SemanticAuditEventKind(str, Enum):
    """Stable semantic stages needed to reconstruct a bounded run."""

    MAILBOX_WRITE = "MAILBOX_WRITE"
    MAILBOX_READBACK = "MAILBOX_READBACK"
    WAKEUP = "WAKEUP"
    BOOTSTRAP = "BOOTSTRAP"
    CLASSIFICATION = "CLASSIFICATION"
    FANOUT = "FANOUT"
    CHILD_COMPLETION = "CHILD_COMPLETION"
    MIXER = "MIXER"
    TERMINAL_COMMIT = "TERMINAL_COMMIT"
    RESUME = "RESUME"
    STALE_REJECTION = "STALE_REJECTION"


_ALLOWED_METADATA_KEYS = frozenset(
    {
        "attempt_id",
        "child_id",
        "child_status",
        "classification",
        "conflict_rate",
        "correlation_id",
        "evidence_count",
        "event_digest",
        "join_status",
        "lease_generation",
        "manifest_digest",
        "message_id",
        "outcome",
        "reason",
        "rejection_code",
        "result_digest",
        "reviewer_count",
        "sequence_hint",
        "source_digest",
        "stage",
        "standards_digest",
        "status",
        "wakeup_ref",
    }
)
_RAW_METADATA_KEYS = frozenset(
    {
        "chain_of_thought",
        "messages",
        "prompt",
        "raw_prompt",
        "raw_transcript",
        "reasoning",
        "transcript",
    }
)
_EVIDENCE_REF_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:(?:/{0,2})[^\s]+$")
_MAX_IDENTITY_LENGTH = 256
_MAX_METADATA_STRING_LENGTH = 256
_MAX_METADATA_INTEGER = 1_000_000_000


class SemanticAuditSink(Protocol):
    """The minimal existing-facade surface used by the recorder/projection."""

    def record(self, run_id: str, event: AuditEvent) -> int:
        ...

    def events(self, run_id: str) -> list[AuditEvent]:
        ...


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise SemanticAuditError("IDENTITY_REQUIRED", f"{field} must be non-empty text")
    normalized = value.strip()
    if len(normalized) > _MAX_IDENTITY_LENGTH:
        raise SemanticAuditError("IDENTITY_INVALID", f"{field} exceeds {_MAX_IDENTITY_LENGTH} characters")
    return normalized


def _optional_text(value: str, field: str) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise SemanticAuditError("IDENTITY_INVALID", f"{field} must be text")
    normalized = value.strip()
    if len(normalized) > _MAX_IDENTITY_LENGTH:
        raise SemanticAuditError("IDENTITY_INVALID", f"{field} exceeds {_MAX_IDENTITY_LENGTH} characters")
    return normalized


def _coerce_kind(value: SemanticAuditEventKind | str) -> SemanticAuditEventKind:
    if isinstance(value, SemanticAuditEventKind):
        return value
    if not isinstance(value, str):
        raise SemanticAuditError("UNKNOWN_EVENT_KIND", "event kind must be a known string")
    try:
        return SemanticAuditEventKind(value)
    except ValueError as exc:
        raise SemanticAuditError("UNKNOWN_EVENT_KIND", f"unsupported kind {value!r}") from exc


def _validate_evidence_refs(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise SemanticAuditError("EVIDENCE_REF_INVALID", "evidence_refs must be a sequence of references")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or len(value) > _MAX_IDENTITY_LENGTH:
            raise SemanticAuditError("EVIDENCE_REF_INVALID", "reference must be bounded text")
        normalized = value.strip()
        if not _EVIDENCE_REF_PATTERN.fullmatch(normalized):
            raise SemanticAuditError("EVIDENCE_REF_INVALID", f"malformed reference {value!r}")
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return tuple(result)


def _validate_metadata(values: Mapping[str, JSONScalar] | None) -> dict[str, JSONScalar]:
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise SemanticAuditError("METADATA_INVALID", "metadata must be a mapping")

    normalized: dict[str, JSONScalar] = {}
    for key, value in values.items():
        if not isinstance(key, str):
            raise SemanticAuditError("METADATA_KEY_INVALID", "metadata keys must be text")
        if key in _RAW_METADATA_KEYS:
            raise SemanticAuditError("RAW_CONTENT_FORBIDDEN", f"raw field {key!r} is not permitted")
        if key not in _ALLOWED_METADATA_KEYS:
            raise SemanticAuditError("METADATA_KEY_FORBIDDEN", f"unbounded field {key!r} is not permitted")
        if isinstance(value, str):
            if len(value) > _MAX_METADATA_STRING_LENGTH or "\x00" in value:
                raise SemanticAuditError("METADATA_VALUE_INVALID", f"metadata value for {key!r} is not bounded")
        elif isinstance(value, bool) or value is None:
            pass
        elif isinstance(value, int):
            if abs(value) > _MAX_METADATA_INTEGER:
                raise SemanticAuditError("METADATA_VALUE_INVALID", f"metadata integer for {key!r} is not bounded")
        else:
            raise SemanticAuditError("METADATA_VALUE_INVALID", f"metadata value for {key!r} is not scalar")
        normalized[key] = value
    return {key: normalized[key] for key in sorted(normalized)}


def _metadata_from_event(event: AuditEvent) -> tuple[tuple[str, JSONScalar], ...]:
    after = event.after
    if not isinstance(after, Mapping):
        raise SemanticAuditError("EVENT_INVALID", "semantic event after-state must be a mapping")
    marker = after.get("semantic_event")
    if marker != event.decision_kind:
        raise SemanticAuditError("EVENT_INVALID", "semantic event marker does not match decision kind")
    values = {key: value for key, value in after.items() if key != "semantic_event"}
    return tuple(_validate_metadata(values).items())


class SemanticAuditEventRecorder:
    """Record stable, bounded semantic events through an existing facade."""

    def __init__(self, sink: SemanticAuditSink) -> None:
        if not callable(getattr(sink, "record", None)):
            raise SemanticAuditError("SINK_INVALID", "sink must expose record(run_id, event)")
        self._sink = sink

    def record(
        self,
        kind: SemanticAuditEventKind | str,
        *,
        event_id: str,
        timestamp: str,
        run_id: str,
        source: str,
        node_id: str = "",
        actor: str = "",
        authority_ref: str = "",
        evidence_refs: Sequence[str] = (),
        metadata: Mapping[str, JSONScalar] | None = None,
    ) -> int:
        semantic_kind = _coerce_kind(kind)
        event = AuditEvent(
            event_id=_required_text(event_id, "event_id"),
            timestamp=_required_text(timestamp, "timestamp"),
            run_id=_required_text(run_id, "run_id"),
            source=_required_text(source, "source"),
            decision_kind=semantic_kind.value,
            node_id=_optional_text(node_id, "node_id"),
            actor=_optional_text(actor, "actor"),
            authority_ref=_optional_text(authority_ref, "authority_ref"),
            payload_summary=semantic_kind.value,
            raw_payload_ref="",
            before={},
            after={
                "semantic_event": semantic_kind.value,
                **_validate_metadata(metadata),
            },
            evidence_refs=_validate_evidence_refs(evidence_refs),
            annotations={"semantic_audit_contract": "v1"},
            version=1,
        )
        return self._sink.record(event.run_id, event)


@dataclass(frozen=True, slots=True)
class SemanticAuditEntry:
    """A projection-safe semantic event entry without raw payload content."""

    sequence: int | None
    event_id: str
    timestamp: str
    kind: SemanticAuditEventKind
    node_id: str
    actor: str
    authority_ref: str
    evidence_refs: tuple[str, ...]
    metadata: tuple[tuple[str, JSONScalar], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "kind": self.kind.value,
            "node_id": self.node_id,
            "actor": self.actor,
            "authority_ref": self.authority_ref,
            "evidence_refs": list(self.evidence_refs),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SemanticAuditTimeline:
    """Deterministic, bounded run reconstruction from semantic event refs."""

    run_id: str
    entries: tuple[SemanticAuditEntry, ...]
    evidence_refs: tuple[str, ...]

    @property
    def event_count(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "event_count": self.event_count,
            "entries": [entry.to_dict() for entry in self.entries],
            "evidence_refs": list(self.evidence_refs),
        }


def _entry_sort_key(entry: SemanticAuditEntry) -> tuple[bool, int, str, str]:
    if entry.sequence is None:
        return (True, 0, entry.timestamp, entry.event_id)
    return (False, entry.sequence, entry.timestamp, entry.event_id)


def reconstruct_semantic_timeline(
    sink: SemanticAuditSink,
    run_id: str,
) -> SemanticAuditTimeline:
    """Reconstruct only the bounded semantic projection for ``run_id``."""

    requested_run_id = _required_text(run_id, "run_id")
    if not callable(getattr(sink, "events", None)):
        raise SemanticAuditError("SINK_INVALID", "sink must expose events(run_id)")

    entries: list[SemanticAuditEntry] = []
    for event in sink.events(requested_run_id):
        if not isinstance(event, AuditEvent):
            raise SemanticAuditError("EVENT_INVALID", "event source returned a non-AuditEvent")
        if event.run_id != requested_run_id:
            raise SemanticAuditError("RUN_ID_MISMATCH", "event belongs to a different run")
        try:
            kind = _coerce_kind(event.decision_kind)
        except SemanticAuditError as exc:
            if exc.code == "UNKNOWN_EVENT_KIND":
                continue
            raise
        entries.append(
            SemanticAuditEntry(
                sequence=event.sequence,
                event_id=event.event_id,
                timestamp=event.timestamp,
                kind=kind,
                node_id=event.node_id,
                actor=event.actor,
                authority_ref=event.authority_ref,
                evidence_refs=_validate_evidence_refs(event.evidence_refs),
                metadata=_metadata_from_event(event),
            )
        )

    ordered = tuple(sorted(entries, key=_entry_sort_key))
    evidence: list[str] = []
    seen: set[str] = set()
    for entry in ordered:
        for ref in entry.evidence_refs:
            if ref not in seen:
                evidence.append(ref)
                seen.add(ref)
    return SemanticAuditTimeline(
        run_id=requested_run_id,
        entries=ordered,
        evidence_refs=tuple(evidence),
    )


__all__ = [
    "SemanticAuditEntry",
    "SemanticAuditError",
    "SemanticAuditEventKind",
    "SemanticAuditEventRecorder",
    "SemanticAuditTimeline",
    "reconstruct_semantic_timeline",
]
