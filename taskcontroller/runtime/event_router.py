"""WP2 runtime event routing: canonical dedupe fingerprint, strict sequence, correlation/fencing, reducer authority (NO GWC).

Design invariants:
- Each accepted AgentEvent is correlated to (run_id, node_id, execution_id, attempt_id).
- Producer sequence is tracked per (execution_id, attempt_id) via StreamWatermark;
  strict next-sequence rule (first 0, thereafter exactly expected_seq, no gaps).
- Idempotency: identical canonical fingerprint => true NO-OP (no state/version/cursor/watermark
  mutation). Same event_id/idempotency_key with different canonical fingerprint => EventRejected.
- Fingerprint covers canonical event content, not only event_id/idempotency_key.
- Correlation/fencing: event must match current AttemptRecord + current ACTIVE lease + exact
  fencing token; missing/non-current/replaced => fail closed before mutation.
- Reducer authority: only explicit event semantics through WP1 transitions.
  Executor COMPLETED => at most RUNNING -> REVIEWING, never DONE.
  STATUS_CHANGE cannot payload-drive arbitrary state/DONE.
  Executor CANCELLED cannot cancel whole run.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.domain.enums import EventType, NodeStatus, RunStatus
from taskcontroller.domain.models import AgentEvent, TeamRunState
from taskcontroller.domain.values import EventCursor, NodeState
from taskcontroller.kernel.errors import TransitionRejected
from taskcontroller.runtime.errors import EventRejected, ConcurrentStateError
from taskcontroller.runtime.runtime_state import (
    AttemptRecord,
    StreamWatermark,
    VersionedRunState,
    make_attempt_record,
)
from taskcontroller.runtime.store import StateStore, RuntimeRecord

_EventFingerprint = dict[str, Any]


def _make_canonical_fingerprint(event: AgentEvent) -> _EventFingerprint:
    """Stable canonical fingerprint covering full event content.

    Covers: event_id, idempotency_key, run_id, node_id, execution_id, attempt_id,
    fencing_token, sequence, event_type, timestamp, payload, artifact_refs.
    """
    fp: _EventFingerprint = {
        "event_id": event.event_id,
        "run_id": event.run_id,
        "node_id": event.node_id,
        "execution_id": event.execution_id,
        "attempt_id": event.attempt_id,
        "fencing_token": event.fencing_token,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "producer": event.producer.to_dict(),
    }
    if event.idempotency_key is not None:
        fp["idempotency_key"] = event.idempotency_key
    if event.payload is not None:
        fp["payload"] = event.payload
    fp["artifact_refs"] = [a.to_dict() for a in event.artifact_refs]
    return fp


def _make_event_fingerprint(event: AgentEvent) -> _EventFingerprint:
    """Backward-compatible alias for the canonical fingerprint (committed WP2 contract).

    The committed regression suite imports this exact symbol and expects a
    fingerprint containing at least ``event_id`` and ``idempotency_key``. The new
    authoritative implementation is :func:`_make_canonical_fingerprint`; this wrapper
    preserves the prior public surface without weakening C1 semantics.
    """
    return _make_canonical_fingerprint(event)


def _dedupe_key(event: AgentEvent) -> str:
    """Backward-compatible single-key dedupe lookup (committed WP2 contract).

    Prior contract: returns the event's primary dedupe key (event_id). The new
    multi-key path is :func:`_dedupe_keys` (event_id + idem:<idempotency_key>);
    this wrapper preserves the prior single-key surface for committed callers.
    """
    return event.event_id


def _dedupe_keys(event: AgentEvent) -> list[str]:
    """Return all dedupe lookup keys for an event (primary + secondary)."""
    keys = [event.event_id]
    if event.idempotency_key is not None:
        keys.append(f"idem:{event.idempotency_key}")
    return keys


class EventRouter:
    """Routes accepted AgentEvents into the runtime store under CAS + dedupe.

    Public contract:
    - route() accepts a validated AgentEvent + current VersionedRunState + store,
      checks dedupe (no-op vs conflict), correlation/fencing, sequence, applies
      the mutation via reducer authority, records journal + dedupe.
    - All public methods are stateless; store + dedupe state live in StateStore.
    """

    def __init__(self, store: StateStore) -> None:
        self._store = store

    def _jp_now(self, run_id: str) -> int:
        """Authoritative journal_position = highest durable record_index.

        Delegates to the store's last_record_index (last RuntimeRecord.record_index,
        N-1, or -1 when empty). Sole authority is the durable journal, NEVER version.
        """
        return self._store.last_record_index(run_id)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def route(
        self,
        event: AgentEvent,
        current_state: VersionedRunState,
        expected_version: int,
    ) -> VersionedRunState:
        """Accept one AgentEvent, apply to store under CAS, return new state.

        Returns current_state unchanged (no-op) when an identical canonical
        fingerprint was already accepted.

        Raises:
            EventRejected: dedupe conflict, correlation/fencing failure,
                sequence non-monotonic, or unsupported authority.
            ConcurrentStateError: CAS version mismatch.
        """
        # 1. dedupe: identical fingerprint => no-op; conflicting reuse => reject
        dedupe_state = self._store.dedupe_state()
        fingerprint = _make_canonical_fingerprint(event)
        keys = _dedupe_keys(event)
        for key in keys:
            existing = dedupe_state.get(key)
            if existing is not None:
                if existing == fingerprint:
                    # identical canonical fingerprint => idempotent no-op
                    return current_state
                # same key but different fingerprint => conflict
                raise EventRejected(
                    f"conflicting reuse of {key}: "
                    f"existing fingerprint differs from current event"
                )

        # 2. correlation + fencing validation
        self._validate_correlation_and_fencing(event, current_state)

        # 3. strict sequence (per stream = execution_id, attempt_id)
        stream_key = (event.execution_id, event.attempt_id)
        current_watermark = self._load_stream_watermark(stream_key)
        expected_seq = current_watermark.producer_sequence if current_watermark else 0
        if event.sequence != expected_seq:
            raise EventRejected(
                f"out-of-order sequence for stream {stream_key}: "
                f"got {event.sequence}, expected {expected_seq}"
            )

        # 4. apply via reducer authority (deductible event semantics)
        new_state = self._apply_event_to_state(current_state, event)

        # 5. CAS commit
        try:
            committed = self._store.put_run(new_state, expected_version)
        except ConcurrentStateError:
            raise
        except Exception as exc:
            raise ConcurrentStateError(
                f"CAS failed for run {new_state.state.run_id}: {exc}"
            ) from exc

        # 6. record journal (accepted mutation) — replay-sufficient payload
        new_version = committed.version
        self._store.journal_append(
            event.run_id,
            RuntimeRecord(
                kind="event",
                run_id=event.run_id,
                payload={
                    "event_id": event.event_id,
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "execution_id": event.execution_id,
                    "attempt_id": event.attempt_id,
                    "run_id": event.run_id,
                    "node_id": event.node_id,
                    "fencing_token": event.fencing_token,
                    "version": new_version,
                    "idempotency_key": event.idempotency_key,
                    "timestamp": event.timestamp,
                    "producer": event.producer.to_dict(),
                    "payload": event.payload,
                    "artifact_refs": [a.to_dict() for a in event.artifact_refs],
                    "fingerprint": fingerprint,
                },
            ),
        )

        # 7. dedupe records (both keys)
        for key in keys:
            self._store.dedupe_put(key, fingerprint)

        # 8. update stream watermark (next expected sequence)
        new_watermark = StreamWatermark(
            execution_id=event.execution_id,
            attempt_id=event.attempt_id,
            producer_sequence=event.sequence + 1,
        )
        self._save_stream_watermark(stream_key, new_watermark)

        # journal_position is SOLELY derived from the durable journal record index,
        # never from version. The journal append above assigns record_index = N-1,
        # so sync the stored position to that real value.
        self._store.sync_journal_position(event.run_id, new_version)

        # run-level EventCursor updated inside _apply_event_to_state
        return committed

    # ------------------------------------------------------------------
    # correlation / fencing
    # ------------------------------------------------------------------

    def _validate_correlation_and_fencing(
        self, event: AgentEvent, current_state: VersionedRunState
    ) -> None:
        """Fail closed if event does not correlate to current live attempt + lease.

        Requires:
        - AttemptRecord for (run_id, node_id, execution_id, attempt_id) exists
          and matches exactly.
        - Current ACTIVE lease exists for that quad with exact fencing_token.
        """
        registry = self._attempt_registry(current_state)
        attempt = registry.get(event.attempt_id)
        if attempt is None:
            raise EventRejected(
                f"unknown attempt_id {event.attempt_id} for event {event.event_id}"
            )
        # exact run/node/execution/attempt correlation
        if (
            attempt.run_id != event.run_id
            or attempt.node_id != event.node_id
            or attempt.execution_id != event.execution_id
            or attempt.attempt_id != event.attempt_id
        ):
            raise EventRejected(
                f"event {event.event_id} correlation mismatch: "
                f"event run/node/execution/attempt != current attempt record"
            )

        # require current ACTIVE lease for this quad with exact fencing token
        leases = self._leases_dict(current_state)
        current_lease = self._find_active_lease(
            leases,
            event.run_id,
            event.node_id,
            event.execution_id,
            event.attempt_id,
        )
        if current_lease is None:
            raise EventRejected(
                f"no current ACTIVE lease for {event.run_id}/{event.node_id}/"
                f"{event.execution_id}/{event.attempt_id}; event {event.event_id} rejected"
            )
        if current_lease.fencing_token != event.fencing_token:
            raise EventRejected(
                f"fencing_token mismatch for event {event.event_id}: "
                f"event token does not match current ACTIVE lease token"
            )

    # ------------------------------------------------------------------
    # reducer authority (WP1 transition validation)
    # ------------------------------------------------------------------

    def _apply_event_to_state(
        self, current: VersionedRunState, event: AgentEvent
    ) -> VersionedRunState:
        """Apply explicit event semantics through WP1 transitions.

        - EventType.COMPLETED => at most RUNNING -> REVIEWING, never DONE.
        - EventType.STATUS_CHANGE => cannot payload-drive arbitrary state/DONE.
        - EventType.CANCELLED => cannot cancel whole run; record-only.
        - Other events => record cursor/artifacts only.
        """
        state = current.state
        new_version = current.version + 1

        # clone state via dict round-trip (deep copy)
        new_state_dict = state.to_dict()

        # last_event_cursor always moves forward for accepted events
        new_state_dict["last_event_cursor"] = EventCursor(
            last_event_id=event.event_id,
            sequence=event.sequence,
        ).to_dict()

        # artifact_refs recording (allowed for most event types)
        if event.artifact_refs:
            existing = list(new_state_dict.get("artifact_refs", []))
            for ar in event.artifact_refs:
                a_id = ar.artifact_id if hasattr(ar, "artifact_id") else str(ar)
                if a_id not in existing:
                    existing.append(a_id)
            new_state_dict["artifact_refs"] = existing

        # ---- reducer authority per event_type ----
        event_type = event.event_type
        if event_type == EventType.COMPLETED.value:
            new_state_dict = self._apply_completed(current, event, new_state_dict)
        elif event_type == EventType.STATUS_CHANGE.value:
            new_state_dict = self._apply_status_change(current, event, new_state_dict)
        elif event_type == EventType.CANCELLED.value:
            new_state_dict = self._apply_cancelled(current, new_state_dict)
        # TASK_STARTED / PROGRESS / ARTIFACT_PRODUCED / NEEDS_INPUT /
        # NEEDS_REVIEW / REVIEW_SUBMITTED / FAILED / HEARTBEAT / ESCALATED /
        # CHECKPOINT: record cursor + artifacts only (no state transition here)

        new_ts = TeamRunState.from_dict(new_state_dict)

        # preserve meta as RuntimeSnapshotMeta
        from taskcontroller.runtime.runtime_state import RuntimeSnapshotMeta

        old_meta = current.meta
        # Source of truth for dedupe/fencing/watermark sidecars is the store's flat
        # _dedupe sidecar (what EventRouter reads at runtime). Mirror it into meta so
        # the run meta carries the same sidecars recovery reconstructs — keeping live
        # state byte-equivalent to a recovered state. The stream watermark for THIS
        # event is derived from event.sequence + 1 (matching _save_stream_watermark),
        # since dedupe_save happens after _apply_event_to_state in route().
        from taskcontroller.runtime.runtime_state import StreamWatermark

        store_dedupe = self._store.dedupe_state()
        live_fps = dict(store_dedupe)
        live_wm: dict[Any, Any] = {}
        for key, val in store_dedupe.items():
            if key.startswith("stream:"):
                parts = key.split(":", 2)
                if len(parts) == 3:
                    live_wm[(parts[1], parts[2])] = (
                        StreamWatermark.from_dict(val) if isinstance(val, dict) else val
                    )
        stream_key = (event.execution_id, event.attempt_id)
        live_wm[stream_key] = StreamWatermark(
            execution_id=event.execution_id,
            attempt_id=event.attempt_id,
            producer_sequence=event.sequence + 1,
        )
        for k in _dedupe_keys(event):
            live_fps[k] = _make_canonical_fingerprint(event)
        if isinstance(old_meta, RuntimeSnapshotMeta):
            new_meta = RuntimeSnapshotMeta(
                attempt_registry=old_meta.attempt_registry,
                leases=old_meta.leases,
                stream_watermarks=live_wm,
                event_cursor=EventCursor(
                    last_event_id=event.event_id,
                    sequence=event.sequence,
                ),
                dedupe_fingerprints=live_fps,
                journal_position=self._jp_now(event.run_id),
            )
        else:
            new_meta = dict(old_meta)
            new_meta["event_cursor"] = EventCursor(
                last_event_id=event.event_id,
                sequence=event.sequence,
            ).to_dict()
            new_meta["stream_watermarks"] = {k: (v.to_dict() if hasattr(v, "to_dict") else v) for k, v in live_wm.items()}
            new_meta["dedupe_fingerprints"] = live_fps
            new_meta["journal_position"] = self._jp_now(event.run_id)

        return VersionedRunState(
            state=new_ts,
            version=new_version,
            meta=new_meta,
        )

    # ------------------------------------------------------------------
    # event-specific reducers
    # ------------------------------------------------------------------

    def _apply_completed(
        self, current: VersionedRunState, event: AgentEvent, new_state_dict: dict
    ) -> dict:
        """Executor COMPLETED => node-level REVIEWING transition, run-level
        status unchanged (normally RUNNING).

        Validates via WP1 validate_node_transition(current_node.status, REVIEWING).
        Does NOT introduce ad-hoc markers.
        """
        from taskcontroller.kernel.transitions import validate_node_transition

        state = current.state
        new_state_dict = dict(new_state_dict)
        # Never allow COMPLETED event to directly set run status to DONE
        if new_state_dict.get("status") == NodeStatus.DONE.value:
            new_state_dict["status"] = state.status
        # If run is already terminal, record-only
        if state.status in (RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value):
            return new_state_dict
        # Resolve correlated node and apply node-level REVIEWING transition
        node = state.nodes.get(event.node_id)
        if node is None:
            # unknown node; record-only (cannot transition)
            return new_state_dict
        node_dict = node.to_dict()
        node_dict["status"] = NodeStatus.REVIEWING.value
        validate_node_transition(
            current=node.status,
            target=NodeStatus.REVIEWING.value,
        )
        new_node = NodeState.from_dict(node_dict)
        new_nodes = {k: v.to_dict() for k, v in state.nodes.items()}
        new_nodes[event.node_id] = new_node.to_dict()
        new_state_dict["nodes"] = new_nodes
        return new_state_dict

    def _apply_status_change(
        self, current: VersionedRunState, event: AgentEvent, new_state_dict: dict
    ) -> dict:
        """STATUS_CHANGE applies node-level status transition via WP1 validation.

        Cannot payload-drive arbitrary state or DONE on the run.
        """
        from taskcontroller.kernel.transitions import validate_node_transition

        payload = event.payload or {}
        proposed = payload.get("status")
        if proposed is None:
            return new_state_dict
        if proposed == NodeStatus.DONE.value:
            raise TransitionRejected(
                "STATUS_CHANGE cannot transition to DONE",
                current=current.state.status,
                target=NodeStatus.DONE.value,
            )
        node = current.state.nodes.get(event.node_id)
        if node is None:
            return new_state_dict
        node_dict = node.to_dict()
        node_dict["status"] = proposed
        validate_node_transition(current=node.status, target=proposed)
        new_node = NodeState.from_dict(node_dict)
        new_nodes = {k: v.to_dict() for k, v in current.state.nodes.items()}
        new_nodes[event.node_id] = new_node.to_dict()
        new_state_dict["nodes"] = new_nodes
        return new_state_dict

    def _apply_cancelled(
        self, current: VersionedRunState, new_state_dict: dict
    ) -> dict:
        """Executor CANCELLED must not cancel whole run.

        Record-only: do NOT mutate run status to CANCELLED here.
        """
        # record-only: keep cursor + artifacts, no run-level cancel
        return new_state_dict

    # ------------------------------------------------------------------
    # stream watermarks
    # ------------------------------------------------------------------

    def _load_stream_watermark(self, stream_key: tuple[str, str]) -> StreamWatermark | None:
        """Load stream watermark from store meta (keyed by execution_id:attempt_id)."""
        dedupe_state = self._store.dedupe_state()
        sk = f"stream:{stream_key[0]}:{stream_key[1]}"
        raw = dedupe_state.get(sk)
        if raw is None:
            return None
        return StreamWatermark.from_dict(raw)

    def _save_stream_watermark(
        self, stream_key: tuple[str, str], watermark: StreamWatermark
    ) -> None:
        sk = f"stream:{stream_key[0]}:{stream_key[1]}"
        self._store.dedupe_put(sk, watermark.to_dict())

    # ------------------------------------------------------------------
    # helpers: attempt registry + leases (from VersionedRunState.meta)
    # ------------------------------------------------------------------

    def _attempt_registry(
        self, current_state: VersionedRunState
    ) -> dict[str, AttemptRecord]:
        """Return attempt_id -> AttemptRecord from current meta."""
        from taskcontroller.runtime.runtime_state import RuntimeSnapshotMeta

        meta = current_state.meta
        if isinstance(meta, RuntimeSnapshotMeta):
            return dict(meta.attempt_registry)
        if isinstance(meta, dict):
            reg_raw = meta.get("attempt_registry", {})
            out: dict[str, AttemptRecord] = {}
            for k, v in reg_raw.items():
                if isinstance(v, AttemptRecord):
                    out[k] = v
                elif isinstance(v, dict):
                    out[k] = AttemptRecord.from_dict(v)
            return out
        return {}

    def _leases_dict(self, current_state: VersionedRunState) -> dict[str, Any]:
        """Return lease_id -> lease dict from current meta (for fencing lookup)."""
        from taskcontroller.runtime.runtime_state import RuntimeLeaseState, RuntimeSnapshotMeta
        from taskcontroller.domain.models import WorkLease

        meta = current_state.meta
        leases: dict[str, Any] = {}
        if isinstance(meta, RuntimeSnapshotMeta):
            for lid, lease in meta.leases.leases.items():
                leases[lid] = lease
        elif isinstance(meta, dict):
            leases_raw = meta.get("leases", {})
            if isinstance(leases_raw, RuntimeLeaseState):
                for lid, lease in leases_raw.leases.items():
                    leases[lid] = lease
            elif isinstance(leases_raw, dict):
                for lid, v in leases_raw.items():
                    if isinstance(v, WorkLease):
                        leases[lid] = v
                    elif isinstance(v, dict):
                        leases[lid] = WorkLease.from_dict(v)
        return leases

    def _find_active_lease(
        self,
        leases: dict[str, Any],
        run_id: str,
        node_id: str,
        execution_id: str,
        attempt_id: str,
    ) -> Any:
        """Return the ACTIVE lease for the given quad, or None."""
        for lease in leases.values():
            if (
                hasattr(lease, "run_id")
                and lease.run_id == run_id
                and hasattr(lease, "node_id")
                and lease.node_id == node_id
                and hasattr(lease, "execution_id")
                and lease.execution_id == execution_id
                and hasattr(lease, "attempt_id")
                and lease.attempt_id == attempt_id
                and hasattr(lease, "status")
                and lease.status == "ACTIVE"
            ):
                return lease
        return None
