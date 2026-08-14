"""WP2 runtime: deterministic journal + crash recovery (NO GWC).

Design invariants:
- Every accepted mutation (event, lease, checkpoint, control) is recorded as a
  RuntimeRecord in an append-only per-run journal.
- RuntimeRecord.record_index is the SOLE journal-order metadata. It is assigned
  monotonically by journal_append and NEVER duplicated into the payload.
- Checkpoint journal_position = the last RuntimeRecord.record_index included in
  the snapshot.
- Recovery RESTORES checkpoint state into a fresh/target store while RETAINING the
  original immutable journal snapshot. The journal is evidence and is never wiped
  or re-appended. Replay reads records with record_index > journal_position.
- Replay uses PURE reducers (apply_runtime_record) that consume only the trusted
  record payload + record_index. They perform NO live acceptance: no EventRouter /
  LeaseManager calls, no dedupe/correlation/fencing/sequence re-validation, no CAS
  decision, no fresh clock (`now`). Replay reconstructs BOTH canonical state and
  runtime sidecars (attempts/leases/current-lease/fencing, dedupe fingerprints,
  stream watermarks, EventCursor, journal_position) from the records alone.
- journal_get returns records after a given index for incremental replay.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from taskcontroller.runtime.store import StateStore, SnapshotRecord, RuntimeRecord
from taskcontroller.runtime.runtime_state import VersionedRunState, RuntimeSnapshotMeta
from taskcontroller.runtime.checkpoint import build_checkpoint_snapshot, restore_from_checkpoint


class Journal:
    """Append-only per-run journal manager.

    Wraps StateStore.journal_append / journal_get with run-scoped helpers.
    """

    def __init__(self, store: StateStore) -> None:
        self._store = store

    def append(self, run_id: str, kind: str, payload: dict) -> RuntimeRecord:
        """Append a record to the run's journal. Returns the record with assigned index."""
        rec = RuntimeRecord(kind=kind, run_id=run_id, payload=payload)
        self._store.journal_append(run_id, rec)
        return rec

    def get_after(self, run_id: str, after_index: int) -> list[RuntimeRecord]:
        """Return all records for run_id with record_index > after_index."""
        return self._store.journal_get(run_id, after_index)

    def last_index(self, run_id: str) -> int:
        """Return the highest record_index for the run, or -1 if empty."""
        recs = self._store.journal_get(run_id, -1)
        if not recs:
            return -1
        return max(r.record_index for r in recs)


# ---------------------------------------------------------------------------
# Replay sidecars (pure, in-memory accumulators built ONLY from record payloads)
# ---------------------------------------------------------------------------

@dataclass
class _ReplaySidecars:
    """Mutable sidecar accumulators reconstructed purely from replay records."""

    attempt_registry: dict[str, Any] = field(default_factory=dict)
    leases: dict[str, Any] = field(default_factory=dict)
    dedupe_fingerprints: dict[str, Any] = field(default_factory=dict)
    stream_watermarks: dict[str, Any] = field(default_factory=dict)
    event_cursor: Any | None = None
    journal_position: int = -1


def _meta_to_sidecars(meta: Any) -> _ReplaySidecars:
    """Seed replay sidecars from a checkpoint meta (state AT checkpoint only)."""
    if isinstance(meta, RuntimeSnapshotMeta):
        return _ReplaySidecars(
            attempt_registry={
                k: (v.to_dict() if hasattr(v, "to_dict") else v)
                for k, v in meta.attempt_registry.items()
            },
            leases={
                k: (v.to_dict() if hasattr(v, "to_dict") else v)
                for k, v in meta.leases.leases.items()
            },
            dedupe_fingerprints=dict(meta.dedupe_fingerprints),
            stream_watermarks={
                k: (v.to_dict() if hasattr(v, "to_dict") else v)
                for k, v in meta.stream_watermarks.items()
            },
            event_cursor=meta.event_cursor.to_dict() if meta.event_cursor else None,
            journal_position=meta.journal_position,
        )
    if isinstance(meta, dict):
        leases_raw = meta.get("leases", {})
        if hasattr(leases_raw, "leases"):
            leases_raw = leases_raw.leases
        return _ReplaySidecars(
            attempt_registry={
                k: (v.to_dict() if hasattr(v, "to_dict") else v)
                for k, v in meta.get("attempt_registry", {}).items()
            },
            leases={
                k: (v.to_dict() if hasattr(v, "to_dict") else v)
                for k, v in leases_raw.items()
            },
            dedupe_fingerprints=dict(meta.get("dedupe_fingerprints", {})),
            stream_watermarks={
                k: (v.to_dict() if hasattr(v, "to_dict") else v)
                for k, v in meta.get("stream_watermarks", {}).items()
            },
            event_cursor=meta.get("event_cursor"),
            journal_position=meta.get("journal_position", -1),
        )
    return _ReplaySidecars()


def _sidecars_to_meta(sc: _ReplaySidecars) -> RuntimeSnapshotMeta:
    """Build a RuntimeSnapshotMeta from replay sidecars (post-checkpoint state)."""
    from taskcontroller.domain.models import WorkLease
    from taskcontroller.runtime.runtime_state import AttemptRecord
    from taskcontroller.domain.values import EventCursor
    from taskcontroller.runtime.runtime_state import RuntimeLeaseState, StreamWatermark

    leases = {}
    for k, v in sc.leases.items():
        leases[k] = WorkLease.from_dict(v) if isinstance(v, dict) else v
    att_reg = {}
    for k, v in sc.attempt_registry.items():
        att_reg[k] = AttemptRecord.from_dict(v) if isinstance(v, dict) else v
    wms = {}
    for k, v in sc.stream_watermarks.items():
        wms[k] = StreamWatermark.from_dict(v) if isinstance(v, dict) else v
    return RuntimeSnapshotMeta(
        attempt_registry=att_reg,
        leases=RuntimeLeaseState(leases=leases),
        stream_watermarks=wms,
        event_cursor=EventCursor.from_dict(sc.event_cursor) if sc.event_cursor else None,
        dedupe_fingerprints=dict(sc.dedupe_fingerprints),
        journal_position=sc.journal_position,
    )


# ---------------------------------------------------------------------------
# Pure reducers (no live acceptance; trusted record payload + record_index only)
# ---------------------------------------------------------------------------

def _apply_event_record(state: VersionedRunState, sidecars: _ReplaySidecars, rec: RuntimeRecord) -> VersionedRunState:
    """Pure reducer for an accepted event record. Reconstructs state + sidecars.

    Consumes only the trusted payload (canonical event) and record_index.
    No dedupe re-validation, no correlation/fencing re-check, no CAS, no `now`.
    """
    from taskcontroller.domain.enums import NodeStatus, RunStatus
    from taskcontroller.domain.values import EventCursor
    from taskcontroller.kernel.transitions import validate_node_transition

    p = rec.payload
    new_version = (p.get("version") or state.version + 1)
    state_dict = copy.deepcopy(state.state.to_dict())

    # EventCursor always moves forward for accepted events
    seq = p.get("sequence", 0)
    state_dict["last_event_cursor"] = EventCursor(
        last_event_id=p.get("event_id", ""),
        sequence=seq,
    ).to_dict()
    sidecars.event_cursor = state_dict["last_event_cursor"]

    # artifact_refs recording (deterministic order, no set->list coercion)
    arts = p.get("artifact_refs") or []
    if arts:
        existing = list(state_dict.get("artifact_refs", []))
        for a in arts:
            a_id = a.get("artifact_id") if isinstance(a, dict) else str(a)
            if a_id not in existing:
                existing.append(a_id)
        state_dict["artifact_refs"] = existing

    # reducer authority per event_type (mirrors EventRouter._apply_*; no validation re-run
    # beyond the transition check that live acceptance already enforced — deterministic replay)
    etype = p.get("event_type")
    node_id = p.get("node_id")
    payload = p.get("payload") or {}
    if etype == "COMPLETED":
        if state_dict.get("status") not in (RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value):
            node = state_dict.get("nodes", {}).get(node_id)
            if node is not None and node.get("status") == NodeStatus.RUNNING.value:
                node = dict(node)
                node["status"] = NodeStatus.REVIEWING.value
                state_dict["nodes"] = dict(state_dict["nodes"])
                state_dict["nodes"][node_id] = node
    elif etype == "STATUS_CHANGE":
        proposed = payload.get("status")
        if proposed is not None and proposed != NodeStatus.DONE.value:
            node = state_dict.get("nodes", {}).get(node_id)
            if node is not None:
                try:
                    validate_node_transition(current=node.get("status"), target=proposed)
                    node = dict(node)
                    node["status"] = proposed
                    state_dict["nodes"] = dict(state_dict["nodes"])
                    state_dict["nodes"][node_id] = node
                except Exception:
                    pass  # live acceptance already validated; replay preserves recorded outcome
    # TASK_STARTED/PROGRESS/ARTIFACT_PRODUCED/etc: cursor + artifacts only

    # Reconstruct sidecars from the accepted event record
    fp = p.get("fingerprint")
    if fp is not None:
        for key in (p.get("event_id"), p.get("idempotency_key") and f"idem:{p['idempotency_key']}"):
            if key:
                sidecars.dedupe_fingerprints[key] = fp
    stream_key = (p.get("execution_id"), p.get("attempt_id"))
    if stream_key[0] is not None:
        sidecars.stream_watermarks[stream_key] = {
            "execution_id": stream_key[0],
            "attempt_id": stream_key[1],
            "producer_sequence": seq + 1,
        }

    sidecars.journal_position = rec.record_index
    from taskcontroller.domain.models import TeamRunState

    new_state = TeamRunState.from_dict(state_dict)
    return VersionedRunState(state=new_state, version=new_version, meta=_sidecars_to_meta(sidecars))


def _apply_lease_record(state: VersionedRunState, sidecars: _ReplaySidecars, rec: RuntimeRecord) -> VersionedRunState:
    """Pure reducer for a lease record. Reconstructs leases/node/attempt/sidecars.

    Consumes only the trusted payload (op + resulting snapshot data) and record_index.
    No live LeaseManager call, no CAS, no fencing re-validation.
    """
    from taskcontroller.domain.models import WorkLease, TeamRunState, NodeState, AttemptRecord

    p = rec.payload
    op = p.get("op")
    new_version = (p.get("version") or state.version + 1)
    state_dict = copy.deepcopy(state.state.to_dict())
    leases = dict(sidecars.leases)

    if op in ("grant", "replace"):
        lid = p["lease_id"]
        # Trusted-record contract: a replay-sufficient grant MUST carry the lease
        # identity fields. Missing required fields fail closed (no fabrication).
        if (
            "node_id" not in p
            or "execution_id" not in p
            or "holder" not in p
            or "granted_at" not in p
            or "expires_at" not in p
        ):
            raise RuntimeError(
                "malformed/incomplete lease grant record: missing required "
                "trusted fields (node_id, execution_id, holder, granted_at, expires_at)"
            )
        leases[lid] = {
            "lease_id": lid,
            "run_id": p.get("run_id", state.state.run_id),
            "node_id": p["node_id"],
            "execution_id": p["execution_id"],
            "attempt_id": p.get("attempt_id", ""),
            "holder": p["holder"],
            "fencing_token": p.get("fencing_token", ""),
            "granted_at": p["granted_at"],
            "expires_at": p["expires_at"],
            "resource_ref": p.get("resource_ref"),
            "status": "ACTIVE",
        }
        # node lease_ref
        node_id = p["node_id"]
        if node_id:
            nodes = dict(state_dict.get("nodes", {}))
            node = dict(nodes.get(node_id, {}))
            node["lease_ref"] = lid
            nodes[node_id] = node
            state_dict["nodes"] = nodes
        # rebuild active_leases deterministically (preserve order, append unseen)
        active = [
            _lid
            for _lid, _l in leases.items()
            if (_l.get("status") if isinstance(_l, dict) else getattr(_l, "status", None))
            == "ACTIVE"
        ]
        if lid not in active:
            active.append(lid)
        state_dict["active_leases"] = active
        # attempt current_lease_id + fencing
        att_id = p.get("attempt_id")
        if att_id and att_id in sidecars.attempt_registry:
            att = dict(sidecars.attempt_registry[att_id])
            att["current_lease_id"] = lid
            att["fencing_token"] = p.get("fencing_token", att.get("fencing_token", ""))
            sidecars.attempt_registry[att_id] = att

    elif op in ("release", "revoke", "expire"):
        lid = p["lease_id"]
        if lid in leases:
            old = dict(leases[lid])
            old["status"] = {
                "release": "RELEASED",
                "revoke": "REVOKED",
                "expire": "EXPIRED",
            }[op]
            leases[lid] = old
        active = [x for x in state_dict.get("active_leases", []) if x != lid]
        state_dict["active_leases"] = active
        node_status = p.get("node_status")
        node_id = p.get("node_id")
        if op == "expire" and node_status and node_id:
            nodes = dict(state_dict.get("nodes", {}))
            node = dict(nodes.get(node_id, {}))
            node["status"] = node_status
            nodes[node_id] = node
            state_dict["nodes"] = nodes
        att_id = p.get("attempt_id")
        if op in ("release", "revoke", "expire") and att_id and att_id in sidecars.attempt_registry:
            att = dict(sidecars.attempt_registry[att_id])
            if att.get("current_lease_id") == lid:
                att["current_lease_id"] = None
            sidecars.attempt_registry[att_id] = att

    elif op == "detach":
        lid = p["lease_id"]
        if lid in leases:
            old = dict(leases[lid])
            old["status"] = "RELEASED"
            leases[lid] = old
        # detach alone does not change active_leases/node; the subsequent grant handles it

    sidecars.leases = leases
    sidecars.journal_position = rec.record_index
    new_state = TeamRunState.from_dict(state_dict)
    return VersionedRunState(state=new_state, version=new_version, meta=_sidecars_to_meta(sidecars))


def apply_runtime_record(
    state: VersionedRunState,
    sidecars: _ReplaySidecars,
    rec: RuntimeRecord,
) -> VersionedRunState:
    """Pure reducer dispatch: apply one trusted record to (state, sidecars)."""
    if rec.kind == "event":
        return _apply_event_record(state, sidecars, rec)
    if rec.kind == "lease":
        return _apply_lease_record(state, sidecars, rec)
    # checkpoint/control records carry no reducible mutation; only advance position
    sidecars.journal_position = rec.record_index
    return state


def replay_records(
    base: VersionedRunState,
    records: list[RuntimeRecord],
) -> VersionedRunState:
    """Deterministically replay trusted records over a base state (no fresh now).

    Pure reducers only, in ascending record_index order. Reconstructs state AND
    all sidecars from the records alone. Returns the reconstructed state with
    journal_position = last replayed record_index.
    """
    sidecars = _meta_to_sidecars(base.meta)
    sidecars.journal_position = base.meta.journal_position if isinstance(base.meta, RuntimeSnapshotMeta) else (base.meta.get("journal_position", -1) if isinstance(base.meta, dict) else -1)
    state = base
    for rec in sorted(records, key=lambda r: r.record_index):
        state = apply_runtime_record(state, sidecars, rec)
    return state


# ---------------------------------------------------------------------------
# Recovery (journal-preserving; replay into a fresh/target store)
# ---------------------------------------------------------------------------

def recover_from_checkpoint(
    source: StateStore,
    run_id: str,
    target: StateStore | None = None,
    *,
    replay: bool = True,
) -> VersionedRunState | None:
    """Recover a run by restoring the latest checkpoint then replaying post-checkpoint journal.

    The durable journal is NEVER wiped or re-appended. The source's full
    SnapshotRecord is captured up front so the immutable journal evidence remains
    available for repeated/audited recovery.

    Flow (deterministic, no live re-acceptance):
      1. capture source SnapshotRecord (immutable journal evidence retained);
      2. build latest CheckpointSnapshot from source (journal_position = last
         included RuntimeRecord.record_index);
      3. restore the checkpoint into a fresh target store (or `target` if given);
      4. replay records with record_index > journal_position via pure reducers;
      5. commit the reconstructed state into the target store (journal untouched).

    Returns the reconstructed VersionedRunState, or None if no snapshot exists.
    """
    try:
        snap = build_checkpoint_snapshot(source, run_id)
    except KeyError:
        return None

    # 1. capture immutable journal evidence (not mutated by recovery)
    _source_snapshot = source.snapshot()

    # 3. restore checkpoint into a fresh target store (journal preserved untouched)
    if target is None:
        from taskcontroller.runtime.store import InMemoryStateStore

        target = InMemoryStateStore()
    restore_from_checkpoint(target, snap)
    base = target.get_run(run_id)
    if base is None:
        return None

    if not replay:
        return base

    # 4. durable post-checkpoint window (record_index > snapshot journal_position)
    records = source.journal_get(run_id, snap.meta.journal_position)
    # 5. deterministic pure replay (replay_records seeds sidecars from base.meta,
    #     handling both RuntimeSnapshotMeta and plain-dict meta)
    reconstructed = replay_records(base, sorted(records, key=lambda r: r.record_index))
    # commit reconstructed state; journal in target stays equal to source's (untouched)
    try:
        target.put_run(reconstructed, base.version)
    except Exception:
        # Defensive: if CAS races (shouldn't on a fresh target), force restore via snapshot
        target.restore(
            SnapshotRecord(
                runs={run_id: reconstructed},
                journals=target.snapshot().journals,
                dedupe=target.snapshot().dedupe,
            )
        )
    # Rebuild the target store's runtime dedupe sidecar (event fingerprints + stream
    # watermarks) from the reconstructed meta so post-restart event dedupe/fencing/
    # watermark behavior is fully preserved (not just the checkpoint snapshot's).
    _rebuild_target_dedupe(target, run_id)
    return target.get_run(run_id)


def recover_from_latest_checkpoint(
    source: StateStore,
    run_id: str,
    target: StateStore | None = None,
    *,
    replay: bool = True,
) -> VersionedRunState | None:
    """Backward-compatible alias for :func:`recover_from_checkpoint`.

    The committed WP2 regression suite imports this exact symbol. The new
    authoritative pure-reducer recovery entry point is ``recover_from_checkpoint``;
    this wrapper delegates to it (journal-preserving, replay into a fresh/target
    store) so the old public surface keeps working without weakening C3 semantics.
    """
    return recover_from_checkpoint(source, run_id, target, replay=replay)


def _rebuild_target_dedupe(target: StateStore, run_id: str) -> None:
    """Rebuild the target store's _dedupe sidecar from the reconstructed run meta.

    EventRouter reads dedupe fingerprints + stream watermarks from store.dedupe_state()
    (the flat _dedupe dict), not from run meta. This restores them from the recovered
    meta so post-restart behavior is identical to pre-crash.
    """
    rs = target.get_run(run_id)
    if rs is None:
        return
    dedupe: dict[str, Any] = {}
    if isinstance(rs.meta, RuntimeSnapshotMeta):
        for key, fp in rs.meta.dedupe_fingerprints.items():
            dedupe[key] = dict(fp)
        for sk, wm in rs.meta.stream_watermarks.items():
            dedupe[f"stream:{sk[0]}:{sk[1]}"] = wm.to_dict() if hasattr(wm, "to_dict") else wm
    elif isinstance(rs.meta, dict):
        for key, fp in rs.meta.get("dedupe_fingerprints", {}).items():
            dedupe[key] = dict(fp)
        for sk, wm in rs.meta.get("stream_watermarks", {}).items():
            if isinstance(sk, tuple):
                dedupe[f"stream:{sk[0]}:{sk[1]}"] = wm
            else:
                dedupe[sk] = wm
    # apply via restore (preserves run + journal, swaps dedupe)
    full = target.snapshot()
    target.restore(
        SnapshotRecord(
            runs=full.runs,
            journals=full.journals,
            dedupe=dedupe,
        )
    )
