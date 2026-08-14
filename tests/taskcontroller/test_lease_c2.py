"""WP2 C2 focused tests for Lease + Attempt lifecycle.

Covers:
- grant with explicit now, detach existing ACTIVE lease, update AttemptRecord
  current_lease_id + fencing_token, node.lease_ref, run.active_leases
- current() returns ACTIVE non-expired lease for correct quad
- renew with fencing token match
- revoke() of ACTIVE lease
- expire() of current ACTIVE lease -> LEASE_EXPIRED node transition (WP1),
  valid WP1 transition, update AttemptRecord + node
- old lease operations cannot detach/replace current lease
- lease operations must go through CAS (version bump)
- journal records appended for accepted lease mutations
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import EventType, LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.ids import ProviderRef
from taskcontroller.domain.models import AgentEvent, TeamRunState, WorkLease
from taskcontroller.domain.values import EventCursor, NodeState
from taskcontroller.kernel.errors import TransitionRejected
from taskcontroller.runtime.errors import ConcurrentStateError, LeaseConflictError
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.runtime_state import (
    AttemptRecord,
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    StreamWatermark,
    VersionedRunState,
    make_attempt_record,
    make_versioned_run,
)
from taskcontroller.runtime.store import InMemoryStateStore

_FENCE = "fence.1"
_NOW = "2026-08-14T10:00:00Z"
_EXPIRES = "2026-08-14T11:00:00Z"
_EXPIRED = "2026-08-14T09:00:00Z"


def _make_lease(
    lease_id: str = "lease.1",
    status: str = LeaseStatus.ACTIVE.value,
    expires_at: str = _EXPIRES,
    fencing_token: str = _FENCE,
    holder: ProviderRef | None = None,
) -> WorkLease:
    if holder is None:
        holder = ProviderRef(provider_id="provider.1")
    return WorkLease(
        lease_id=lease_id,
        run_id="run.1",
        node_id="n1",
        execution_id="exec.1",
        attempt_id="att.1",
        holder=holder,
        fencing_token=fencing_token,
        granted_at=_NOW,
        expires_at=expires_at,
        status=status,
    )


def _make_state(
    run_status: str = RunStatus.RUNNING.value,
    node_status: str = NodeStatus.RUNNING.value,
    lease: WorkLease | None = None,
) -> VersionedRunState:
    run = TeamRunState(
        run_id="run.1",
        status=run_status,
        nodes={"n1": _make_node_state(node_status, lease.lease_id if lease else None)},
        active_attempts=["att.1"],
        active_leases=[lease.lease_id if lease else "lease.1"],
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={
            "att.1": make_attempt_record(
                attempt_id="att.1",
                run_id="run.1",
                node_id="n1",
                execution_id="exec.1",
                fencing_token=_FENCE,
                current_attempt_number=1,
                current_lease_id=lease.lease_id if lease else None,
            )
        },
        leases=RuntimeLeaseState(leases={lease.lease_id: lease} if lease else {}),
        stream_watermarks={},
        event_cursor=None,
        dedupe_fingerprints={},
        journal_position=0,
    )
    return VersionedRunState(state=run, version=1, meta=meta)


def _make_node_state(status: str, lease_ref: str | None = None) -> "NodeState":
    from taskcontroller.domain.values import NodeState

    return NodeState(
        status=status,
        contract_ref="ctr.1",
        current_attempt=1,
        lease_ref=lease_ref,
        artifact_refs=[],
    )


def _make_store() -> InMemoryStateStore:
    return InMemoryStateStore()


def _seed_store(store: InMemoryStateStore) -> VersionedRunState:
    state = _make_state(lease=_make_lease())
    store.put_run(state, -1)
    return state


@pytest.fixture
def lease_mgr():
    return LeaseManager(_make_store())


@pytest.fixture
def seeded():
    store = _make_store()
    state = _seed_store(store)
    return LeaseManager(store), store, state


class TestGrantDetachesExistingActiveLease:
    def test_grant_detaches_existing_active_lease(self, seeded):
        mgr, store, current = seeded
        existing = mgr.current("run.1", "n1", "exec.1", "att.1")
        assert existing is not None
        assert existing.status == LeaseStatus.ACTIVE.value

        new_lease = _make_lease(lease_id="lease.2")
        new_state = mgr.grant(new_lease, current.version, current)
        updated = store.get_run("run.1")

        # existing lease must be RELEASED — inspect via store meta
        existing_updated = updated.meta.leases.leases.get("lease.1")
        assert existing_updated is not None
        assert existing_updated.status == LeaseStatus.RELEASED.value

        # new lease must be ACTIVE
        new = mgr.current("run.1", "n1", "exec.1", "att.1")
        assert new is not None
        assert new.lease_id == "lease.2"
        assert new.status == LeaseStatus.ACTIVE.value

        # version bumped
        assert updated.version == current.version + 2  # detach + register = 2 CAS

    def test_grant_updates_attempt_record_current_lease_and_fencing(self, seeded):
        mgr, store, current = seeded
        new_lease = _make_lease(lease_id="lease.2")
        mgr.grant(new_lease, current.version, current)
        updated = store.get_run("run.1")

        att = updated.meta.attempt_registry["att.1"]
        assert att.current_lease_id == "lease.2"
        assert att.fencing_token == new_lease.fencing_token

    def test_grant_updates_node_lease_ref_and_run_active_leases(self, seeded):
        mgr, store, current = seeded
        new_lease = _make_lease(lease_id="lease.2")
        mgr.grant(new_lease, current.version, current)
        updated = store.get_run("run.1")

        node = updated.state.nodes["n1"]
        assert node.lease_ref == "lease.2"
        assert "lease.2" in updated.state.active_leases
        assert "lease.1" not in updated.state.active_leases

    def test_grant_with_no_existing_active_lease(self):
        store = _make_store()
        state = _make_state(lease=None)
        store.put_run(state, -1)
        mgr = LeaseManager(store)
        new_lease = _make_lease(lease_id="lease.1")
        mgr.grant(new_lease, state.version, state)
        cur = mgr.current("run.1", "n1", "exec.1", "att.1")
        assert cur is not None
        assert cur.lease_id == "lease.1"

    def test_grant_current_returns_latest_version(self, seeded):
        mgr, store, current = seeded
        new_lease = _make_lease(lease_id="lease.2")
        result = mgr.grant(new_lease, current.version, current)
        assert result.version == current.version + 2

    def test_grant_rejects_non_active_lease(self, seeded):
        mgr, store, current = seeded
        new_lease = _make_lease(status=LeaseStatus.RELEASED.value)
        with pytest.raises(LeaseConflictError, match="cannot grant non-ACTIVE"):
            mgr.grant(new_lease, current.version, current)


class TestCurrent:
    def test_current_returns_active_lease_for_correct_quad(self, seeded):
        mgr, store, _ = seeded
        lease = mgr.current("run.1", "n1", "exec.1", "att.1")
        assert lease is not None
        assert lease.status == LeaseStatus.ACTIVE.value

    def test_current_returns_none_for_wrong_quad(self, seeded):
        mgr, store, _ = seeded
        lease = mgr.current("run.1", "n1", "exec.1", "att.999")
        assert lease is None

    def test_current_returns_none_for_nonexistent_run(self, lease_mgr):
        assert lease_mgr.current("run.999", "n1", "exec.1", "att.1") is None

    def test_current_uses_explicit_leases_dict(self, seeded):
        mgr, store, state = seeded
        leases = mgr._leases_dict(state)
        lease = mgr.current("run.1", "n1", "exec.1", "att.1", leases)
        assert lease is not None


class TestRenew:
    def test_renew_extends_expiry_with_matching_fencing(self, seeded):
        mgr, store, current = seeded
        new_expires = _EXPIRES
        updated = mgr.renew("lease.1", new_expires, _FENCE, current.version, current)
        lease = mgr.current("run.1", "n1", "exec.1", "att.1")
        assert lease is not None
        assert lease.expires_at == new_expires
        assert updated.version == current.version + 1

    def test_renew_rejects_wrong_fencing(self, seeded):
        mgr, store, current = seeded
        with pytest.raises(LeaseConflictError, match="fencing_token mismatch"):
            mgr.renew("lease.1", _EXPIRES, "wrong-fence", current.version, current)

    def test_renew_rejects_non_active(self, seeded):
        mgr, store, current = seeded
        mgr.release("lease.1", current.version, current)
        fresh = store.get_run("run.1")
        with pytest.raises(LeaseConflictError, match="cannot renew non-ACTIVE"):
            mgr.renew("lease.1", _EXPIRES, _FENCE, fresh.version, fresh)

    def test_renew_rejects_expired(self, seeded_expired):
        mgr, store, current = seeded_expired
        with pytest.raises(LeaseConflictError, match="cannot renew expired"):
            mgr.renew("lease.1", _EXPIRES, _FENCE, current.version, current)


class TestRelease:
    def test_release_transitions_active_to_released(self, seeded):
        mgr, store, current = seeded
        updated = mgr.release("lease.1", current.version, current)
        lease = mgr.current("run.1", "n1", "exec.1", "att.1")
        assert lease is None
        stale = updated.meta.leases.leases.get("lease.1")
        assert stale is not None
        assert stale.status == LeaseStatus.RELEASED.value
        assert updated.version == current.version + 1

    def test_release_rejects_non_active(self, seeded):
        mgr, store, current = seeded
        mgr.release("lease.1", current.version, current)
        fresh = store.get_run("run.1")
        with pytest.raises(LeaseConflictError, match="cannot release non-ACTIVE"):
            mgr.release("lease.1", fresh.version, fresh)

    def test_release_rejects_expired(self, seeded_expired):
        mgr, store, current = seeded_expired
        with pytest.raises(LeaseConflictError, match="cannot release expired"):
            mgr.release("lease.1", current.version, current)


class TestRevoke:
    def test_revoke_marks_lease_revoked(self, seeded):
        mgr, store, current = seeded
        updated = mgr.revoke("lease.1", current.version, current)
        stale = updated.meta.leases.leases.get("lease.1")
        assert stale is not None
        assert stale.status == LeaseStatus.REVOKED.value
        assert updated.version == current.version + 1

    def test_revoke_rejects_non_active(self, seeded):
        mgr, store, current = seeded
        mgr.revoke("lease.1", current.version, current)
        fresh = store.get_run("run.1")
        with pytest.raises(LeaseConflictError, match="cannot revoke non-ACTIVE"):
            mgr.revoke("lease.1", fresh.version, fresh)


class TestExpire:
    def test_expire_transitions_node_to_lease_expired(self, seeded):
        mgr, store, current = seeded
        updated = mgr.expire("lease.1", current.version, current)
        node = store.get_run("run.1").state.nodes["n1"]
        assert node.status == NodeStatus.LEASE_EXPIRED.value
        assert updated.version == current.version + 1  # expire CAS step only

    def test_expire_updates_attempt_record(self, seeded):
        mgr, store, current = seeded
        mgr.expire("lease.1", current.version, current)
        att = store.get_run("run.1").meta.attempt_registry["att.1"]
        assert att.status == NodeStatus.LEASE_EXPIRED.value

    def test_expire_is_valid_wp1_transition(self, seeded):
        mgr, store, current = seeded
        # validate_node_transition already called inside expire; if it raises, test fails
        mgr.expire("lease.1", current.version, current)

    def test_expire_current_lease_only(self, seeded):
        mgr, store, current = seeded
        # grant a second lease to replace current (lease.1 becomes RELEASED)
        new_lease = _make_lease(lease_id="lease.2")
        mgr.grant(new_lease, current.version, current)
        # the OLD lease.1 is now RELEASED; expiring it must be rejected
        fresh = store.get_run("run.1")
        with pytest.raises(LeaseConflictError, match="cannot expire non-ACTIVE"):
            mgr.expire("lease.1", fresh.version, fresh)
        # expiring the CURRENT lease.2 transitions the node
        fresh2 = store.get_run("run.1")
        mgr.expire("lease.2", fresh2.version, fresh2)
        node = store.get_run("run.1").state.nodes["n1"]
        assert node.status == NodeStatus.LEASE_EXPIRED.value

    def test_expired_lease_current_returns_none(self, seeded_expired):
        mgr, store, current = seeded_expired
        lease = mgr.current("run.1", "n1", "exec.1", "att.1")
        assert lease is None

    def test_expire_rejects_non_active(self, seeded):
        mgr, store, current = seeded
        mgr.release("lease.1", current.version, current)
        fresh = store.get_run("run.1")
        with pytest.raises(LeaseConflictError, match="cannot expire non-ACTIVE"):
            mgr.expire("lease.1", fresh.version, fresh)


class TestOldLeaseOperationsCannotAffectCurrent:
    def test_old_lease_release_does_not_detach_current(self, seeded):
        mgr, store, current = seeded
        # first grant a replacement to become current
        new_lease = _make_lease(lease_id="lease.2")
        mgr.grant(new_lease, current.version, current)
        # old lease.1 is now RELEASED; release must reject (non-ACTIVE) and not touch current
        fresh = store.get_run("run.1")
        with pytest.raises(LeaseConflictError, match="cannot release non-ACTIVE"):
            mgr.release("lease.1", fresh.version, fresh)
        current_lease = mgr.current("run.1", "n1", "exec.1", "att.1")
        assert current_lease is not None and current_lease.status == LeaseStatus.ACTIVE.value
        assert current_lease.lease_id == "lease.2"

    def test_old_lease_expire_does_not_affect_current_node(self, seeded):
        mgr, store, current = seeded
        new_lease = _make_lease(lease_id="lease.2")
        mgr.grant(new_lease, current.version, current)
        # old lease.1 is now RELEASED; expire must reject (non-ACTIVE) and not touch node
        fresh = store.get_run("run.1")
        with pytest.raises(LeaseConflictError, match="cannot expire non-ACTIVE"):
            mgr.expire("lease.1", fresh.version, fresh)
        node = store.get_run("run.1").state.nodes["n1"]
        # node status should remain RUNNING (current lease is lease.2)
        assert node.status == NodeStatus.RUNNING.value


class TestLeaseCAS:
    def test_lease_operation_rejects_concurrent_mutation(self, seeded):
        mgr, store, current = seeded
        new_lease = _make_lease(lease_id="lease.2")
        mgr.grant(new_lease, current.version, current)
        # now try grant with stale version
        newer = _make_lease(lease_id="lease.3")
        with pytest.raises(ConcurrentStateError):
            mgr.grant(newer, current.version, current)


class TestJournalAppendForLease:
    def test_lease_grant_appends_journal(self, seeded):
        mgr, store, current = seeded
        new_lease = _make_lease(lease_id="lease.2")
        mgr.grant(new_lease, current.version, current)
        records = store.journal_get("run.1", -1)
        assert len(records) >= 2  # detach + register
        kinds = {r.kind for r in records[-2:]}
        assert "lease" in kinds

    def test_lease_release_appends_journal(self, seeded):
        mgr, store, current = seeded
        mgr.release("lease.1", current.version, current)
        records = store.journal_get("run.1", -1)
        assert any(r.kind == "lease" for r in records)


@pytest.fixture
def leased_state(seeded):
    return seeded


@pytest.fixture
def seeded_expired():
    """A store with an already-expired lease (expires_at in the past)."""
    from taskcontroller.domain.enums import LeaseStatus
    from taskcontroller.domain.models import WorkLease
    from taskcontroller.domain.ids import ProviderRef
    from taskcontroller.runtime.runtime_state import (
        RuntimeLeaseState,
        RuntimeSnapshotMeta,
        VersionedRunState,
        make_attempt_record,
    )
    from taskcontroller.runtime.store import InMemoryStateStore

    _EXPIRED = "2026-08-14T09:00:00Z"
    _NOW = "2026-08-14T10:00:00Z"

    expired_lease = WorkLease(
        lease_id="lease.1",
        run_id="run.1",
        node_id="n1",
        execution_id="exec.1",
        attempt_id="att.1",
        holder=ProviderRef(provider_id="provider.1"),
        fencing_token="fence.1",
        granted_at=_NOW,
        expires_at=_EXPIRED,
        status=LeaseStatus.ACTIVE.value,
    )
    state = VersionedRunState(
        state=TeamRunState(
            run_id="run.1",
            status="RUNNING",
            nodes={
                "n1": NodeState(
                    status="RUNNING",
                    contract_ref="ctr.1",
                    current_attempt=1,
                    lease_ref="lease.1",
                    artifact_refs=[],
                )
            },
            active_attempts=["att.1"],
            active_leases=["lease.1"],
        ),
        version=1,
        meta=RuntimeSnapshotMeta(
            attempt_registry={
                "att.1": make_attempt_record(
                    attempt_id="att.1",
                    run_id="run.1",
                    node_id="n1",
                    execution_id="exec.1",
                    fencing_token="fence.1",
                    current_attempt_number=1,
                    current_lease_id="lease.1",
                )
            },
            leases=RuntimeLeaseState(leases={"lease.1": expired_lease}),
            stream_watermarks={},
            event_cursor=None,
            dedupe_fingerprints={},
            journal_position=0,
        ),
    )
    store = InMemoryStateStore()
    store.put_run(state, -1)
    return LeaseManager(store), store, state
