"""WP2 in-memory runtime store with CAS + deep-copy guarantee (NO GWC).

Design invariants:
- sole CAS source = VersionedRunState.version
- every store read/write returns/accepts deep copies so callers cannot
  bypass CAS by mutating aliased objects
- InMemoryStateStore MVP; persistence-neutral StateStore interface declared
  here for future substitution
"""

from __future__ import annotations

import copy
from typing import Any

from taskcontroller.domain.models import TeamRunState, WorkLease
from taskcontroller.kernel.errors import TransitionRejected
from taskcontroller.runtime.errors import ConcurrentStateError, RuntimeError
from taskcontroller.runtime.runtime_state import (
    AttemptRecord,
    PendingMutation,
    VersionedRunState,
    RuntimeSnapshotMeta,
)

_EventFingerprint = dict[str, Any]


def _deep(obj: Any) -> Any:
    return copy.deepcopy(obj)


class StateStore:
    """Persistence-neutral runtime store interface.

    MVP: InMemoryStateStore. Future persistence may substitute without
    changing runtime logic as long as the same CAS + copy semantics hold.
    """

    def get_run(self, run_id: str) -> VersionedRunState | None: ...

    def put_run(self, value: VersionedRunState, expected_version: int) -> VersionedRunState: ...

    def snapshot(self) -> SnapshotRecord: ...

    def restore(self, snapshot: SnapshotRecord) -> None: ...

    def journal_append(self, run_id: str, record: "RuntimeRecord") -> None: ...

    def journal_get(self, run_id: str, after_index: int) -> list["RuntimeRecord"]: ...

    def last_record_index(self, run_id: str) -> int:
        """Highest durable record_index for run_id, or -1 if empty. Sole journal_position authority."""
        ...

    def sync_journal_position(self, run_id: str, expected_version: int) -> None: ...


    def dedupe_state(self) -> dict[str, _EventFingerprint]: ...

    def dedupe_put(self, key: str, fingerprint: _EventFingerprint) -> None: ...


class RuntimeRecord:
    """Append-only per-run journal record for accepted event + lease/control mutations.

    record_index is assigned by the journal (monotonic per run).
    """

    def __init__(self, kind: str, run_id: str, payload: dict) -> None:
        self.kind = kind
        self.run_id = run_id
        self.payload = payload
        self.record_index = -1  # assigned by journal


class InMemoryStateStore(StateStore):
    """MVP: single-process in-memory store.

    - run_id -> VersionedRunState
    - per-run journal (list of RuntimeRecord)
    - dedupe fingerprints: key -> fingerprint (for event_id / idempotency)
    """

    def __init__(self) -> None:
        self._runs: dict[str, VersionedRunState] = {}
        self._journals: dict[str, list[RuntimeRecord]] = {}
        self._dedupe: dict[str, _EventFingerprint] = {}

    def get_run(self, run_id: str) -> VersionedRunState | None:
        v = self._runs.get(run_id)
        if v is None:
            return None
        return _deep(v)

    def put_run(self, value: VersionedRunState, expected_version: int) -> VersionedRunState:
        cur = self._runs.get(value.state.run_id)
        cur_version = cur.version if cur is not None else -1
        if cur_version != expected_version:
            raise ConcurrentStateError(
                f"CAS mismatch for run {value.state.run_id}: "
                f"expected {expected_version}, current {cur_version}"
            )
        if cur is None:
            self._runs[value.state.run_id] = _deep(value)
        else:
            self._runs[value.state.run_id] = _deep(value)
        return _deep(value)

    def snapshot(self) -> SnapshotRecord:
        runs_deep = {rid: _deep(v) for rid, v in self._runs.items()}
        journals_deep = {
            rid: list(_deep(recs)) for rid, recs in self._journals.items()
        }
        dedupe_deep = dict(self._dedupe)
        return SnapshotRecord(
            runs=runs_deep,
            journals=journals_deep,
            dedupe=dedupe_deep,
        )

    def restore(self, snapshot: SnapshotRecord) -> None:
        self._runs = {rid: _deep(v) for rid, v in snapshot.runs.items()}
        self._journals = {
            rid: list(_deep(recs)) for rid, recs in snapshot.journals.items()
        }
        self._dedupe = dict(snapshot.dedupe)

    def journal_append(self, run_id: str, record: RuntimeRecord) -> None:
        recs = self._journals.setdefault(run_id, [])
        record.record_index = len(recs)
        recs.append(_deep(record))

    def journal_get(self, run_id: str, after_index: int) -> list["RuntimeRecord"]:
        recs = self._journals.get(run_id, [])
        return [_deep(r) for r in recs if r.record_index > after_index]

    def last_record_index(self, run_id: str) -> int:
        """Sole authority for journal_position: the highest durable record_index.

        Returns -1 when the journal is empty. This is NEVER derived from the
        run/state version — version and record count are independent dimensions.
        """
        recs = self._journals.get(run_id, [])
        if not recs:
            return -1
        return max(r.record_index for r in recs)

    def sync_journal_position(self, run_id: str, expected_version: int) -> None:
        """Make the stored run meta.journal_position equal the durable last record_index.

        This is the ONLY sanctioned place that writes journal_position from the
        actual journal. It is a no-op when the run/record disagree on CAS or the
        position already matches, so it is safe to call after any committed mutation.
        The correction mandates: journal_position derives from RuntimeRecord.record_index,
        never from VersionedRunState.version.

        CAS guard (E): if ``expected_version`` does not match the current stored run
        version, the sync is a STALE write attempt and is rejected with
        ConcurrentStateError rather than mutating a newer run. No stale sync may
        silently overwrite a newer run's journal_position.
        """
        rs = self._runs.get(run_id)
        if rs is None:
            return
        if rs.version != expected_version:
            raise ConcurrentStateError(
                f"stale sync_journal_position for run {run_id}: "
                f"expected {expected_version}, current {rs.version}"
            )
        real = self.last_record_index(run_id)
        cur = getattr(rs.meta, "journal_position", None)
        if isinstance(cur, int) and cur == real:
            return
        if isinstance(rs.meta, RuntimeSnapshotMeta):
            new_meta = RuntimeSnapshotMeta(
                attempt_registry=rs.meta.attempt_registry,
                leases=rs.meta.leases,
                stream_watermarks=rs.meta.stream_watermarks,
                event_cursor=rs.meta.event_cursor,
                dedupe_fingerprints=rs.meta.dedupe_fingerprints,
                journal_position=real,
            )
        elif isinstance(rs.meta, dict):
            new_meta = dict(rs.meta)
            new_meta["journal_position"] = real
        else:
            return
        self._runs[run_id] = VersionedRunState(
            state=rs.state, version=rs.version, meta=new_meta
        )

    def dedupe_state(self) -> dict[str, _EventFingerprint]:
        return dict(self._dedupe)

    def dedupe_put(self, key: str, fingerprint: _EventFingerprint) -> None:
        self._dedupe[key] = dict(fingerprint)


class SnapshotRecord:
    """Checkpoint snapshot data sidecar.

    Contains deep-copied TeamRunState (inside VersionedRunState), version,
    attempt registry, leases, dedupe fingerprints, per-stream watermarks,
    event cursor, and journal position — enough to reconstruct without chat.
    """

    def __init__(
        self,
        runs: dict[str, VersionedRunState],
        journals: dict[str, list[RuntimeRecord]],
        dedupe: dict[str, _EventFingerprint],
    ) -> None:
        self.runs = runs
        self.journals = journals
        self.dedupe = dedupe


class SnapshotBuilder:
    """Builds a SnapshotRecord from the current in-memory store."""

    def __init__(self, store: InMemoryStateStore) -> None:
        self._store = store

    def build(self) -> SnapshotRecord:
        return self._store.snapshot()


def _apply_pending(store: StateStore, pending: PendingMutation) -> VersionedRunState:
    """Apply a validated pending mutation under CAS."""
    new_state = pending.new_state
    store.put_run(new_state, pending.expected_version)
    return store.get_run(new_state.state.run_id)


def apply_event(store: StateStore, run_id: str, expected_version: int, new_state: VersionedRunState) -> VersionedRunState:
    """CAS apply an event-applied state mutation."""
    return store.put_run(new_state, expected_version)
