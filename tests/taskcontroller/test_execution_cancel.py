"""WP4 S4 focused tests: cancellation + adversarial E2E authority (NO GWC).

Required coercion of the fabric's fail-closed cancel path plus the WP2 authority
guard for adapter signals:

  cancel-unsupported    -> typed AdapterUnsupportedError, zero adapter side-effect
  cancel-currentness     -> no/expired/replaced-fencing lease blocks before adapter call
  cancel-happy-idempotent-> current lease + cancel-capable adapter => exactly one
                           adapter cancel call + normalized CancelAck; identical retry
                           no second call; conflicting envelope => DuplicateCommandError
  no-blind-mutation      -> fabric/cancel never sets run/node status directly
  stale-signal-lease-B   -> dispatch under lease A, replace with lease B, stale A signal
                           is rejected by WP2 EventRouter (no WP2 mutation)
  completed-not-done     -> COMPLETED signal reaches at most node REVIEWING, never DONE
  status-change-guard    -> STATUS_CHANGE payload cannot drive DONE / run cancellation
  fake-only              -> no real network/tool/product side effect (fake adapters only)
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import (
    BindingType,
    EventType,
    LeaseStatus,
    NodeStatus,
    RunStatus,
)
from taskcontroller.domain.ids import BindingRef, ExecutionRef, ProviderRef
from taskcontroller.domain.models import (
    ExecutionProviderCard,
    ExecutionReceipt,
    ExecutionRequest,
    TeamRunState,
    WorkLease,
)
from taskcontroller.domain.values import (
    Binding,
    CapabilityRequirement,
    EnvironmentRequirement,
    NodeState,
    RoutingPref,
)
from taskcontroller.execution.errors import (
    AdapterUnsupportedError,
    DuplicateCommandError,
    ExecutionCorrelationError,
)
from taskcontroller.execution.fabric import ExecutionFabric
from taskcontroller.execution.orchestrator import forward_signal_to_router, signal_to_event
from taskcontroller.execution.ports import ExecutionAdapter, FakeExecutionAdapter
from taskcontroller.execution.registry import build_registry as build_adapter_registry
from taskcontroller.execution.types import AdapterSignal, CancelAck, DispatchAck
from taskcontroller.runtime.event_router import EventRouter
from taskcontroller.runtime.errors import EventRejected
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
    make_attempt_record,
)
from taskcontroller.runtime.store import InMemoryStateStore

_NOW = "2026-08-14T10:00:00Z"
_EXPIRES = "2026-08-14T11:00:00Z"
_EXPIRED = "2026-08-14T09:00:00Z"
_RUN = "run.1"
_NODE = "n1"
_EXEC = "exec.1"
_ATT = "att.1"
_LEASE = "lease.1"
_LEASE_B = "lease.B"
_PROV = "prov.1"
_FENCE = "fence.1"
_FENCE_B = "fence.B"


class _UnsupportedCancelAdapter(ExecutionAdapter):
    """Adapter that does NOT support cancel (declares unsupported)."""

    supported_binding_types = (BindingType.LOCAL_IPC.value,)

    def __init__(self, adapter_key: str = "unsupported.1") -> None:
        self.adapter_key = adapter_key
        self.cancel_called = False

    def dispatch(self, envelope) -> DispatchAck:
        return DispatchAck(command_id=envelope.command_id, accepted=True,
                           status="ACCEPTED", adapter_key=self.adapter_key)

    def supports_cancel(self) -> bool:
        return False

    def cancel(self, envelope):
        # Should never be reached: fabric short-circuits on supports_cancel()==False
        self.cancel_called = True
        raise AdapterUnsupportedError("unreachable in fail-closed path")


def _provider_card():
    return ExecutionProviderCard(
        provider_id=_PROV, provider_kind="LOCAL",
        capability_refs=[], environment=None,
        bindings=[Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="ipc://l", binding_id="b1")],
        trust_tier="STANDARD", cost_class="FREE",
    )


def _request():
    return ExecutionRequest(
        execution_id=_EXEC, contract_ref="tc.1", attempt=1, attempt_id=_ATT,
        fencing_token=_FENCE,
        capability_requirements=CapabilityRequirement(capability_id="cap.gen"),
        environment_requirements=EnvironmentRequirement(),
        routing_preferences=RoutingPref(),
    )


def _receipt():
    return ExecutionReceipt(
        receipt_id="rcpt.1", contract_ref="tc.1",
        execution_ref=ExecutionRef(execution_id=_EXEC, attempt=1, attempt_id=_ATT, fencing_token=_FENCE),
        selected_provider=ProviderRef(provider_id=_PROV),
        binding=BindingRef(binding_id="b1"), status="ROUTING",
    )


def _lease(fencing=_FENCE, expires_at=_EXPIRES, lease_id=_LEASE, status=LeaseStatus.ACTIVE.value):
    return WorkLease(
        lease_id=lease_id, run_id=_RUN, node_id=_NODE, execution_id=_EXEC,
        attempt_id=_ATT, holder=ProviderRef(provider_id=_PROV),
        fencing_token=fencing, granted_at=_NOW, expires_at=expires_at, status=status,
    )


def _seeded_store(lease=_lease()):
    run = TeamRunState(
        run_id=_RUN, status=RunStatus.RUNNING.value,
        nodes={_NODE: NodeState(status=NodeStatus.RUNNING.value, contract_ref="ctr.1",
                                current_attempt=1, lease_ref=lease.lease_id, artifact_refs=[])},
        active_attempts=[_ATT], active_leases=[lease.lease_id],
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={_ATT: make_attempt_record(
            attempt_id=_ATT, run_id=_RUN, node_id=_NODE, execution_id=_EXEC,
            fencing_token=_FENCE, current_attempt_number=1, current_lease_id=lease.lease_id)},
        leases=RuntimeLeaseState(leases={lease.lease_id: lease}),
        stream_watermarks={}, event_cursor=None,
        dedupe_fingerprints={}, journal_position=0,
    )
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=run, version=1, meta=meta), -1)
    return store


def _empty_store():
    """No active lease at all."""
    run = TeamRunState(
        run_id=_RUN, status=RunStatus.RUNNING.value,
        nodes={_NODE: NodeState(status=NodeStatus.RUNNING.value, contract_ref="ctr.1",
                                current_attempt=1, lease_ref=None, artifact_refs=[])},
        active_attempts=[_ATT], active_leases=[],
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={}, leases=RuntimeLeaseState(leases={}),
        stream_watermarks={}, event_cursor=None,
        dedupe_fingerprints={}, journal_position=0,
    )
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=run, version=1, meta=meta), -1)
    return store


def _store_replaced_with_lease_b():
    """Lease A was replaced by lease B (different fencing) for the same quad."""
    lb = _lease(fencing=_FENCE_B, lease_id=_LEASE_B)
    run = TeamRunState(
        run_id=_RUN, status=RunStatus.RUNNING.value,
        nodes={_NODE: NodeState(status=NodeStatus.RUNNING.value, contract_ref="ctr.1",
                                current_attempt=1, lease_ref=_LEASE_B, artifact_refs=[])},
        active_attempts=[_ATT], active_leases=[_LEASE_B],
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={_ATT: make_attempt_record(
            attempt_id=_ATT, run_id=_RUN, node_id=_NODE, execution_id=_EXEC,
            fencing_token=_FENCE_B, current_attempt_number=1, current_lease_id=_LEASE_B)},
        leases=RuntimeLeaseState(leases={_LEASE_B: lb}),
        stream_watermarks={}, event_cursor=None,
        dedupe_fingerprints={}, journal_position=0,
    )
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=run, version=1, meta=meta), -1)
    return store


class TestCancelUnsupported:
    def test_unsupported_adapter_raises_typed_no_side_effect(self):
        store = _seeded_store()
        reg = build_adapter_registry([_UnsupportedCancelAdapter()])
        fabric = ExecutionFabric(reg, LeaseManager(store))
        with pytest.raises(AdapterUnsupportedError):
            fabric.cancel(_request(), _receipt(), _provider_card(), _RUN, _NODE, "cancel.1", _NOW)
        # adapter.cancel() must never have been invoked (zero side-effect)
        assert reg.lookup_by_key("unsupported.1").cancel_called is False


class TestCancelCurrentnessFencing:
    def test_no_lease_blocks_before_adapter(self):
        store = _empty_store()
        reg = build_adapter_registry([FakeExecutionAdapter(adapter_key="fake.1")])
        fabric = ExecutionFabric(reg, LeaseManager(store))
        with pytest.raises(ExecutionCorrelationError, match="no current ACTIVE lease"):
            fabric.cancel(_request(), _receipt(), _provider_card(), _RUN, _NODE, "cancel.2", _NOW)
        assert len(reg.lookup_by_key("fake.1").cancelled) == 0

    def test_expired_lease_blocks_before_adapter(self):
        store = _seeded_store(lease=_lease(expires_at=_EXPIRED))
        reg = build_adapter_registry([FakeExecutionAdapter(adapter_key="fake.1")])
        fabric = ExecutionFabric(reg, LeaseManager(store))
        with pytest.raises(ExecutionCorrelationError):
            fabric.cancel(_request(), _receipt(), _provider_card(), _RUN, _NODE, "cancel.3", _NOW)
        assert len(reg.lookup_by_key("fake.1").cancelled) == 0

    def test_replaced_fencing_blocks_before_adapter(self):
        # store now holds lease B (fence.B); cancel request still carries fence.1
        store = _store_replaced_with_lease_b()
        reg = build_adapter_registry([FakeExecutionAdapter(adapter_key="fake.1")])
        fabric = ExecutionFabric(reg, LeaseManager(store))
        with pytest.raises(ExecutionCorrelationError, match="fencing_token"):
            fabric.cancel(_request(), _receipt(), _provider_card(), _RUN, _NODE, "cancel.4", _NOW)
        assert len(reg.lookup_by_key("fake.1").cancelled) == 0


class TestCancelHappyIdempotent:
    def test_happy_exactly_once_and_normalized_ack(self):
        store = _seeded_store()
        adapter = FakeExecutionAdapter(adapter_key="fake.1")
        fabric = ExecutionFabric(build_adapter_registry([adapter]), LeaseManager(store))
        ack = fabric.cancel(_request(), _receipt(), _provider_card(), _RUN, _NODE, "cancel.5", _NOW)
        assert isinstance(ack, CancelAck)
        assert ack.status == "ACCEPTED"
        assert len(adapter.cancelled) == 1

    def test_identical_retry_no_second_adapter_call(self):
        store = _seeded_store()
        adapter = FakeExecutionAdapter(adapter_key="fake.1")
        fabric = ExecutionFabric(build_adapter_registry([adapter]), LeaseManager(store))
        fabric.cancel(_request(), _receipt(), _provider_card(), _RUN, _NODE, "cancel.6", _NOW)
        ack2 = fabric.cancel(_request(), _receipt(), _provider_card(), _RUN, _NODE, "cancel.6", _NOW)
        assert ack2.status == "ACCEPTED"
        assert len(adapter.cancelled) == 1  # idempotent: no second adapter call

    def test_conflicting_command_identity_fails_closed(self):
        store = _seeded_store()
        adapter = FakeExecutionAdapter(adapter_key="fake.1")
        fabric = ExecutionFabric(build_adapter_registry([adapter]), LeaseManager(store))
        fabric.cancel(_request(), _receipt(), _provider_card(), _RUN, _NODE, "cancel.7", _NOW)
        alt = ExecutionRequest(
            execution_id=_EXEC, contract_ref="tc.1", attempt=1, attempt_id=_ATT,
            fencing_token=_FENCE,
            capability_requirements=CapabilityRequirement(capability_id="cap.OTHER"),
            environment_requirements=EnvironmentRequirement(),
            routing_preferences=RoutingPref(),
        )
        with pytest.raises(DuplicateCommandError):
            fabric.cancel(alt, _receipt(), _provider_card(), _RUN, _NODE, "cancel.7", _NOW)


class TestNoBlindMutation:
    def test_cancel_does_not_set_run_or_node_status(self):
        store = _seeded_store()
        adapter = FakeExecutionAdapter(adapter_key="fake.1")
        fabric = ExecutionFabric(build_adapter_registry([adapter]), LeaseManager(store))
        before = store.get_run(_RUN)
        fabric.cancel(_request(), _receipt(), _provider_card(), _RUN, _NODE, "cancel.8", _NOW)
        after = store.get_run(_RUN)
        # fabric/cancel must NOT mutate WP2 run/node state
        assert after.state.status == before.state.status == RunStatus.RUNNING.value
        assert after.state.nodes[_NODE].status == NodeStatus.RUNNING.value


class TestStaleSignalAfterReplacement:
    def test_lease_a_signal_rejected_by_wp2_router(self):
        # dispatch happened under lease A; then lease replaced by B. A stale signal
        # carrying lease A fencing/attempt must be rejected by WP2 EventRouter.
        store = _store_replaced_with_lease_b()
        router = EventRouter(store)
        stale = AdapterSignal(
            event_id="evt.stale", event_type=EventType.PROGRESS.value,
            sequence=0,
            execution_ref=ExecutionRef(execution_id=_EXEC, attempt=1, attempt_id=_ATT, fencing_token=_FENCE),
            node_id=_NODE, run_id=_RUN, fencing_token=_FENCE, provider_id=_PROV,
            idempotency_key="idk.stale", timestamp=_NOW,
            payload={"note": "stale"}, artifact_refs=[],
        )
        event = signal_to_event(stale)
        before = store.get_run(_RUN).version
        with pytest.raises(EventRejected):
            forward_signal_to_router(stale, router, store)
        # no WP2 mutation occurred
        assert store.get_run(_RUN).version == before


class TestCompletedAuthority:
    def test_completed_reaches_at_most_reviewing_never_done(self):
        store = _seeded_store()
        router = EventRouter(store)
        sig = AdapterSignal(
            event_id="evt.done", event_type=EventType.COMPLETED.value,
            sequence=0,
            execution_ref=ExecutionRef(execution_id=_EXEC, attempt=1, attempt_id=_ATT, fencing_token=_FENCE),
            node_id=_NODE, run_id=_RUN, fencing_token=_FENCE, provider_id=_PROV,
            idempotency_key="idk.done", timestamp=_NOW,
            payload={"ok": True}, artifact_refs=[],
        )
        forward_signal_to_router(sig, router, store)
        node = store.get_run(_RUN).state.nodes[_NODE]
        assert node.status == NodeStatus.REVIEWING.value
        # run-level authority unchanged by COMPLETED (never DONE)
        assert store.get_run(_RUN).state.status == RunStatus.RUNNING.value


class TestStatusChangeGuard:
    def test_status_change_cannot_drive_done(self):
        store = _seeded_store()
        router = EventRouter(store)
        sig = AdapterSignal(
            event_id="evt.sc", event_type=EventType.STATUS_CHANGE.value,
            sequence=0,
            execution_ref=ExecutionRef(execution_id=_EXEC, attempt=1, attempt_id=_ATT, fencing_token=_FENCE),
            node_id=_NODE, run_id=_RUN, fencing_token=_FENCE, provider_id=_PROV,
            idempotency_key="idk.sc", timestamp=_NOW,
            payload={"status": "DONE"}, artifact_refs=[],
        )
        with pytest.raises(Exception):
            forward_signal_to_router(sig, router, store)
        # node/run must NOT have been driven to DONE by a generic status change
        assert store.get_run(_RUN).state.nodes[_NODE].status != NodeStatus.DONE.value
        assert store.get_run(_RUN).state.status != "DONE"
