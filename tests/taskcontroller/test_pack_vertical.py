"""WP7 S4 focused tests: full vertical pilot (NO GWC, fake Hermes Cloud + fake Slack).

One realistic run composing WP2 runtime + WP3 routing + WP4 execution + WP5 control
plane + WP6 Slack projection, with restart-safe host state. Proves every required
vertical property, ending with the invariant proof: no duplicate root at any point.
"""

from __future__ import annotations

import pytest

from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.domain.enums import (
    BindingType,
    EventType,
    LeaseStatus,
    NodeStatus,
    RunStatus,
)
from taskcontroller.domain.ids import (
    BindingRef,
    CapabilityRef,
    ExecutionRef,
    ProducerRef,
    ProviderRef,
)
from taskcontroller.domain.models import (
    CapabilityCard,
    ExecutionProviderCard,
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
from taskcontroller.execution.ports import FakeExecutionAdapter
from taskcontroller.execution.registry import build_registry as build_adapter_registry
from taskcontroller.execution.types import AdapterSignal
from taskcontroller.packs.host_pack import SlackTaskControllerPack
from taskcontroller.packs.host_state import TaskControllerHostConfig
from taskcontroller.projections.transport import FakeSlackTransport
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

_RUN = "run.1"
_NODE = "n1"
_EXEC = "exec.1"
_ATT = "att.1"
_LEASE = "lease.1"
_PROV = "prov.1"
_FENCE = "fence.1"
_NOW = "2026-08-14T10:00:00Z"
_EXPIRES = "2026-08-14T11:00:00Z"


def _store_with_lease(fence=_FENCE, version=5, status=RunStatus.RUNNING.value):
    lease = WorkLease(
        lease_id=_LEASE, run_id=_RUN, node_id=_NODE, execution_id=_EXEC,
        attempt_id=_ATT, holder=ProviderRef(provider_id=_PROV),
        fencing_token=fence, granted_at=_NOW, expires_at=_EXPIRES,
        status=LeaseStatus.ACTIVE.value,
    )
    run = TeamRunState(
        run_id=_RUN, status=status,
        nodes={_NODE: NodeState(status=NodeStatus.RUNNING.value, contract_ref="ctr.1",
                                current_attempt=1, lease_ref=_LEASE, artifact_refs=[])},
        active_attempts=[_ATT], active_leases=[_LEASE],
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={_ATT: make_attempt_record(
            attempt_id=_ATT, run_id=_RUN, node_id=_NODE, execution_id=_EXEC,
            fencing_token=fence, current_attempt_number=1, current_lease_id=_LEASE)},
        leases=RuntimeLeaseState(leases={_LEASE: lease}),
        stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=0,
    )
    store = InMemoryStateStore()
    # fresh store starts at current version -1; first put must CAS against -1.
    # the stored state.version is set to `version` (the logical version).
    store.put_run(VersionedRunState(state=run, version=version, meta=meta), -1)
    return store


def _route_adapter_registry():
    prov = ExecutionProviderCard(
        provider_id=_PROV, provider_kind="LOCAL", capability_refs=[CapabilityRef("cap.gen")],
        environment=None,
        bindings=[Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="ipc://l", binding_id="b1")],
        trust_tier="STANDARD", cost_class="FREE",
    )
    cap = CapabilityCard(capability_id="cap.gen", name="g", version="1.0.0", idempotency="NON_IDEMPOTENT",
                         cost_class="FREE", required_environment=EnvironmentRequirement(),
                         supported_binding_types=[BindingType.LOCAL_IPC.value])
    return build_route_registry([prov], [cap]), build_adapter_registry([FakeExecutionAdapter(adapter_key="fake.hermes")])


def _host(store, state=None):
    cfg = TaskControllerHostConfig(run_id=_RUN, task_id="t1", executor_profile="HERMES_CLOUD")
    return SlackTaskControllerPack(cfg, ControlPlane(store), FakeSlackTransport(), host_state=state)


class TestVerticalPilot:
    def test_initial_projection_creates_root(self):
        store = _store_with_lease()
        host = _host(store)
        host.materialize(session_id="s1")
        assert host._transport.roots_created == ["root.run.1"]

    def test_route_then_dispatch_exactly_once(self):
        store = _store_with_lease()
        host = _host(store)
        route_reg, adap_reg = _route_adapter_registry()
        req = ExecutionRequest(
            execution_id=_EXEC, contract_ref="ctr.1", attempt=1, attempt_id=_ATT,
            fencing_token=_FENCE, capability_requirements=CapabilityRequirement(capability_id="cap.gen"),
            environment_requirements=EnvironmentRequirement(), routing_preferences=RoutingPref(),
        )
        receipt, ack = host.route_and_dispatch(
            route_reg, req, "rcpt.1", LeaseManager(store), adap_reg, _NODE, _NOW,
            accepted_at=_NOW, command_id="cmd.dispatch",
        )
        assert ack.status == "ACCEPTED"
        assert len(adap_reg.lookup_by_key("fake.hermes").dispatched) == 1

    def test_progress_signal_through_wp2_updates_same_root(self):
        store = _store_with_lease()
        host = _host(store)
        host.materialize(session_id="s1")
        router = EventRouter(store)
        sig = AdapterSignal(
            event_id="evt.p1", event_type=EventType.PROGRESS.value, sequence=0,
            execution_ref=ExecutionRef(execution_id=_EXEC, attempt=1, attempt_id=_ATT, fencing_token=_FENCE),
            node_id=_NODE, run_id=_RUN, fencing_token=_FENCE, provider_id=_PROV,
            idempotency_key="idk.p1", timestamp=_NOW, payload={"note": "progress"}, artifact_refs=[],
        )
        host.forward_signal(sig, router, store)
        host.materialize(session_id="s1")
        assert host._transport.roots_created == ["root.run.1"]
        assert len(host._transport.roots_updated) >= 1

    def test_completed_signal_at_most_reviewing_never_done(self):
        store = _store_with_lease()
        host = _host(store)
        router = EventRouter(store)
        sig = AdapterSignal(
            event_id="evt.c1", event_type=EventType.COMPLETED.value, sequence=0,
            execution_ref=ExecutionRef(execution_id=_EXEC, attempt=1, attempt_id=_ATT, fencing_token=_FENCE),
            node_id=_NODE, run_id=_RUN, fencing_token=_FENCE, provider_id=_PROV,
            idempotency_key="idk.c1", timestamp=_NOW, payload={}, artifact_refs=[],
        )
        host.forward_signal(sig, router, store)
        node = store.get_run(_RUN).state.nodes[_NODE]
        assert node.status == NodeStatus.REVIEWING.value  # at most REVIEWING
        assert node.status != NodeStatus.DONE.value  # never auto-DONE
        assert store.get_run(_RUN).state.status == RunStatus.RUNNING.value

    def test_pause_resume_round_trip_same_root(self):
        store = _store_with_lease()
        host = _host(store)
        host.materialize(session_id="s1")
        host.controller_action("PAUSE", expected_version=store.get_run(_RUN).version, command_id="cmd.p")
        host.controller_action("RESUME", expected_version=store.get_run(_RUN).version, command_id="cmd.r")
        assert host._transport.root_count() == 1
        assert host._transport.roots_created == ["root.run.1"]

    def test_stale_signal_after_lease_replacement_rejected(self):
        store = _store_with_lease(fence=_FENCE)
        host = _host(store)
        router = EventRouter(store)
        new_fence = "fence.2"
        lease2 = WorkLease(
            lease_id="lease.2", run_id=_RUN, node_id=_NODE, execution_id=_EXEC,
            attempt_id=_ATT, holder=ProviderRef(provider_id=_PROV),
            fencing_token=new_fence, granted_at=_NOW, expires_at=_EXPIRES,
            status=LeaseStatus.ACTIVE.value,
        )
        live = store.get_run(_RUN)
        store.put_run(VersionedRunState(
            state=TeamRunState(
                run_id=_RUN, status=RunStatus.RUNNING.value,
                nodes={_NODE: NodeState(status=NodeStatus.RUNNING.value, contract_ref="ctr.1",
                                        current_attempt=1, lease_ref="lease.2", artifact_refs=[])},
                active_attempts=[_ATT], active_leases=["lease.2"]),
            version=live.version + 1,
            meta=RuntimeSnapshotMeta(
                attempt_registry={_ATT: make_attempt_record(
                    attempt_id=_ATT, run_id=_RUN, node_id=_NODE, execution_id=_EXEC,
                    fencing_token=new_fence, current_attempt_number=1, current_lease_id="lease.2")},
                leases=RuntimeLeaseState(leases={"lease.2": lease2}),
                stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=0),
        ), live.version)
        sig = AdapterSignal(
            event_id="evt.stale", event_type=EventType.PROGRESS.value, sequence=0,
            execution_ref=ExecutionRef(execution_id=_EXEC, attempt=1, attempt_id=_ATT, fencing_token=_FENCE),
            node_id=_NODE, run_id=_RUN, fencing_token=_FENCE, provider_id=_PROV,
            idempotency_key="idk.stale", timestamp=_NOW, payload={}, artifact_refs=[],
        )
        with pytest.raises(Exception):
            host.forward_signal(sig, router, store)
        assert host._transport.roots_created == []

    def test_approve_merge_authority_only_no_mutation(self):
        store = _store_with_lease()
        host = _host(store)
        host.materialize(session_id="s1")
        before = store.get_run(_RUN).state.status
        res = host.controller_action("APPROVE", expected_version=store.get_run(_RUN).version)
        assert res["authority_required"] is True
        assert store.get_run(_RUN).state.status == before
        assert host._transport.roots_created == ["root.run.1"]

    def test_restart_mid_run_restores_root_and_continues(self):
        store = _store_with_lease()
        host = _host(store)
        host.materialize(session_id="s1")
        persisted = host.checkpoint_host_state()
        b = SlackTaskControllerPack.restore(persisted, ControlPlane(store), FakeSlackTransport())
        b.materialize(session_id="s9")
        b.controller_action("PAUSE", expected_version=store.get_run(_RUN).version, command_id="cmd.pr")
        # restart restored the SAME root; no new root ever created across restart
        assert b._transport.roots_created == []
        # the existing root continues to be updated (>=1 UPDATE_ROOT)
        assert len(b._transport.roots_updated) >= 1

    def test_no_duplicate_root_at_any_point(self):
        store = _store_with_lease()
        host = _host(store)
        host.materialize(session_id="s1")
        host.controller_action("PAUSE", expected_version=store.get_run(_RUN).version, command_id="cmd.p")
        host.rotate(session_id="s2")
        persisted = host.checkpoint_host_state()
        b = SlackTaskControllerPack.restore(persisted, ControlPlane(store), FakeSlackTransport())
        b.materialize(session_id="s9")
        assert host._transport.root_count() == 1
        assert b._transport.roots_created == []
