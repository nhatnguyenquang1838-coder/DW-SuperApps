"""WP2 runtime checkpoint + recovery (NO GWC).

CheckpointSnapshot captures full runtime state (TeamRunState + version + RuntimeSnapshotMeta)
in a serializable dict for recovery/rehydration.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.domain.models import TeamRunState
from taskcontroller.runtime.runtime_state import (
    CheckpointSnapshot,
    RuntimeSnapshotMeta,
    AttemptRecord,
    RuntimeLeaseState,
    StreamWatermark,
    VersionedRunState,
)
from taskcontroller.domain.values import EventCursor
from taskcontroller.runtime.store import StateStore, SnapshotRecord

_EventFingerprint = dict[str, Any]


def build_checkpoint_snapshot(
    store: StateStore,
    run_id: str,
) -> CheckpointSnapshot:
    """Build a CheckpointSnapshot for a single run from the store.

    Raises KeyError if run not found.
    """
    rs = store.get_run(run_id)
    if rs is None:
        raise KeyError(f"run {run_id} not found in store")
    meta = _coerce_meta(rs.meta)
    return CheckpointSnapshot(
        run_id=rs.state.run_id,
        state=rs.state,
        version=rs.version,
        meta=meta,
    )


def _coerce_meta(meta: Any) -> RuntimeSnapshotMeta:
    """Coerce a dict or partial meta into RuntimeSnapshotMeta."""
    if isinstance(meta, RuntimeSnapshotMeta):
        return meta
    if isinstance(meta, dict):
        leases_raw = meta.get("leases", {})
        leases = {}
        for k, v in leases_raw.items():
            if isinstance(v, dict):
                from taskcontroller.domain.models import WorkLease
                leases[k] = WorkLease.from_dict(v)
            else:
                leases[k] = v
        return RuntimeSnapshotMeta(
            attempt_registry={
                k: AttemptRecord.from_dict(v) if isinstance(v, dict) else v
                for k, v in meta.get("attempt_registry", {}).items()
            },
            leases=RuntimeLeaseState(leases=leases),
            stream_watermarks={
                k: StreamWatermark.from_dict(v) if isinstance(v, dict) else v
                for k, v in meta.get("stream_watermarks", {}).items()
            },
            event_cursor=EventCursor.from_dict(meta["event_cursor"]) if meta.get("event_cursor") else None,
            dedupe_fingerprints=dict(meta.get("dedupe_fingerprints", {})),
            journal_position=meta.get("journal_position", 0),
        )
    raise TypeError(f"cannot coerce meta of type {type(meta)}")


def restore_from_checkpoint(
    store: StateStore,
    snapshot: CheckpointSnapshot,
) -> None:
    """Restore store from a CheckpointSnapshot (full rehydration)."""
    # snapshot.meta is already a RuntimeSnapshotMeta; convert to dict for VersionedRunState
    meta_dict: dict[str, Any] = {
        "attempt_registry": {k: v.to_dict() for k, v in snapshot.meta.attempt_registry.items()},
        "leases": {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in snapshot.meta.leases.leases.items()},
        "stream_watermarks": {k: v.to_dict() for k, v in snapshot.meta.stream_watermarks.items()},
        "event_cursor": snapshot.meta.event_cursor.to_dict() if snapshot.meta.event_cursor else None,
        "dedupe_fingerprints": dict(snapshot.meta.dedupe_fingerprints),
        "journal_position": snapshot.meta.journal_position,
    }
    vs = VersionedRunState(
        state=snapshot.state,
        version=snapshot.version,
        meta=meta_dict,
    )
    store.restore(SnapshotRecord(
        runs={snapshot.run_id: vs},
        journals={},
        dedupe={},
    ))