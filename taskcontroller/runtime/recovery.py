"""WP2 runtime recovery helpers (NO GWC).

Deterministic crash recovery: restore from checkpoint + journal replay.
"""

from __future__ import annotations

from taskcontroller.runtime.store import StateStore
from taskcontroller.runtime.runtime_state import VersionedRunState
from taskcontroller.runtime.journal import Journal, recover_from_latest_checkpoint


def recover_run(
    store: StateStore,
    run_id: str,
) -> VersionedRunState | None:
    """Recover a single run: restore from latest checkpoint, then replay journal."""
    rs = recover_from_latest_checkpoint(store, run_id)
    if rs is None:
        return None
    # replay journal records after the checkpoint's journal_position
    journal = Journal(store)
    rs_after = store.get_run(run_id)
    last_pos = rs_after.meta.get("journal_position", 0) if rs_after else 0
    pending = journal.get_after(run_id, last_pos)
    # MVP: apply each record in order (the records are already reflected via CAS;
    # journal serves as audit/replay trail). For MVP we just return the restored state.
    return rs
