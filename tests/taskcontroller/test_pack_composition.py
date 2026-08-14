"""WP7 S2 focused tests: host composition lifecycle (NO GWC, fake transport)."""

from __future__ import annotations

from taskcontroller.controlplane.orchestrator import ControlPlane
from taskcontroller.controlplane.projection import RunProjection
from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.domain.values import NodeState
from taskcontroller.packs.host_pack import SlackTaskControllerPack
from taskcontroller.packs.host_state import TaskControllerHostConfig, TaskControllerHostState
from taskcontroller.projections.binding import DuplicateRootError
from taskcontroller.projections.transport import FakeSlackTransport
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
)
from taskcontroller.runtime.store import InMemoryStateStore


def _store(status=RunStatus.RUNNING.value, version=5, plan="p1"):
    nodes = {
        "n1": NodeState(status=NodeStatus.RUNNING.value, contract_ref="c1", current_attempt=1, lease_ref="l1", artifact_refs=[]),
        "n2": NodeState(status=NodeStatus.DONE.value, contract_ref="c2", current_attempt=1, lease_ref=None, artifact_refs=[]),
        "n3": NodeState(status=NodeStatus.PENDING.value, contract_ref="c3", current_attempt=1, lease_ref=None, artifact_refs=[]),
    }
    state = TeamRunState(
        run_id="run.1", status=status, nodes=nodes,
        active_attempts=["att.1"], active_leases=["l1"], plan_version=plan,
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={}, leases=RuntimeLeaseState(leases={}),
        stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=2,
    )
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=state, version=version, meta=meta), -1)
    return store


def _host(state: TaskControllerHostState | None = None, store=None):
    store = store or _store()
    cfg = TaskControllerHostConfig(run_id="run.1", task_id="t1")
    return SlackTaskControllerPack(cfg, ControlPlane(store), FakeSlackTransport(), host_state=state), store


class TestCompositionLifecycle:
    def test_materialize_creates_one_root(self):
        host, _ = _host()
        host.materialize(session_id="s1")
        # one root created, no second
        assert host.root_count() == 1

    def test_route_and_dispatch_delegates_to_wp3_wp4(self):
        # verify the host does not duplicate authority: it calls route_and_dispatch
        # and returns its result unchanged. We exercise the real path minimally.
        host, store = _host()
        # the host composes; ensure calling the delegate works and returns a tuple
        from taskcontroller.domain.enums import BindingType, LeaseStatus
        from taskcontroller.domain.ids import BindingRef, CapabilityRef, ProviderRef
        from taskcontroller.domain.models import (
            CapabilityCard, ExecutionProviderCard, ExecutionReceipt, ExecutionRequest,
        )
        from taskcontroller.domain.values import Binding, CapabilityRequirement, EnvironmentRequirement, RoutingPref
        from taskcontroller.execution.ports import FakeExecutionAdapter
        from taskcontroller.execution.registry import build_registry as build_adapter_registry
        from taskcontroller.routing.registry import build_registry as build_route_registry
        from taskcontroller.runtime.lease import LeaseManager

        prov = ExecutionProviderCard(
            provider_id="prov.1", provider_kind="LOCAL", capability_refs=[CapabilityRef("cap.gen")],
            environment=None, bindings=[Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="ipc://l", binding_id="b1")],
            trust_tier="STANDARD", cost_class="FREE",
        )
        cap = CapabilityCard(capability_id="cap.gen", name="g", version="1.0.0", idempotency="NON_IDEMPOTENT",
                             cost_class="FREE", required_environment=EnvironmentRequirement(),
                             supported_binding_types=[BindingType.LOCAL_IPC.value])
        req = ExecutionRequest(execution_id="exec.1", contract_ref="tc.1", attempt=1, attempt_id="att.1",
                               fencing_token="fence.1", capability_requirements=CapabilityRequirement(capability_id="cap.gen"),
                               environment_requirements=EnvironmentRequirement(), routing_preferences=RoutingPref())
        route_reg = build_route_registry([prov], [cap])
        adap_reg = build_adapter_registry([FakeExecutionAdapter(adapter_key="fake.1")])
        from taskcontroller.domain.enums import LeaseStatus as LS
        from taskcontroller.domain.models import WorkLease
        from taskcontroller.domain.ids import ExecutionRef
        store = _store()
        lease = WorkLease(lease_id="lease.1", run_id="run.1", node_id="n1", execution_id="exec.1", attempt_id="att.1",
                         holder=ProviderRef(provider_id="prov.1"), fencing_token="fence.1",
                         granted_at="2026-08-14T10:00:00Z", expires_at="2026-08-14T11:00:00Z", status=LS.ACTIVE.value)
        store.put_run(VersionedRunState(
            state=TeamRunState(run_id="run.1", status=RunStatus.RUNNING.value,
                               nodes={"n1": NodeState(status=NodeStatus.RUNNING.value, contract_ref="c1",
                                                      current_attempt=1, lease_ref="lease.1", artifact_refs=[])},
                               active_attempts=["att.1"], active_leases=["lease.1"]),
            version=5,
            meta=RuntimeSnapshotMeta(attempt_registry={}, leases=RuntimeLeaseState(leases={"lease.1": lease}),
                                     stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=2),
        ), 5)
        cfg = TaskControllerHostConfig(run_id="run.1", task_id="t1")
        host = SlackTaskControllerPack(cfg, ControlPlane(store), FakeSlackTransport())
        receipt, ack = host.route_and_dispatch(
            route_reg, req, "rcpt.1", LeaseManager(store), adap_reg, "n1",
            "2026-08-14T10:00:00Z", accepted_at="2026-08-14T10:00:00Z", command_id="cmd.1",
        )
        assert ack.status == "ACCEPTED"
        assert len(adap_reg.lookup_by_key("fake.1").dispatched) == 1

    def test_controller_action_round_trip_same_root(self):
        host, _ = _host()
        host.materialize()
        res = host.controller_action("PAUSE", expected_version=5, command_id="cmd.p")
        assert res["accepted"] is True
        # still exactly one root
        assert host.root_count() == 1

    def test_rotate_emits_session_rotated_thread_event(self):
        host, _ = _host()
        host.materialize()
        host.rotate(session_id="s2", model="gpt-x", executor="e2")
        # rotation: same root, thread reply emitted, no new root
        assert host.root_count() == 1
        kinds = [o["payload"].get("event_kind") for o in host._transport.ops if o["op"] == "REPLY_THREAD"]
        assert "SESSION_ROTATED" in kinds

    def test_checkpoint_then_restore_preserves_binding(self):
        host, _ = _host()
        host.materialize(session_id="s1")
        state = host.checkpoint_host_state()
        # destroy host; reconstruct from persisted state into a FRESH transport
        restored = SlackTaskControllerPack.restore(state, ControlPlane(_store()), FakeSlackTransport())
        # the restored host already holds the binding, so the next materialize is
        # an UPDATE on the SAME root, never a new CREATE_ROOT
        restored.materialize(session_id="s9")
        # no new root created in the fresh transport; existing root updated
        assert restored._transport.roots_created == []
        assert restored._transport.roots_updated == ["root.run.1"]
        # the binding identity is intact (same root, only content changed)
        assert restored.root_for("run.1") == "root.run.1"

    def test_no_direct_state_mutation_in_pack(self):
        host, store = _host()
        before = store.get_run("run.1").version
        host.materialize()
        # materialize is projection-only; it must not bump the runtime version
        assert store.get_run("run.1").version == before

    def test_second_root_attempt_fails_closed(self):
        host, _ = _host()
        host.materialize()
        with pytest.raises(DuplicateRootError):
            host.attempt_second_root()
        assert host.root_count() == 1


import pytest  # noqa: E402  (kept at end to avoid disturbing test ordering)
