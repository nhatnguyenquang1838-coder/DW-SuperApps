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

from taskcontroller.kernel.errors import TransitionRejected
from taskcontroller.runtime.errors import ConcurrentStateError, RuntimeError
from taskcontroller.runtime.runtime_state import (
    AttemptRecord,
    PendingMutation,
    VersionedRunState,
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

    def journal_get(self, run_id: str, after_index: int) -> list[RuntimeRecord]:
        recs = self._journals.get(run_id, [])
        return [_deep(r) for r in recs if r.record_index > after_index]

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
