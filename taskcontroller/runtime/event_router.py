"""WP2 runtime event routing: sequence check, dedupe fingerprint, stream watermark, CAS apply (NO GWC).

Design invariants:
- Each accepted AgentEvent is correlated to (run_id, node_id, execution_id, attempt_id).
- Producer sequence is tracked per (execution_id, attempt_id) via StreamWatermark,
  and is independent of the run-level EventCursor (accepted-event log cursor).
- Idempotency: duplicate event_id or idempotency_key is rejected (EventRejected)
  after the first acceptance is recorded in the dedupe fingerprint store.
- Out-of-order low sequence is rejected; strict monotonic per stream.
- CAS apply under VersionedRunState.version; stale version raises ConcurrentStateError.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.domain.models import AgentEvent, TeamRunState
from taskcontroller.domain.values import EventCursor
from taskcontroller.runtime.errors import EventRejected, ConcurrentStateError
from taskcontroller.runtime.runtime_state import (
    AttemptRecord,
    StreamWatermark,
    VersionedRunState,
    make_attempt_record,
)
from taskcontroller.runtime.store import StateStore, RuntimeRecord

_EventFingerprint = dict[str, Any]


def _make_event_fingerprint(event: AgentEvent) -> _EventFingerprint:
    """Stable fingerprint for dedupe: event_id + idempotency_key (if any)."""
    fp: _EventFingerprint = {"event_id": event.event_id}
    if event.idempotency_key is not None:
        fp["idempotency_key"] = event.idempotency_key
    return fp


def _dedupe_key(event: AgentEvent) -> str:
    """Primary dedupe key: event_id. Secondary: idempotency_key when present."""
    return event.event_id


class EventRouter:
    """Routes accepted AgentEvents into the runtime store under CAS + dedupe.

    Public contract:
    - route() accepts a validated AgentEvent + current VersionedRunState + store,
      checks dedupe, sequence, applies the mutation, records journal + dedupe.
    - All public methods are stateless; store + dedupe state live in StateStore.
    """

    def __init__(self, store: StateStore) -> None:
        self._store = store

    def route(
        self,
        event: AgentEvent,
        current_state: VersionedRunState,
        expected_version: int,
    ) -> VersionedRunState:
        """Accept one AgentEvent, apply to store under CAS, return new state.

        Raises:
            EventRejected: dedupe hit, sequence non-monotonic, or event capped.
            ConcurrentStateError: CAS version mismatch.
        """
        # dedupe check (idempotency)
        dedupe_state = self._store.dedupe_state()
        primary_key = _dedupe_key(event)
        if primary_key in dedupe_state:
            raise EventRejected(
                f"duplicate event_id {event.event_id}; already accepted"
            )
        # secondary dedupe via idempotency_key when present
        if event.idempotency_key is not None:
            for existing_fp in dedupe_state.values():
                if existing_fp.get("idempotency_key") == event.idempotency_key:
                    raise EventRejected(
                        f"duplicate idempotency_key {event.idempotency_key}"
                    )

        # sequence check per (execution_id, attempt_id) stream
        stream_key = (event.execution_id, event.attempt_id)
        current_watermark = self._load_stream_watermark(stream_key)
        expected_seq = current_watermark.producer_sequence if current_watermark else 0
        if event.sequence < expected_seq:
            raise EventRejected(
                f"out-of-order sequence for stream {stream_key}: "
                f"got {event.sequence}, expected >= {expected_seq}"
            )
        # gap allowed? MVP: allow any sequence >= expected_seq (no gap enforcement)
        # Tighten later if required by contract; currently: >= is sufficient.

        # build new state from current_state + event application
        new_state = self._apply_event_to_state(current_state, event)

        # CAS commit
        try:
            committed = self._store.put_run(new_state, expected_version)
        except ConcurrentStateError:
            raise
        except Exception as exc:
            raise ConcurrentStateError(
                f"CAS failed for run {new_state.state.run_id}: {exc}"
            ) from exc

        # record journal
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
                },
            ),
        )

        # dedupe record
        self._store.dedupe_put(primary_key, _make_event_fingerprint(event))
        # also record idempotency_key as a separate dedupe entry if present
        if event.idempotency_key is not None:
            self._store.dedupe_put(f"idem:{event.idempotency_key}", {
                "idempotency_key": event.idempotency_key,
                "event_id": event.event_id,
            })

        # update stream watermark
        new_watermark = StreamWatermark(
            execution_id=event.execution_id,
            attempt_id=event.attempt_id,
            producer_sequence=event.sequence + 1,
        )
        self._save_stream_watermark(stream_key, new_watermark)

        # update event cursor: already set in _apply_event_to_state; no mutation needed.
        return committed

    def _load_stream_watermark(self, stream_key: tuple[str, str]) -> StreamWatermark | None:
        """Load stream watermark from store meta (MVP: in-memory via snapshot dedupe)."""
        # Stream watermarks are stored in RuntimeSnapshotMeta; MVP: keep in dedupe state
        # under key "stream:<execution_id>:<attempt_id>"
        dedupe_state = self._store.dedupe_state()
        sk = f"stream:{stream_key[0]}:{stream_key[1]}"
        raw = dedupe_state.get(sk)
        if raw is None:
            return None
        return StreamWatermark.from_dict(raw)

    def _save_stream_watermark(self, stream_key: tuple[str, str], watermark: StreamWatermark) -> None:
        sk = f"stream:{stream_key[0]}:{stream_key[1]}"
        self._store.dedupe_put(sk, watermark.to_dict())

    def _apply_event_to_state(self, current: VersionedRunState, event: AgentEvent) -> VersionedRunState:
        """Apply event payload to TeamRunState (WP0 schema) + bump version.

        This is the deterministic event→state transition function.
        MVP: record event in TeamRunState.artifact_refs / last_event_cursor.
        """
        state = current.state
        # bump version
        new_version = current.version + 1
        # clone state via from_dict/to_dict round-trip to get a fresh copy
        new_state_dict = state.to_dict()
        # update last_event_cursor
        new_state_dict["last_event_cursor"] = EventCursor(
            last_event_id=event.event_id,
            sequence=event.sequence,
        ).to_dict()
        # record artifact_refs from event
        if event.artifact_refs:
            existing = set(new_state_dict.get("artifact_refs", []))
            for ar in event.artifact_refs:
                existing.add(ar.artifact_id if hasattr(ar, "artifact_id") else str(ar))
            new_state_dict["artifact_refs"] = list(existing)
        new_ts = TeamRunState.from_dict(new_state_dict)
        # preserve meta as RuntimeSnapshotMeta, update event_cursor
        from taskcontroller.runtime.runtime_state import RuntimeSnapshotMeta
        old_meta = current.meta
        if isinstance(old_meta, RuntimeSnapshotMeta):
            new_meta = RuntimeSnapshotMeta(
                attempt_registry=old_meta.attempt_registry,
                leases=old_meta.leases,
                stream_watermarks=old_meta.stream_watermarks,
                event_cursor=EventCursor(
                    last_event_id=event.event_id,
                    sequence=event.sequence,
                ),
                dedupe_fingerprints=old_meta.dedupe_fingerprints,
                journal_position=old_meta.journal_position,
            )
        else:
            new_meta = dict(old_meta)
            new_meta["event_cursor"] = EventCursor(
                last_event_id=event.event_id,
                sequence=event.sequence,
            ).to_dict()
        return VersionedRunState(
            state=new_ts,
            version=new_version,
            meta=new_meta,
        )
