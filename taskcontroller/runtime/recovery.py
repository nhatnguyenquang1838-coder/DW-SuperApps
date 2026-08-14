"""WP2 runtime recovery helpers (NO GWC).

Deterministic crash recovery: restore from checkpoint + journal replay.

This module is a thin orchestration layer over the pure-reducer recovery
implementation in :mod:`taskcontroller.runtime.journal` (``recover_from_checkpoint`` /
``recover_from_latest_checkpoint``). Those functions preserve the immutable journal
and replay trusted RuntimeRecords through pure reducers (no live EventRouter /
LeaseManager, no fresh clock), using the durable RuntimeRecord.record_index as the
sole journal_position authority.
"""

from __future__ import annotations

from taskcontroller.runtime.store import StateStore
from taskcontroller.runtime.journal import recover_from_latest_checkpoint


def recover_run(
    store: StateStore,
    run_id: str,
) -> object | None:
    """Recover a single run: restore from the latest checkpoint, then replay journal.

    Delegates to the authoritative pure-reducer recovery entry point. The journal
    is never wiped or re-appended; only records with record_index >
    checkpoint.journal_position are replayed.
    """
    return recover_from_latest_checkpoint(store, run_id)
