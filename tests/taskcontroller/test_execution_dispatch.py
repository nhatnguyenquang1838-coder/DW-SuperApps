"""WP4 S2 focused tests: dispatch preflight + idempotent dispatch (NO GWC).

Required: happy dispatch exactly one adapter call; no lease; expired/non-current
lease; fencing mismatch; provider mismatch; binding mismatch; request/receipt
execution mismatch; identical command retry no second call; command-ID conflict;
adapter rejection typed; no state/version mutation merely from dispatch.
"""
from __future__ import annotations
import pytest
from taskcontroller.domain.enums import BindingType, LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.ids import BindingRef, ExecutionRef, ProviderRef
from taskcontroller.domain.models import ExecutionProviderCard, ExecutionReceipt, ExecutionRequest, TeamRunState, WorkLease
from taskcontroller.domain.values import Binding, CapabilityRequirement, EnvironmentRequirement, NodeState, RoutingPref
from taskcontroller.execution.errors import DuplicateCommandError, ExecutionCorrelationError, DispatchRejectedError
from taskcontroller.execution.fabric import ExecutionFabric
from taskcontroller.execution.ports import FakeExecutionAdapter
from taskcontroller.execution.registry import build_registry
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.runtime_state import RuntimeLeaseState, RuntimeSnapshotMeta, VersionedRunState, make_attempt_record
from taskcontroller.runtime.store import InMemoryStateStore
_FENCE = 'fence.1'
_NOW = '2026-08-14T10:00:00Z'
_EXPIRES = '2026-08-14T11:00:00Z'
_EXPIRED = '2026-08-14T09:00:00Z'
_RUN = 'run.1'
_NODE = 'n1'
_EXEC = 'exec.1'
_ATT = 'att.1'
_LEASE = 'lease.1'
_PROV = 'prov.1'

# Sentinel: _seeded_store() with no arg builds a store WITH a valid active lease.
# Pass lease=None explicitly to build a store with NO active lease.
_USE_DEFAULT_LEASE = object()

def _binding():
    return Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref='ipc://l', binding_id='b1')

def _provider():
    return ExecutionProviderCard(provider_id=_PROV, provider_kind='LOCAL', capability_refs=[], environment=None, bindings=[_binding()], trust_tier='STANDARD', cost_class='FREE')

def _request():
    return ExecutionRequest(execution_id=_EXEC, contract_ref='tc.1', attempt=1, attempt_id=_ATT, fencing_token=_FENCE, capability_requirements=CapabilityRequirement(capability_id='cap.gen'), environment_requirements=EnvironmentRequirement(), routing_preferences=RoutingPref())

def _receipt(binding_id='b1', provider_id=_PROV):
    return ExecutionReceipt(receipt_id='rcpt.1', contract_ref='tc.1', execution_ref=ExecutionRef(execution_id=_EXEC, attempt=1, attempt_id=_ATT, fencing_token=_FENCE), selected_provider=ProviderRef(provider_id=provider_id), binding=BindingRef(binding_id=binding_id), status='ROUTING')

def _lease(expires_at=_EXPIRES, fencing=_FENCE, holder=_PROV, status=LeaseStatus.ACTIVE.value):
    return WorkLease(lease_id=_LEASE, run_id=_RUN, node_id=_NODE, execution_id=_EXEC, attempt_id=_ATT, holder=ProviderRef(provider_id=holder), fencing_token=fencing, granted_at=_NOW, expires_at=expires_at, status=status)

def _seeded_store(lease=_USE_DEFAULT_LEASE):
    if lease is None:
        # No active lease at all: empty attempt registry + lease dict so that
        # LeaseManager.current() returns None (preflight must reject dispatch).
        run = TeamRunState(run_id=_RUN, status=RunStatus.RUNNING.value, nodes={_NODE: NodeState(status=NodeStatus.RUNNING.value, contract_ref='ctr.1', current_attempt=1, lease_ref=None, artifact_refs=[])}, active_attempts=[_ATT], active_leases=[])
        meta = RuntimeSnapshotMeta(attempt_registry={}, leases=RuntimeLeaseState(leases={}), stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=0)
        store = InMemoryStateStore()
        store.put_run(VersionedRunState(state=run, version=1, meta=meta), -1)
        return store
    lease = lease if lease is not _USE_DEFAULT_LEASE else _lease()
    run = TeamRunState(run_id=_RUN, status=RunStatus.RUNNING.value, nodes={_NODE: NodeState(status=NodeStatus.RUNNING.value, contract_ref='ctr.1', current_attempt=1, lease_ref=lease.lease_id, artifact_refs=[])}, active_attempts=[_ATT], active_leases=[lease.lease_id])
    meta = RuntimeSnapshotMeta(attempt_registry={_ATT: make_attempt_record(attempt_id=_ATT, run_id=_RUN, node_id=_NODE, execution_id=_EXEC, fencing_token=_FENCE, current_attempt_number=1, current_lease_id=lease.lease_id)}, leases=RuntimeLeaseState(leases={lease.lease_id: lease}), stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=0)
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=run, version=1, meta=meta), -1)
    return store

class TestDispatchHappy:

    def test_happy_dispatch_exactly_one_adapter_call(self):
        store = _seeded_store()
        fabric = ExecutionFabric(build_registry([FakeExecutionAdapter(adapter_key='fake.1')]), LeaseManager(store))
        adapter = fabric._registry.lookup_by_key('fake.1')
        ack = fabric.dispatch(_request(), _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)
        assert ack.status == 'ACCEPTED'
        assert len(adapter.dispatched) == 1

    def test_no_state_version_mutation_from_dispatch(self):
        store = _seeded_store()
        before = store.get_run(_RUN).version
        fabric = ExecutionFabric(build_registry([FakeExecutionAdapter(adapter_key='fake.1')]), LeaseManager(store))
        fabric.dispatch(_request(), _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)
        after = store.get_run(_RUN).version
        assert after == before

class TestDispatchPreflightFailClosed:

    def test_no_lease_blocks(self):
        store = _seeded_store(lease=None)
        fabric = ExecutionFabric(build_registry([FakeExecutionAdapter(adapter_key='fake.1')]), LeaseManager(store))
        with pytest.raises(ExecutionCorrelationError, match='no current ACTIVE lease'):
            fabric.dispatch(_request(), _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)
        assert len(fabric._registry.lookup_by_key('fake.1').dispatched) == 0

    def test_expired_lease_blocks(self):
        store = _seeded_store(lease=_lease(expires_at=_EXPIRED))
        fabric = ExecutionFabric(build_registry([FakeExecutionAdapter(adapter_key='fake.1')]), LeaseManager(store))
        with pytest.raises(ExecutionCorrelationError):
            fabric.dispatch(_request(), _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)

    def test_fencing_mismatch_blocks(self):
        store = _seeded_store(lease=_lease(fencing='other-fence'))
        fabric = ExecutionFabric(build_registry([FakeExecutionAdapter(adapter_key='fake.1')]), LeaseManager(store))
        with pytest.raises(ExecutionCorrelationError, match='fencing_token'):
            fabric.dispatch(_request(), _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)

    def test_provider_mismatch_blocks(self):
        store = _seeded_store()
        fabric = ExecutionFabric(build_registry([FakeExecutionAdapter(adapter_key='fake.1')]), LeaseManager(store))
        with pytest.raises(ExecutionCorrelationError, match='selected provider'):
            fabric.dispatch(_request(), _receipt(provider_id='prov.OTHER'), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)

    def test_binding_mismatch_blocks(self):
        store = _seeded_store()
        fabric = ExecutionFabric(build_registry([FakeExecutionAdapter(adapter_key='fake.1')]), LeaseManager(store))
        with pytest.raises(ExecutionCorrelationError, match='no provider binding resolved'):
            fabric.dispatch(_request(), _receipt(binding_id='wrong.b'), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)

    def test_request_receipt_execution_mismatch_blocks(self):
        store = _seeded_store()
        fabric = ExecutionFabric(build_registry([FakeExecutionAdapter(adapter_key='fake.1')]), LeaseManager(store))
        bad = ExecutionRequest(execution_id='exec.OTHER', contract_ref='tc.1', attempt=1, attempt_id=_ATT, fencing_token=_FENCE, capability_requirements=CapabilityRequirement(capability_id='cap.gen'), environment_requirements=EnvironmentRequirement(), routing_preferences=RoutingPref())
        with pytest.raises(ExecutionCorrelationError, match='execution_id'):
            fabric.dispatch(bad, _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)

class TestDispatchIdempotency:

    def test_identical_command_retry_no_second_call(self):
        store = _seeded_store()
        fabric = ExecutionFabric(build_registry([FakeExecutionAdapter(adapter_key='fake.1')]), LeaseManager(store))
        adapter = fabric._registry.lookup_by_key('fake.1')
        a1 = fabric.dispatch(_request(), _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)
        a2 = fabric.dispatch(_request(), _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)
        assert a1.status == a2.status
        assert len(adapter.dispatched) == 1

    def test_command_id_conflict_different_envelope(self):
        store = _seeded_store()
        fabric = ExecutionFabric(build_registry([FakeExecutionAdapter(adapter_key='fake.1')]), LeaseManager(store))
        fabric.dispatch(_request(), _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)
        # Same command_id, but a different (still-correlated) request envelope:
        # only an un-correlated field (capability requirement) differs. Correlation
        # passes, yet the canonical envelope fingerprint differs => conflict.
        alt = ExecutionRequest(
            execution_id=_EXEC, contract_ref='tc.1', attempt=1, attempt_id=_ATT,
            fencing_token=_FENCE,
            capability_requirements=CapabilityRequirement(capability_id='cap.OTHER'),
            environment_requirements=EnvironmentRequirement(),
            routing_preferences=RoutingPref(),
        )
        with pytest.raises(DuplicateCommandError):
            fabric.dispatch(alt, _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)

class TestDispatchAdapterRejection:

    def test_adapter_rejection_typed(self):
        store = _seeded_store()
        adapter = FakeExecutionAdapter(adapter_key='fake.1')
        adapter.set_reject_next_dispatch()
        fabric = ExecutionFabric(build_registry([adapter]), LeaseManager(store))
        with pytest.raises(DispatchRejectedError):
            fabric.dispatch(_request(), _receipt(), _provider(), _RUN, _NODE, 'cmd.1', now=_NOW)