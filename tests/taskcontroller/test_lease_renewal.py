"""TC-MBX-802: bounded lease renewal and stale-heartbeat fencing."""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.ids import ProviderRef
from taskcontroller.domain.models import TeamRunState, WorkLease
from taskcontroller.domain.values import NodeState
from taskcontroller.runtime.errors import LeaseConflictError
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
    make_attempt_record,
)
from taskcontroller.runtime.store import InMemoryStateStore


_NOW = "2026-09-12T13:00:00Z"
_GRANT = "2026-09-12T12:00:00Z"
_CURRENT_EXPIRY = "2026-09-12T14:00:00Z"
_EXPIRED = "2026-09-12T12:30:00Z"
_FENCE = "fence-802"
_ATTEMPT = "attempt-802"


def _lease(*, expires_at: str = _CURRENT_EXPIRY, status: str = LeaseStatus.ACTIVE.value) -> WorkLease:
    return WorkLease(
        lease_id="lease-802",
        run_id="run-802",
        node_id="node-802",
        execution_id="execution-802",
        attempt_id=_ATTEMPT,
        holder=ProviderRef("hermes-mac"),
        fencing_token=_FENCE,
        granted_at=_GRANT,
        expires_at=expires_at,
        status=status,
    )


def _seed(lease: WorkLease) -> tuple[LeaseManager, InMemoryStateStore, VersionedRunState]:
    state = VersionedRunState(
        state=TeamRunState(
            run_id="run-802",
            status=RunStatus.RUNNING.value,
            nodes={
                "node-802": NodeState(
                    status=NodeStatus.RUNNING.value,
                    contract_ref="contract-802",
                    current_attempt=1,
                    lease_ref=lease.lease_id,
                    artifact_refs=[],
                )
            },
            active_attempts=[_ATTEMPT],
            active_leases=[lease.lease_id],
        ),
        version=1,
        meta=RuntimeSnapshotMeta(
            attempt_registry={
                _ATTEMPT: make_attempt_record(
                    _ATTEMPT,
                    "run-802",
                    "node-802",
                    "execution-802",
                    _FENCE,
                    1,
                    current_lease_id=lease.lease_id,
                )
            },
            leases=RuntimeLeaseState(leases={lease.lease_id: lease}),
            stream_watermarks={},
            event_cursor=None,
            dedupe_fingerprints={},
            journal_position=0,
        ),
    )
    store = InMemoryStateStore()
    store.put_run(state, -1)
    current = store.get_run("run-802")
    assert current is not None
    return LeaseManager(store), store, current


def _journal_indexes(store: InMemoryStateStore) -> list[int]:
    return [record.record_index for record in store.journal_get("run-802", -1)]


def _stored(store: InMemoryStateStore) -> VersionedRunState:
    current = store.get_run("run-802")
    assert current is not None
    return current


def _stored_lease(store: InMemoryStateStore) -> WorkLease:
    meta = _stored(store).meta
    assert isinstance(meta, RuntimeSnapshotMeta)
    return meta.leases.leases["lease-802"]


def test_expired_active_lease_rejects_future_stale_heartbeat_without_mutation() -> None:
    manager, store, current = _seed(_lease(expires_at=_EXPIRED))
    before = _stored(store)
    before_journal = _journal_indexes(store)
    before_lease = before.meta.leases.leases["lease-802"].to_dict()

    with pytest.raises(LeaseConflictError, match="cannot renew expired"):
        manager.renew(
            "lease-802",
            new_expires_at="2026-09-12T16:00:00Z",
            fencing_token=_FENCE,
            expected_version=current.version,
            current_state=current,
            now=_NOW,
        )

    after = _stored(store)
    assert after.version == before.version
    assert _journal_indexes(store) == before_journal
    assert after.meta.leases.leases["lease-802"].to_dict() == before_lease
    assert manager.current(
        "run-802", "node-802", "execution-802", _ATTEMPT, now=_NOW
    ) is None


def test_stale_heartbeat_cannot_shorten_an_active_lease() -> None:
    manager, store, current = _seed(_lease())
    before = _stored(store)
    before_journal = _journal_indexes(store)

    with pytest.raises(LeaseConflictError, match="cannot shorten"):
        manager.renew(
            "lease-802",
            new_expires_at="2026-09-12T13:30:00Z",
            fencing_token=_FENCE,
            expected_version=current.version,
            current_state=current,
            now=_NOW,
        )

    after = _stored(store)
    assert after.version == before.version
    assert _journal_indexes(store) == before_journal
    assert after.meta.leases.leases["lease-802"].expires_at == _CURRENT_EXPIRY


def test_matching_heartbeat_extends_active_lease_and_journals_once() -> None:
    manager, store, current = _seed(_lease())
    before_journal = _journal_indexes(store)

    updated = manager.renew(
        "lease-802",
        new_expires_at="2026-09-12T16:00:00Z",
        fencing_token=_FENCE,
        expected_version=current.version,
        current_state=current,
        now=_NOW,
    )

    assert updated.version == current.version + 1
    renewed = _stored_lease(store)
    assert renewed.status == LeaseStatus.ACTIVE.value
    assert renewed.expires_at == "2026-09-12T16:00:00Z"
    expected_index = before_journal[-1] + 1 if before_journal else 0
    assert _journal_indexes(store) == before_journal + [expected_index]


def test_expired_status_rejects_late_heartbeat_even_with_future_expiry() -> None:
    manager, store, current = _seed(_lease(status=LeaseStatus.EXPIRED.value))
    before = _stored(store)
    before_journal = _journal_indexes(store)

    with pytest.raises(LeaseConflictError, match="cannot renew non-ACTIVE"):
        manager.renew(
            "lease-802",
            new_expires_at="2026-09-12T16:00:00Z",
            fencing_token=_FENCE,
            expected_version=current.version,
            current_state=current,
            now=_NOW,
        )

    after = _stored(store)
    assert after.version == before.version
    assert _journal_indexes(store) == before_journal
