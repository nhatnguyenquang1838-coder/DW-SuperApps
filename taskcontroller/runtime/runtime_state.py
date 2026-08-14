"""WP2 runtime state primitives: VersionedRunState, AttemptRecord, snapshots, stream watermarks.

These are runtime-only sidecars; they do NOT modify any WP0 schema.

Design invariants:
- VersionedRunState.version is the sole CAS source for state writes.
- AttemptRecord registry binds run/node/execution/attempt/current lease+fencing.
- Per (execution_id, attempt_id) producer sequence watermark.
- run-level EventCursor is an accepted-event log cursor, NOT producer sequence.
- All public constructors/accessors return deep copies where mutation could
  leak aliasing back into the store.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from taskcontroller.domain.enums import LeaseStatus, NodeStatus
from taskcontroller.domain.models import TeamRunState, WorkLease
from taskcontroller.domain.values import EventCursor


def _deep(obj: Any) -> Any:
    return copy.deepcopy(obj)


# ---------------------------------------------------------------------------
# AttemptRecord (runtime-only sidecar)
# ---------------------------------------------------------------------------

@dataclass
class AttemptRecord:
    """Runtime-only binding: attempt_id -> run/node/execution/lease/fencing/status.

    This supplements WP0 TeamRunState.active_attempts (which only carries IDs)
    so event correlation can prove run_id:node_id:execution_id:attempt_id mapping.
    """

    attempt_id: str
    run_id: str
    node_id: str
    execution_id: str
    current_lease_id: str | None  # ACTIVE lease for this attempt, if any
    fencing_token: str
    status: str  # runtime attempt status; MVP mirrors NodeStatus-ish values
    current_attempt_number: int

    def to_dict(self) -> dict:
        return {
            "attempt_id": self.attempt_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "execution_id": self.execution_id,
            "current_lease_id": self.current_lease_id,
            "fencing_token": self.fencing_token,
            "status": self.status,
            "current_attempt_number": self.current_attempt_number,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AttemptRecord":
        return cls(
            attempt_id=d["attempt_id"],
            run_id=d["run_id"],
            node_id=d["node_id"],
            execution_id=d["execution_id"],
            current_lease_id=d.get("current_lease_id"),
            fencing_token=d["fencing_token"],
            status=d["status"],
            current_attempt_number=d["current_attempt_number"],
        )


# ---------------------------------------------------------------------------
# per-stream sequence watermark
# ---------------------------------------------------------------------------

@dataclass
class StreamWatermark:
    """Producer sequence watermark for one (execution_id, attempt_id) stream.

    TeamRunState.last_event_cursor is an accepted-event log cursor, NOT this.
    """

    execution_id: str
    attempt_id: str
    producer_sequence: int  # next expected producer sequence for this stream

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "attempt_id": self.attempt_id,
            "producer_sequence": self.producer_sequence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StreamWatermark":
        return cls(
            execution_id=d["execution_id"],
            attempt_id=d["attempt_id"],
            producer_sequence=d["producer_sequence"],
        )


# ---------------------------------------------------------------------------
# VersionedRunState (CAS source)
# ---------------------------------------------------------------------------

@dataclass
class VersionedRunState:
    """Runtime wrapper: WP0 TeamRunState + CAS version + runtime metadata.

    version is the sole CAS source for state writes.
    meta carries runtime-only sidecars (attempt registry, watermarks, etc.)
    without touching WP0 schemas.
    """

    state: TeamRunState
    version: int
    meta: dict[str, Any] | RuntimeSnapshotMeta = field(default_factory=dict)

    def to_dict(self) -> dict:
        meta_dict: dict[str, Any]
        if isinstance(self.meta, RuntimeSnapshotMeta):
            meta_dict = {
                "attempt_registry": {k: v.to_dict() for k, v in self.meta.attempt_registry.items()},
                "leases": self.meta.leases.to_dict(),
                "stream_watermarks": {k: v.to_dict() for k, v in self.meta.stream_watermarks.items()},
                "event_cursor": self.meta.event_cursor.to_dict() if self.meta.event_cursor else None,
                "dedupe_fingerprints": dict(self.meta.dedupe_fingerprints),
                "journal_position": self.meta.journal_position,
            }
        else:
            meta_dict = dict(self.meta)
        return {
            "state": self.state.to_dict(),
            "version": self.version,
            "meta": meta_dict,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VersionedRunState":
        meta_raw = d.get("meta", {})
        if isinstance(meta_raw, dict) and "attempt_registry" in meta_raw:
            meta = RuntimeSnapshotMeta(
                attempt_registry={k: AttemptRecord.from_dict(v) for k, v in meta_raw.get("attempt_registry", {}).items()},
                leases=RuntimeLeaseState.from_dict(meta_raw.get("leases", {})),
                stream_watermarks={k: StreamWatermark.from_dict(v) for k, v in meta_raw.get("stream_watermarks", {}).items()},
                event_cursor=EventCursor.from_dict(meta_raw["event_cursor"]) if meta_raw.get("event_cursor") else None,
                dedupe_fingerprints=dict(meta_raw.get("dedupe_fingerprints", {})),
                journal_position=meta_raw.get("journal_position", 0),
            )
        else:
            meta = dict(meta_raw)
        return cls(
            state=TeamRunState.from_dict(d["state"]),
            version=d["version"],
            meta=meta,
        )


# ---------------------------------------------------------------------------
# Runtime-side snapshot + pending mutation types
# ---------------------------------------------------------------------------

@dataclass
class PendingMutation:
    """A validated mutation ready for CAS commit."""

    expected_version: int
    new_state: VersionedRunState


@dataclass
class RuntimeLeaseState:
    """Runtime snapshot of the current leases active in a run (sidecar)."""

    leases: dict[str, WorkLease]  # lease_id -> WorkLease (deep copy on export)

    def to_dict(self) -> dict:
        return {lid: lease.to_dict() for lid, lease in self.leases.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "RuntimeLeaseState":
        return cls(
            leases={lid: WorkLease.from_dict(v) for lid, v in d.items()}
        )


@dataclass
class RuntimeSnapshotMeta:
    """Runtime-only metadata section inside a checkpoint snapshot."""

    attempt_registry: dict[str, AttemptRecord]
    leases: RuntimeLeaseState
    stream_watermarks: dict[str, StreamWatermark]  # key=(execution_id,attempt_id)
    event_cursor: EventCursor | None
    dedupe_fingerprints: dict[str, dict[str, Any]]
    journal_position: int  # last committed record_index for this run


@dataclass
class CheckpointSnapshot:
    """Full checkpoint snapshot record (sidecar content, not a WP0 schema)."""

    run_id: str
    state: TeamRunState
    version: int
    meta: RuntimeSnapshotMeta

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "state": self.state.to_dict(),
            "version": self.version,
            "meta": {
                "attempt_registry": {k: v.to_dict() for k, v in self.meta.attempt_registry.items()},
                "leases": self.meta.leases.to_dict(),
                "stream_watermarks": {k: v.to_dict() for k, v in self.meta.stream_watermarks.items()},
                "event_cursor": self.meta.event_cursor.to_dict() if self.meta.event_cursor else None,
                "dedupe_fingerprints": dict(self.meta.dedupe_fingerprints),
                "journal_position": self.meta.journal_position,
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CheckpointSnapshot":
        meta = d["meta"]
        return cls(
            run_id=d["run_id"],
            state=TeamRunState.from_dict(d["state"]),
            version=d["version"],
            meta=RuntimeSnapshotMeta(
                attempt_registry={k: AttemptRecord.from_dict(v) for k, v in meta["attempt_registry"].items()},
                leases=RuntimeLeaseState.from_dict(meta["leases"]),
                stream_watermarks={k: StreamWatermark.from_dict(v) for k, v in meta["stream_watermarks"].items()},
                event_cursor=EventCursor.from_dict(meta["event_cursor"]) if meta.get("event_cursor") else None,
                dedupe_fingerprints=dict(meta["dedupe_fingerprints"]),
                journal_position=meta["journal_position"],
            ),
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_versioned_run(
    state: TeamRunState,
    version: int,
    meta: dict[str, Any] | None = None,
) -> VersionedRunState:
    """Factory with deep-copy of state so caller cannot alias-store-mutate."""
    return VersionedRunState(state=_deep(state), version=version, meta=dict(meta or {}))


def make_attempt_record(
    attempt_id: str,
    run_id: str,
    node_id: str,
    execution_id: str,
    fencing_token: str,
    current_attempt_number: int,
    current_lease_id: str | None = None,
    status: str = NodeStatus.PENDING.value,
) -> AttemptRecord:
    return AttemptRecord(
        attempt_id=attempt_id,
        run_id=run_id,
        node_id=node_id,
        execution_id=execution_id,
        current_lease_id=current_lease_id,
        fencing_token=fencing_token,
        status=status,
        current_attempt_number=current_attempt_number,
    )
