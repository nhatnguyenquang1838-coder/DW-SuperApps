"""WP4 S3 focused tests: orchestrator route->dispatch + signal->event (NO GWC).

Required: route_and_dispatch composes WP3 route() -> ExecutionReceipt -> fabric
dispatch exactly once with explicit now; a no-route request fails closed
(RoutingNoRouteError propagates, no adapter call); signal_to_event maps a trusted
AdapterSignal into a canonical WP2 AgentEvent that WP2 EventRouter accepts.
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import BindingType, EventType, LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.ids import BindingRef, CapabilityRef, ExecutionRef, ProducerRef, ProviderRef
from taskcontroller.domain.models import (
    AgentEvent,
    CapabilityCard,
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
from taskcontroller.execution.errors import ExecutionCorrelationError
from taskcontroller.execution.orchestrator import route_and_dispatch, signal_to_event
from taskcontroller.execution.ports import FakeExecutionAdapter
from taskcontroller.execution.registry import build_registry as build_adapter_registry
from taskcontroller.execution.types import AdapterSignal
from taskcontroller.routing.errors import RoutingNoRouteError
from taskcontroller.routing.registry import build_registry as build_route_registry
from taskcontroller.runtime.event_router import EventRouter
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
    make_attempt_record,
)
from taskcontroller.runtime.store import InMemoryStateStore

_FENCE = "fence.1"
_NOW = "2026-08-14T10:00:00Z"
_EXPIRES = "2026-08-14T11:00:00Z"
_RUN = "run.1"
_NODE = "n1"
_EXEC = "exec.1"
_ATT = "att.1"
_LEASE = "lease.1"
_PROV = "prov.1"


def _provider_card():
    return ExecutionProviderCard(
        provider_id=_PROV,
        provider_kind="LOCAL",
        capability_refs=[CapabilityRef("cap.gen")],
        environment=None,
        bindings=[Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="ipc://l", binding_id="b1")],
        trust_tier="STANDARD",
        cost_class="FREE",
    )


def _capability_card():
    return CapabilityCard(
        capability_id="cap.gen",
        name="generic",
        version="1.0.0",
        idempotency="NON_IDEMPOTENT",
        cost_class="FREE",
        required_environment=EnvironmentRequirement(),
        supported_binding_types=[BindingType.LOCAL_IPC.value],
    )


def _request():
    return ExecutionRequest(
        execution_id=_EXEC,
        contract_ref="tc.1",
        attempt=1,
        attempt_id=_ATT,
        fencing_token=_FENCE,
        capability_requirements=CapabilityRequirement(capability_id="cap.gen"),
        environment_requirements=EnvironmentRequirement(),
        routing_preferences=RoutingPref(),
    )


def _seeded_store():
    lease = WorkLease(
        lease_id=_LEASE, run_id=_RUN, node_id=_NODE, execution_id=_EXEC,
        attempt_id=_ATT, holder=ProviderRef(provider_id=_PROV),
        fencing_token=_FENCE, granted_at=_NOW, expires_at=_EXPIRES,
        status=LeaseStatus.ACTIVE.value,
    )
    run = TeamRunState(
        run_id=_RUN, status=RunStatus.RUNNING.value,
        nodes={_NODE: NodeState(status=NodeStatus.RUNNING.value, contract_ref="ctr.1",
                                current_attempt=1, lease_ref=_LEASE, artifact_refs=[])},
        active_attempts=[_ATT], active_leases=[_LEASE],
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={_ATT: make_attempt_record(
            attempt_id=_ATT, run_id=_RUN, node_id=_NODE, execution_id=_EXEC,
            fencing_token=_FENCE, current_attempt_number=1, current_lease_id=_LEASE)},
        leases=RuntimeLeaseState(leases={_LEASE: lease}),
        stream_watermarks={}, event_cursor=None,
        dedupe_fingerprints={}, journal_position=0,
    )
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=run, version=1, meta=meta), -1)
    return store


class TestRouteAndDispatch:
    def test_route_then_dispatch_exactly_once(self):
        route_reg = build_route_registry([_provider_card()], [_capability_card()])
        adapter_reg = build_adapter_registry([FakeExecutionAdapter(adapter_key="fake.1")])
        store = _seeded_store()
        receipt, ack = route_and_dispatch(
            route_reg, _request(), "rcpt.1", LeaseManager(store),
            adapter_reg, _RUN, _NODE, _NOW, accepted_at=_NOW,
        )
        assert isinstance(receipt, ExecutionReceipt)
        assert receipt.selected_provider.provider_id == _PROV
        assert ack.status == "ACCEPTED"
        assert len(adapter_reg.lookup_by_key("fake.1").dispatched) == 1

    def test_no_route_fails_closed_no_adapter_call(self):
        # capability 'cap.other' has no provider => RoutingNoRouteError
        bad = ExecutionRequest(
            execution_id=_EXEC, contract_ref="tc.1", attempt=1, attempt_id=_ATT,
            fencing_token=_FENCE,
            capability_requirements=CapabilityRequirement(capability_id="cap.other"),
            environment_requirements=EnvironmentRequirement(),
            routing_preferences=RoutingPref(),
        )
        route_reg = build_route_registry([_provider_card()], [_capability_card()])
        adapter_reg = build_adapter_registry([FakeExecutionAdapter(adapter_key="fake.1")])
        store = _seeded_store()
        with pytest.raises(RoutingNoRouteError):
            route_and_dispatch(
                route_reg, bad, "rcpt.2", LeaseManager(store),
                adapter_reg, _RUN, _NODE, _NOW, accepted_at=_NOW,
            )
        assert len(adapter_reg.lookup_by_key("fake.1").dispatched) == 0

    def test_correlation_failure_fails_closed(self):
        # lease store has no active lease for this run => ExecutionCorrelationError
        route_reg = build_route_registry([_provider_card()], [_capability_card()])
        adapter_reg = build_adapter_registry([FakeExecutionAdapter(adapter_key="fake.1")])
        # empty store (no lease)
        store = InMemoryStateStore()
        store.put_run(VersionedRunState(
            state=TeamRunState(run_id=_RUN, status=RunStatus.RUNNING.value,
                               nodes={_NODE: NodeState(status=NodeStatus.RUNNING.value,
                                                       contract_ref="ctr.1", current_attempt=1,
                                                       lease_ref=None, artifact_refs=[])},
                               active_attempts=[_ATT], active_leases=[]),
            version=1,
            meta=RuntimeSnapshotMeta(attempt_registry={}, leases=RuntimeLeaseState(leases={}),
                                     stream_watermarks={}, event_cursor=None,
                                     dedupe_fingerprints={}, journal_position=0),
        ), -1)
        with pytest.raises(ExecutionCorrelationError):
            route_and_dispatch(
                route_reg, _request(), "rcpt.3", LeaseManager(store),
                adapter_reg, _RUN, _NODE, _NOW, accepted_at=_NOW,
            )


class TestSignalToEvent:
    def test_signal_maps_to_canonical_event(self):
        sig = AdapterSignal(
            event_id="evt.1", event_type=EventType.PROGRESS.value,
            sequence=0, execution_ref=ExecutionRef(execution_id=_EXEC, attempt=1,
                                                   attempt_id=_ATT, fencing_token=_FENCE),
            node_id=_NODE, run_id=_RUN, fencing_token=_FENCE, provider_id=_PROV,
            idempotency_key="idk.1", timestamp=_NOW,
            payload={"note": "ok"}, artifact_refs=[],
        )
        event = signal_to_event(sig)
        assert isinstance(event, AgentEvent)
        assert event.event_id == "evt.1"
        assert event.run_id == _RUN and event.node_id == _NODE
        assert event.execution_id == _EXEC and event.attempt_id == _ATT
        assert event.fencing_token == _FENCE
        assert event.producer.producer_id == _PROV
        assert event.sequence == 0

    def test_event_accepted_by_wp2_event_router(self):
        # WP2 EventRouter remains the sole acceptance authority; a well-formed
        # signal-derived event must be accepted (correlated + fenced + sequenced).
        store = _seeded_store()
        router = EventRouter(store)
        sig = AdapterSignal(
            event_id="evt.2", event_type=EventType.PROGRESS.value,
            sequence=0, execution_ref=ExecutionRef(execution_id=_EXEC, attempt=1,
                                                   attempt_id=_ATT, fencing_token=_FENCE),
            node_id=_NODE, run_id=_RUN, fencing_token=_FENCE, provider_id=_PROV,
            idempotency_key="idk.2", timestamp=_NOW,
            payload={"note": "ok"}, artifact_refs=[],
        )
        event = signal_to_event(sig)
        current = store.get_run(_RUN)
        prev = current.version
        router.route(event, current, prev)  # WP2 accepts correlated/fenced event (persists new version)
        assert store.get_run(_RUN).version == prev + 1
