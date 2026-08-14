"""WP2 runtime: deterministic journal + crash recovery (NO GWC).

Design invariants:
- Every accepted mutation (event, lease, checkpoint, control) is recorded as a
  RuntimeRecord in an append-only per-run journal.
- record_index is assigned monotonically by the journal.
- After a crash, recovery replays the journal from the last checkpoint to reconstruct
  the current state.
- JournalGet returns records after a given index for incremental replay.
"""

from __future__ import annotations

from taskcontroller.runtime.store import StateStore, RuntimeRecord, SnapshotRecord
from taskcontroller.runtime.runtime_state import VersionedRunState
from taskcontroller.runtime.checkpoint import build_checkpoint_snapshot


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


def recover_from_latest_checkpoint(
    store: StateStore,
    run_id: str,
) -> VersionedRunState | None:
    """Recover a run's state by restoring the latest checkpoint snapshot.

    MVP: restores from a single CheckpointSnapshot (no incremental replay yet).
    Returns the reconstructed VersionedRunState, or None if no snapshot exists.
    """
    try:
        snap = build_checkpoint_snapshot(store, run_id)
    except KeyError:
        return None
    # restore into a fresh store and return the reconstructed state
    from taskcontroller.runtime.checkpoint import restore_from_checkpoint
    restore_from_checkpoint(store, snap)
    return store.get_run(run_id)
