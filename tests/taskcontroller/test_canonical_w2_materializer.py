from __future__ import annotations

import pytest

from taskcontroller.domain.enums import BindingType, LeaseStatus, NodeStatus, RunStatus
from taskcontroller.domain.ids import BindingRef, ExecutionRef, ProviderRef
from taskcontroller.domain.models import (
    ExecutionProviderCard,
    ExecutionReceipt,
    ExecutionRequest,
    TeamRunState,
    WorkLease,
)
from taskcontroller.domain.runtime_plan import (
    FilePlanStore,
    PlanEdge,
    RunCursor,
    RuntimePlan,
    RuntimePlanStep,
)
from taskcontroller.domain.values import Binding, CapabilityRequirement, EnvironmentRequirement, NodeState, RoutingPref
from taskcontroller.execution.fabric import ExecutionFabric
from taskcontroller.execution.ports import FakeExecutionAdapter
from taskcontroller.execution.registry import build_registry
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.runtime_state import RuntimeLeaseState, RuntimeSnapshotMeta, VersionedRunState, make_attempt_record
from taskcontroller.runtime.materializer import StepMaterializer


PLAN_REF = "runtime-plan/run.671"
RUN_ID = "run.671"
STEP_ID = "STEP-001"
EXEC_ID = "exec.671"
ATTEMPT_ID = "att.671"
NODE_ID = "node.671"
PROVIDER_ID = "provider.671"
FENCE = "fence.671"
NOW = "2026-09-01T00:00:00+00:00"


def _plan() -> RuntimePlan:
    return RuntimePlan(
        runtime_plan_ref=PLAN_REF,
        revision="r7",
        steps={
            STEP_ID: RuntimePlanStep(
                step_id=STEP_ID,
                semantic_action="inspect",
                allowed_inputs=("input.current",),
                allowed_actions=("read", "report"),
                evidence_refs=("evidence.plan",),
                edges={"PASS": PlanEdge(outcome="PASS", target="terminal")},
            ),
            "STEP-002": RuntimePlanStep(
                step_id="STEP-002",
                semantic_action="later",
                allowed_inputs=("input.later",),
                allowed_actions=("write",),
                evidence_refs=("evidence.later",),
            ),
        },
    )


def _cursor(plan: RuntimePlan) -> RunCursor:
    return RunCursor(
        run_id=RUN_ID,
        runtime_plan_ref=PLAN_REF,
        runtime_plan_digest=plan.runtime_plan_digest,
        plan_revision=plan.revision,
        current_step_id=STEP_ID,
    )


def test_step_materializer_loads_durable_plan_and_exposes_only_current_step(tmp_path):
    plan = _plan()
    FilePlanStore(tmp_path).put(plan)

    context = StepMaterializer(FilePlanStore(tmp_path)).materialize(
        _cursor(plan), evidence_refs=("evidence.plan", "evidence.runtime")
    )

    assert context.runtime_plan_ref == PLAN_REF
    assert context.runtime_plan_digest == plan.runtime_plan_digest
    assert context.plan_revision == "r7"
    assert context.step_id == STEP_ID
    assert context.allowed_inputs == ("input.current",)
    assert context.allowed_actions == ("read", "report")
    assert context.evidence_refs == ("evidence.plan", "evidence.runtime")
    assert "steps" not in context.to_dict()
    assert "conversation" not in context.to_dict()
    assert not hasattr(context, "plan")


def test_step_materializer_rejects_evidence_not_declared_by_current_step(tmp_path):
    plan = _plan()
    store = FilePlanStore(tmp_path)
    store.put(plan)

    with pytest.raises(TaskControllerValidationError, match="evidence"):
        StepMaterializer(store).materialize(
            _cursor(plan), evidence_refs=("evidence.other-step",)
        )


def _dispatch_parts(tmp_path):
    plan = _plan()
    FilePlanStore(tmp_path).put(plan)
    cursor = _cursor(plan)
    lease = WorkLease(
        lease_id="lease.671",
        run_id=RUN_ID,
        node_id=NODE_ID,
        execution_id=EXEC_ID,
        attempt_id=ATTEMPT_ID,
        holder=ProviderRef(provider_id=PROVIDER_ID),
        fencing_token=FENCE,
        granted_at=NOW,
        expires_at="2026-09-01T01:00:00+00:00",
        status=LeaseStatus.ACTIVE.value,
    )
    run = TeamRunState(
        run_id=RUN_ID,
        status=RunStatus.RUNNING.value,
        nodes={NODE_ID: NodeState(status=NodeStatus.RUNNING.value, contract_ref="contract.671", current_attempt=1, lease_ref=lease.lease_id, artifact_refs=[])},
        active_attempts=[ATTEMPT_ID],
        active_leases=[lease.lease_id],
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={ATTEMPT_ID: make_attempt_record(attempt_id=ATTEMPT_ID, run_id=RUN_ID, node_id=NODE_ID, execution_id=EXEC_ID, fencing_token=FENCE, current_attempt_number=1, current_lease_id=lease.lease_id)},
        leases=RuntimeLeaseState(leases={lease.lease_id: lease}),
        stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=0,
    )
    state_store = __import__("taskcontroller.runtime.store", fromlist=["InMemoryStateStore"]).InMemoryStateStore()
    state_store.put_run(VersionedRunState(state=run, version=1, meta=meta), -1)
    provider = ExecutionProviderCard(
        provider_id=PROVIDER_ID, provider_kind="LOCAL", capability_refs=[], environment=None,
        bindings=[Binding(kind=BindingType.LOCAL_IPC.value, endpoint_ref="ipc://671", binding_id="binding.671")],
        trust_tier="STANDARD", cost_class="FREE",
    )
    request = ExecutionRequest(
        execution_id=EXEC_ID, contract_ref="contract.671", attempt=1, attempt_id=ATTEMPT_ID,
        fencing_token=FENCE, capability_requirements=CapabilityRequirement(capability_id="cap.671"),
        environment_requirements=EnvironmentRequirement(), routing_preferences=RoutingPref(),
    )
    receipt = ExecutionReceipt(
        receipt_id="receipt.671", contract_ref="contract.671",
        execution_ref=ExecutionRef(execution_id=EXEC_ID, attempt=1, attempt_id=ATTEMPT_ID, fencing_token=FENCE),
        selected_provider=ProviderRef(provider_id=PROVIDER_ID), binding=BindingRef("binding.671"), status="ROUTING",
    )
    adapter = FakeExecutionAdapter(adapter_key="fake.671", binding_type=BindingType.LOCAL_IPC.value)
    fabric = ExecutionFabric(build_registry([adapter]), LeaseManager(state_store))
    return plan, cursor, fabric, adapter, request, receipt, provider


def test_semantic_dispatch_missing_binding_fails_before_provider_dispatch(tmp_path):
    plan, cursor, fabric, adapter, request, receipt, provider = _dispatch_parts(tmp_path)

    with pytest.raises(TaskControllerValidationError, match="runtime plan binding"):
        fabric.dispatch_semantic(
            request, receipt, provider, RUN_ID, NODE_ID, "command.671", NOW,
            runtime_plan=plan, run_cursor=cursor, evidence_refs=("evidence.plan",),
            runtime_plan_ref=None, runtime_plan_digest=plan.runtime_plan_digest,
            plan_revision=plan.revision, step_id=STEP_ID,
        )

    assert adapter.dispatched == []


def test_semantic_dispatch_passes_bounded_current_step_context(tmp_path):
    plan, cursor, fabric, adapter, request, receipt, provider = _dispatch_parts(tmp_path)

    ack = fabric.dispatch_semantic(
        request, receipt, provider, RUN_ID, NODE_ID, "command.671", NOW,
        runtime_plan=plan, run_cursor=cursor, evidence_refs=("evidence.plan",),
        runtime_plan_ref=PLAN_REF, runtime_plan_digest=plan.runtime_plan_digest,
        plan_revision=plan.revision, step_id=STEP_ID,
    )

    assert ack.status == "ACCEPTED"
    assert len(adapter.dispatched) == 1
    context = adapter.dispatched[0].context
    assert context.step_id == STEP_ID
    assert context.allowed_inputs == ("input.current",)
    assert context.allowed_actions == ("read", "report")
    assert context.evidence_refs == ("evidence.plan",)
    assert not hasattr(context, "plan")
    assert "conversation" not in context.to_dict()
