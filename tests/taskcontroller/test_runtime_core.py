"""WP2 focused tests: runtime core (errors, runtime_state, store, event_router, lease).

Coverage:
- CAS version mismatch → ConcurrentStateError
- Store deep-copy guarantee (no aliasing bypass)
- Snapshot / restore round-trip
- Dedupe: duplicate event_id / idempotency_key → EventRejected
- Out-of-order sequence → EventRejected
- Lease grant, current, release, renew, detach-existing
- Checkpoint snapshot / restore

All tests are framework-neutral; no GWC.
"""
from __future__ import annotations
import pytest
from taskcontroller.domain.enums import LeaseStatus, NodeStatus, RunStatus, EventType
from taskcontroller.domain.ids import ProducerRef, ProviderRef
from taskcontroller.domain.models import TeamRunState, WorkLease, AgentEvent
from taskcontroller.domain.values import EventCursor, NodeState
from taskcontroller.runtime.runtime_state import RuntimeLeaseState, RuntimeSnapshotMeta
from taskcontroller.runtime.errors import ConcurrentStateError, EventRejected, LeaseConflictError, RuntimeError, ConcurrentStateError as CSE
from taskcontroller.runtime.runtime_state import AttemptRecord, StreamWatermark, VersionedRunState, RuntimeLeaseState, RuntimeSnapshotMeta, CheckpointSnapshot, PendingMutation, make_versioned_run, make_attempt_record
from taskcontroller.runtime.store import StateStore, InMemoryStateStore, SnapshotRecord, RuntimeRecord, SnapshotBuilder, apply_event
from taskcontroller.runtime.event_router import EventRouter, _make_event_fingerprint, _dedupe_key
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.checkpoint import build_checkpoint_snapshot, restore_from_checkpoint
from taskcontroller.runtime.journal import Journal, recover_from_latest_checkpoint

# Explicit caller-supplied "now" used for lease currentness/expiry decisions.
# Lease.1 expires at 2026-08-20T01:00:00Z, so this value is BEFORE expiry
# (lease is current). Passed explicitly per the explicit-time invariant.
_NOW = "2026-08-14T10:00:00Z"

@pytest.fixture
def team_run_state():
    return TeamRunState(run_id='run.1', status=RunStatus.RUNNING.value, nodes={'n1': NodeState(status=NodeStatus.PENDING.value, contract_ref='tc.1', current_attempt=1, lease_ref='lease.1', artifact_refs=['out.1'])}, active_attempts=['exec.1'], active_leases=['lease.1'], artifact_refs=['out.1'], last_event_cursor=EventCursor(last_event_id='evt.0', sequence=0), checkpoint=None, plan_version='p1', run_version='r1', updated_at='2026-08-13T00:00:00Z')

@pytest.fixture
def versioned_run(team_run_state):
    meta = RuntimeSnapshotMeta(attempt_registry={'att.1': make_attempt_record('att.1', 'run.1', 'n1', 'exec.1', 'ft-1', 1, current_lease_id='lease.1')}, leases=RuntimeLeaseState(leases={}), stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=0)
    return VersionedRunState(state=team_run_state, version=0, meta=meta)

@pytest.fixture
def store():
    return InMemoryStateStore()

@pytest.fixture
def seeded_store(store, versioned_run):
    store.put_run(versioned_run, -1)
    return store

@pytest.fixture
def lease_manager(seeded_store):
    return LeaseManager(seeded_store)

@pytest.fixture
def event_router(seeded_store):
    mgr = LeaseManager(seeded_store)
    lease = WorkLease(lease_id='lease.1', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', holder=ProviderRef('prov.local'), fencing_token='ft-1', granted_at='2026-08-13T00:00:00Z', expires_at='2026-08-20T01:00:00Z', status=LeaseStatus.ACTIVE.value)
    cur = seeded_store.get_run('run.1')
    mgr.grant(lease, cur.version, cur)
    return EventRouter(seeded_store)

@pytest.fixture
def sample_work_lease():
    return WorkLease(lease_id='lease.1', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', holder=ProviderRef('prov.local'), fencing_token='ft-1', granted_at='2026-08-13T00:00:00Z', expires_at='2026-08-20T01:00:00Z', status=LeaseStatus.ACTIVE.value)

@pytest.fixture
def sample_agent_event():
    return AgentEvent(event_id='evt.1', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', fencing_token='ft-1', sequence=0, event_type=EventType.TASK_STARTED.value, producer=ProducerRef('prov.local'), timestamp='2026-08-13T00:00:01Z', idempotency_key='idem.1', payload={'msg': 'started'}, artifact_refs=[])

class TestRuntimeErrors:

    def test_runtime_error_is_exception(self):
        assert issubclass(RuntimeError, Exception)

    def test_concurrent_state_error_message(self):
        err = ConcurrentStateError('run r1: expected 0, current 1')
        assert 'expected 0' in str(err)
        assert 'current 1' in str(err)

    def test_event_rejected_carries_reason(self):
        err = EventRejected('duplicate event_id evt.1')
        assert 'duplicate event_id evt.1' in str(err)

    def test_lease_conflict_error(self):
        err = LeaseConflictError('cannot release non-ACTIVE lease: RELEASED')
        assert 'cannot release non-ACTIVE lease' in str(err)

class TestRuntimeStatePrimitives:

    def test_make_versioned_run_deep_copies_state(self, team_run_state):
        vs = make_versioned_run(team_run_state, 0)
        team_run_state.nodes['n1'].status = 'MUTATED'
        assert vs.state.nodes['n1'].status == NodeStatus.PENDING.value

    def test_versioned_run_to_dict_round_trip(self, versioned_run):
        d = versioned_run.to_dict()
        restored = VersionedRunState.from_dict(d)
        assert restored.version == versioned_run.version
        assert restored.state.run_id == versioned_run.state.run_id

    def test_attempt_record_to_dict_round_trip(self):
        rec = make_attempt_record(attempt_id='att.1', run_id='run.1', node_id='n1', execution_id='exec.1', fencing_token='ft-1', current_attempt_number=1)
        d = rec.to_dict()
        restored = AttemptRecord.from_dict(d)
        assert restored.attempt_id == 'att.1'
        assert restored.fencing_token == 'ft-1'

    def test_stream_watermark_to_dict_round_trip(self):
        wm = StreamWatermark(execution_id='exec.1', attempt_id='att.1', producer_sequence=5)
        d = wm.to_dict()
        restored = StreamWatermark.from_dict(d)
        assert restored.producer_sequence == 5

class TestInMemoryStateStore:

    def test_put_get_run(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        got = store.get_run('run.1')
        assert got is not None
        assert got.version == 0
        assert got.state.run_id == 'run.1'

    def test_cas_mismatch_raises(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        with pytest.raises(ConcurrentStateError):
            store.put_run(versioned_run, 999)

    def test_store_returns_deep_copy(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        got = store.get_run('run.1')
        got.state.nodes['n1'].status = 'MUTATED'
        got2 = store.get_run('run.1')
        assert got2.state.nodes['n1'].status == NodeStatus.PENDING.value

    def test_snapshot_restore_round_trip(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        snap = store.snapshot()
        assert 'run.1' in snap.runs
        store2 = InMemoryStateStore()
        store2.restore(snap)
        got = store2.get_run('run.1')
        assert got is not None
        assert got.version == 0

    def test_journal_append_and_get(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        rec = RuntimeRecord(kind='event', run_id='run.1', payload={'k': 'v'})
        store.journal_append('run.1', rec)
        recs = store.journal_get('run.1', -1)
        assert len(recs) == 1
        assert recs[0].kind == 'event'

    def test_dedupe_put_get(self, store):
        store.dedupe_put('key1', {'event_id': 'evt.1'})
        state = store.dedupe_state()
        assert state['key1'] == {'event_id': 'evt.1'}

class TestEventRouterDedupe:

    def test_duplicate_event_id_rejected(self, event_router, sample_agent_event):
        router = event_router
        store = router._store
        current = store.get_run('run.1')
        router.route(sample_agent_event, current, current.version)
        current = store.get_run('run.1')
        conflicting = AgentEvent(event_id='evt.1', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', fencing_token='ft-1', sequence=1, event_type=EventType.PROGRESS.value, producer=ProducerRef('prov.local'), timestamp='2026-08-13T00:00:02Z', idempotency_key='idem.1', payload={'msg': 'changed'}, artifact_refs=[])
        with pytest.raises(EventRejected, match='conflicting reuse'):
            router.route(conflicting, current, current.version)

    def test_duplicate_idempotency_key_rejected(self, event_router, sample_agent_event):
        router = event_router
        store = router._store
        current = store.get_run('run.1')
        router.route(sample_agent_event, current, current.version)
        current = store.get_run('run.1')
        conflicting = AgentEvent(event_id='evt.2', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', fencing_token='ft-1', sequence=1, event_type=EventType.PROGRESS.value, producer=ProducerRef('prov.local'), timestamp='2026-08-13T00:00:02Z', idempotency_key='idem.1', payload={'msg': 'changed'}, artifact_refs=[])
        with pytest.raises(EventRejected, match='conflicting reuse'):
            router.route(conflicting, current, current.version)

    def test_dedupe_key_function(self, sample_agent_event):
        assert _dedupe_key(sample_agent_event) == 'evt.1'

    def test_make_event_fingerprint_includes_event_id(self, sample_agent_event):
        fp = _make_event_fingerprint(sample_agent_event)
        assert fp['event_id'] == 'evt.1'
        assert fp['idempotency_key'] == 'idem.1'

class TestEventRouterSequence:

    def test_first_event_sequence_zero_accepted(self, event_router):
        from taskcontroller.domain.enums import EventType
        evt = AgentEvent(event_id='evt.1', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', fencing_token='ft-1', sequence=0, event_type=EventType.TASK_STARTED.value, producer=ProducerRef('prov.local'), timestamp='2026-08-13T00:00:01Z', idempotency_key=None, payload={}, artifact_refs=[])
        router = event_router
        store = router._store
        current = store.get_run('run.1')
        result = router.route(evt, current, current.version)
        assert result is not None
        assert result.version == current.version + 1

    def test_out_of_order_sequence_rejected(self, event_router):
        router = event_router
        store = router._store
        current = store.get_run('run.1')
        first = AgentEvent(event_id='evt.1', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', fencing_token='ft-1', sequence=0, event_type=EventType.TASK_STARTED.value, producer=ProducerRef('prov.local'), timestamp='2026-08-13T00:00:01Z', idempotency_key=None, payload={}, artifact_refs=[])
        router.route(first, current, current.version)
        current = store.get_run('run.1')
        second = AgentEvent(event_id='evt.2', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', fencing_token='ft-1', sequence=3, event_type=EventType.TASK_STARTED.value, producer=ProducerRef('prov.local'), timestamp='2026-08-13T00:00:02Z', idempotency_key=None, payload={}, artifact_refs=[])
        with pytest.raises(EventRejected, match='out-of-order sequence'):
            router.route(second, current, current.version)

    def test_same_sequence_not_rejected(self, event_router):
        router = event_router
        store = router._store
        current = store.get_run('run.1')
        first = AgentEvent(event_id='evt.1', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', fencing_token='ft-1', sequence=0, event_type=EventType.TASK_STARTED.value, producer=ProducerRef('prov.local'), timestamp='2026-08-13T00:00:01Z', idempotency_key=None, payload={}, artifact_refs=[])
        router.route(first, current, current.version)
        current = store.get_run('run.1')
        second = AgentEvent(event_id='evt.2', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', fencing_token='ft-1', sequence=0, event_type=EventType.TASK_STARTED.value, producer=ProducerRef('prov.local'), timestamp='2026-08-13T00:00:02Z', idempotency_key=None, payload={}, artifact_refs=[])
        with pytest.raises(EventRejected, match='out-of-order sequence'):
            router.route(second, current, current.version)

class TestEventRouterCAS:

    def test_cas_mismatch_raises(self, event_router, sample_agent_event):
        router = event_router
        store = router._store
        current = store.get_run('run.1')
        with pytest.raises(ConcurrentStateError):
            router.route(sample_agent_event, current, 999)

    def test_version_bumped_on_accept(self, event_router, sample_agent_event):
        router = event_router
        store = router._store
        current = store.get_run('run.1')
        result = router.route(sample_agent_event, current, current.version)
        assert result.version == current.version + 1

class TestLeaseGrant:

    def test_grant_active_lease(self, lease_manager, sample_work_lease):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        result = mgr.grant(sample_work_lease, 0, current)
        assert result is not None
        assert result.version == current.version + 1

    def test_grant_detaches_existing_active_lease(self, lease_manager, sample_work_lease):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        mgr.grant(sample_work_lease, 0, current)
        current = store.get_run('run.1')
        second = WorkLease(lease_id='lease.2', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', holder=ProviderRef('prov.remote'), fencing_token='ft-2', granted_at='2026-08-13T00:01:00Z', expires_at='2026-08-13T02:00:00Z', status=LeaseStatus.ACTIVE.value)
        result = mgr.grant(second, current.version, store.get_run('run.1'))
        assert result.version == 3
        leases = mgr._leases_dict(store.get_run('run.1'))
        assert leases['lease.1'].status == LeaseStatus.RELEASED.value
        assert leases['lease.2'].status == LeaseStatus.ACTIVE.value

    def test_current_returns_active_lease(self, lease_manager, sample_work_lease):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        mgr.grant(sample_work_lease, 0, current)
        cur = mgr.current('run.1', 'n1', 'exec.1', 'att.1', now=_NOW)
        assert cur is not None
        assert cur.lease_id == 'lease.1'

    def test_current_returns_none_for_nonexistent(self, lease_manager):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        cur = mgr.current('run.1', 'n1', 'exec.1', 'att.1', now=_NOW)
        assert cur is None

    def test_grant_rejects_non_active_status(self, lease_manager):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        bad = WorkLease(lease_id='lease.1', run_id='run.1', node_id='n1', execution_id='exec.1', attempt_id='att.1', holder=ProviderRef('prov.local'), fencing_token='ft-1', granted_at='2026-08-13T00:00:00Z', expires_at='2026-08-13T01:00:00Z', status=LeaseStatus.RELEASED.value)
        with pytest.raises(LeaseConflictError, match='cannot grant non-ACTIVE'):
            mgr.grant(bad, 0, current)

class TestLeaseRelease:

    def test_release_active_lease(self, lease_manager, sample_work_lease):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        mgr.grant(sample_work_lease, 0, current)
        current = store.get_run('run.1')
        result = mgr.release('lease.1', current.version, store.get_run('run.1'), now=_NOW)
        assert result is not None
        assert result.version == 2
        cur = mgr.current('run.1', 'n1', 'exec.1', 'att.1', now=_NOW)
        assert cur is None

    def test_release_unknown_lease_raises(self, lease_manager):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        with pytest.raises(LeaseConflictError, match='unknown lease_id'):
            mgr.release('lease.unknown', 0, current, now=_NOW)

    def test_release_non_active_raises(self, lease_manager, sample_work_lease):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        mgr.grant(sample_work_lease, 0, current)
        current = store.get_run('run.1')
        mgr.release('lease.1', current.version, store.get_run('run.1'), now=_NOW)
        current = store.get_run('run.1')
        with pytest.raises(LeaseConflictError, match='cannot release non-ACTIVE'):
            mgr.release('lease.1', current.version, store.get_run('run.1'), now=_NOW)

class TestLeaseRenew:

    def test_renew_extends_expiry(self, lease_manager, sample_work_lease):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        mgr.grant(sample_work_lease, 0, current)
        current = store.get_run('run.1')
        result = mgr.renew('lease.1', new_expires_at='2026-08-20T02:00:00Z', fencing_token='ft-1', expected_version=current.version, current_state=store.get_run('run.1'), now=_NOW)
        assert result is not None
        assert result.version == 2
        cur = mgr.current('run.1', 'n1', 'exec.1', 'att.1', now=_NOW)
        assert cur is not None
        assert cur.expires_at == '2026-08-20T02:00:00Z'

    def test_renew_fencing_token_mismatch_raises(self, lease_manager, sample_work_lease):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        mgr.grant(sample_work_lease, 0, current)
        current = store.get_run('run.1')
        with pytest.raises(LeaseConflictError, match='fencing_token mismatch'):
            mgr.renew('lease.1', new_expires_at='2026-08-13T02:00:00Z', fencing_token='ft-wrong', expected_version=current.version, current_state=store.get_run('run.1'), now=_NOW)

    def test_renew_unknown_lease_raises(self, lease_manager):
        mgr = lease_manager
        store = mgr._store
        current = store.get_run('run.1')
        with pytest.raises(LeaseConflictError, match='unknown lease_id'):
            mgr.renew('lease.unknown', new_expires_at='2026-08-13T02:00:00Z', fencing_token='ft-1', expected_version=0, current_state=current, now=_NOW)

class TestCheckpointSnapshot:

    def test_build_checkpoint_snapshot(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        snap = build_checkpoint_snapshot(store, 'run.1')
        assert snap.run_id == 'run.1'
        assert snap.version == 0
        assert snap.state.run_id == 'run.1'

    def test_build_checkpoint_snapshot_unknown_run_raises(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        with pytest.raises(KeyError):
            build_checkpoint_snapshot(store, 'run.unknown')

    def test_restore_from_checkpoint(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        snap = build_checkpoint_snapshot(store, 'run.1')
        store2 = InMemoryStateStore()
        restore_from_checkpoint(store2, snap)
        got = store2.get_run('run.1')
        assert got is not None
        assert got.version == 0
        assert got.state.run_id == 'run.1'

class TestJournal:

    def test_append_and_get_after(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        journal = Journal(store)
        rec = journal.append('run.1', 'event', {'k': 'v'})
        assert rec.record_index == 0
        recs = journal.get_after('run.1', -1)
        assert len(recs) == 1
        assert recs[0].kind == 'event'

    def test_last_index(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        journal = Journal(store)
        assert journal.last_index('run.1') == -1
        journal.append('run.1', 'event', {})
        assert journal.last_index('run.1') == 0

    def test_recover_from_latest_checkpoint(self, store, versioned_run):
        store.put_run(versioned_run, -1)
        rs = recover_from_latest_checkpoint(store, 'run.1')
        assert rs is not None
        assert rs.version == 0
        assert rs.state.run_id == 'run.1'

    def test_recover_from_latest_checkpoint_unknown_run_returns_none(self, store):
        rs = recover_from_latest_checkpoint(store, 'run.unknown')
        assert rs is None