"""WP2 runtime checkpoint + recovery (NO GWC).

CheckpointSnapshot captures full runtime state (TeamRunState + version + RuntimeSnapshotMeta)
in a serializable dict for recovery/rehydration.

Recovery contract (controller C3):
- Checkpoint journal_position = the last RuntimeRecord.record_index included in the snapshot.
- Recovery reads records with record_index > journal_position and replays them through pure
  reducers (no fresh clock, no live acceptance rerun).
- journal_position is authoritative from the actual durable journal (RuntimeRecord.record_index),
  not from a soft meta counter.
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
from taskcontroller.runtime.store import StateStore, SnapshotRecord, RuntimeRecord


_EventFingerprint = dict[str, Any]


def build_checkpoint_snapshot(
    store: StateStore,
    run_id: str,
) -> CheckpointSnapshot:
    """Build a CheckpointSnapshot for a single run from the store.

    journal_position is the authoritative last RuntimeRecord.record_index for the
    run (or -1 if the journal is empty). Raises KeyError if run not found.
    """
    rs = store.get_run(run_id)
    if rs is None:
        raise KeyError(f"run {run_id} not found in store")
    meta = _coerce_meta(rs.meta)

    # Authoritative journal high-water mark (last included record_index).
    # SOLE authority is the durable journal's actual RuntimeRecord.record_index,
    # NEVER the run/state version (they may diverge independently).
    journal_position = store.last_record_index(run_id)

    # Merge runtime dedupe sidecar (event fingerprints + stream watermarks) from the
    # store into the checkpoint meta. EventRouter/LeaseManager persist these in the
    # store's flat _dedupe sidecar (event_id/idempotency keys + stream: keys), not in
    # run meta, so recovery can preserve post-checkpoint dedupe/fencing/watermark behavior.
    store_dedupe = store.dedupe_state()
    merged_fingerprints = dict(meta.dedupe_fingerprints)
    merged_watermarks = dict(meta.stream_watermarks)
    for key, val in store_dedupe.items():
        if key.startswith("stream:"):
            parts = key.split(":", 2)
            if len(parts) == 3:
                merged_watermarks[(parts[1], parts[2])] = (
                    StreamWatermark.from_dict(val) if isinstance(val, dict) else val
                )
        else:
            merged_fingerprints[key] = val

    # Keep meta.journal_position consistent with the durable journal so restored
    # state carries the same high-water mark.
    meta = RuntimeSnapshotMeta(
        attempt_registry=meta.attempt_registry,
        leases=meta.leases,
        stream_watermarks=merged_watermarks,
        event_cursor=meta.event_cursor,
        dedupe_fingerprints=merged_fingerprints,
        journal_position=journal_position,
    )

    return CheckpointSnapshot(
        run_id=rs.state.run_id,
        state=rs.state,
        version=rs.version,
        meta=meta,
    )


def checkpoint_after_index(
    store: StateStore,
    run_id: str,
    journal_position: int,
) -> list[RuntimeRecord]:
    """Return the durable journal window for recovery: records with record_index > journal_position.

    These are the trusted RuntimeRecords to replay after restoring the checkpoint.
    Ordering is by RuntimeRecord.record_index (ascending).
    """
    recs = store.journal_get(run_id, journal_position)
    return sorted(recs, key=lambda r: r.record_index)


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
    """Restore store from a CheckpointSnapshot (full rehydration).

    Rebuilds the run state AND the store's dedupe sidecar (event-id/idempotency
    fingerprints + per-stream sequence watermarks) from the checkpoint meta so
    post-restart dedupe/fencing/watermark behavior is preserved. The journal is
    re-seeded by the caller's replay step (or left empty for a fresh recovery).
    """
    # snapshot.meta is already a RuntimeSnapshotMeta; preserve it as the run meta
    # (store the typed object, not a dict, so recovery equivalence holds even when
    # there are no post-checkpoint records to replay).
    vs = VersionedRunState(
        state=snapshot.state,
        version=snapshot.version,
        meta=snapshot.meta,
    )
    # Rebuild store dedupe sidecar from meta so post-restart behavior is preserved
    dedupe: dict[str, Any] = {}
    for key, fp in snapshot.meta.dedupe_fingerprints.items():
        dedupe[key] = dict(fp)
    for (exec_id, att_id), wm in snapshot.meta.stream_watermarks.items():
        dedupe[f"stream:{exec_id}:{att_id}"] = wm.to_dict() if hasattr(wm, "to_dict") else wm
    store.restore(SnapshotRecord(
        runs={snapshot.run_id: vs},
        journals={},
        dedupe=dedupe,
    ))
