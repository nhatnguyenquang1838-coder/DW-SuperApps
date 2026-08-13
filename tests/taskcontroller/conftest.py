"""Shared WP0 test fixtures (valid instances for every model)."""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import (
    ActorKind,
    BindingType,
    CostClass,
    DecisionType,
    EventType,
    ExecutionStatus,
    Idempotency,
    LeaseStatus,
    ProviderKind,
    ReviewVerdict,
    RunStatus,
    TrustTier,
)
from taskcontroller.domain.ids import (
    ArtifactRef,
    BindingRef,
    CapabilityRef,
    ExecutionRef,
    ProducerRef,
    ProviderRef,
    TaskRef,
)
from taskcontroller.domain.models import (
    AgentEvent,
    Artifact,
    CapabilityCard,
    ControllerDecision,
    ControllerHostProfile,
    ExecutionProviderCard,
    ExecutionReceipt,
    ExecutionRequest,
    ReviewResult,
    TaskContract,
    TeamRunState,
    WorkLease,
)
from taskcontroller.domain.values import (
    Binding,
    Checkpoint,
    EnvironmentInfo,
    EnvironmentRequirement,
    EventCursor,
    EvidenceSpec,
    InputRef,
    NodeState,
    Permission,
    Provenance,
    ReportingSpec,
    RetryPolicy,
    RoutingPref,
    ScopeSpec,
    ArtifactSpec,
    CapabilityRequirement,
)


@pytest.fixture
def cap_req():
    return CapabilityRequirement(
        capability_id="cap.build", idempotency="IDEMPOTENT", cost_class="LOW"
    )


@pytest.fixture
def binding():
    return Binding(kind="HTTP_API", endpoint_ref="https://prov/agent", protocol="a2a")


@pytest.fixture
def host_profile(binding):
    return ControllerHostProfile(
        host_id="host.ctrl",
        actor_kind=ActorKind.CONTROLLER.value,
        trust_tier=TrustTier.TRUSTED.value,
        environment=EnvironmentInfo(os="linux", runtime="python3.11"),
        bindings=[binding],
        capabilities=[CapabilityRef("cap.build")],
    )


@pytest.fixture
def capability_card():
    return CapabilityCard(
        capability_id="cap.build",
        name="Build Package",
        version="1.0.0",
        idempotency=Idempotency.IDEMPOTENT.value,
        cost_class=CostClass.LOW.value,
        required_environment=EnvironmentRequirement(runtime="python3.11"),
        supported_binding_types=[BindingType.HTTP_API.value],
    )


@pytest.fixture
def provider_card(binding):
    return ExecutionProviderCard(
        provider_id="prov.local.chatgpt.py",
        provider_kind=ProviderKind.LOCAL.value,
        capability_refs=[CapabilityRef("cap.build")],
        environment=EnvironmentInfo(runtime="python3.11"),
        bindings=[binding],
        trust_tier=TrustTier.STANDARD.value,
        cost_class=CostClass.FREE.value,
    )


@pytest.fixture
def task_contract(cap_req):
    return TaskContract(
        contract_id="tc.1",
        run_id="run.1",
        node_id="node.a",
        objective="Build the distribution",
        scope=ScopeSpec(allowed_work=["compile"], forbidden_actions=["deploy"]),
        acceptance_criteria=["artifact produced"],
        capability_requirement=cap_req,
        dependencies=[],
        required_evidence=[EvidenceSpec(evidence_id="ev.1", description="log")],
        reporting=ReportingSpec(milestones=["start", "done"], after_report="AWAIT_REVIEW"),
        priority="HIGH",
        plan_version="p1",
        run_version="r1",
    )


@pytest.fixture
def exec_request(cap_req):
    return ExecutionRequest(
        execution_id="exec.1",
        contract_ref="tc.1",
        attempt=1,
        attempt_id="att.1",
        fencing_token="ft-abc",
        capability_requirements=cap_req,
        environment_requirements=EnvironmentRequirement(runtime="python3.11"),
        routing_preferences=RoutingPref(locality="ANY", remote_fallback=True),
        inputs=[InputRef(input_id="in.1", source_ref="src/code")],
        permissions=Permission(boundaries=["no_network"]),
        expected_outputs=[ArtifactSpec(artifact_id="out.1", media_type="application/zip")],
        retry=RetryPolicy(timeout_seconds=60, max_attempts=3),
        plan_version="p1",
        run_version="r1",
    )


@pytest.fixture
def exec_receipt():
    return ExecutionReceipt(
        receipt_id="rcpt.1",
        contract_ref="tc.1",
        execution_ref=ExecutionRef(
            execution_id="exec.1", attempt=1, attempt_id="att.1", fencing_token="ft-abc"
        ),
        selected_provider=ProviderRef("prov.local.chatgpt.py"),
        binding=BindingRef("b.1"),
        status=ExecutionStatus.ROUTING.value,
        accepted_at="2026-08-13T00:00:00Z",
    )


@pytest.fixture
def agent_event():
    return AgentEvent(
        event_id="evt.1",
        run_id="run.1",
        node_id="node.a",
        execution_id="exec.1",
        attempt_id="att.1",
        fencing_token="ft-abc",
        sequence=1,
        event_type=EventType.TASK_STARTED.value,
        producer=ProducerRef("prov.local.chatgpt.py"),
        timestamp="2026-08-13T00:00:01Z",
        idempotency_key="idem.1",
        payload={"msg": "started"},
        artifact_refs=[ArtifactRef("out.1")],
    )


@pytest.fixture
def artifact():
    return Artifact(
        artifact_id="out.1",
        content_ref="s3://bucket/out.zip",
        media_type="application/zip",
        provenance=Provenance(
            producer="prov.local.chatgpt.py",
            produced_at="2026-08-13T00:01:00Z",
            source_ref="src/code",
            digest="sha256:abc",
            schema_ref="schemas/artifact",
            schema_version="1",
            execution_ref="exec.1",
            attempt_id="att.1",
            fencing_token="ft-abc",
        ),
        digest="sha256:abc",
        schema_ref="schemas/artifact",
        schema_version="1",
    )


@pytest.fixture
def review_result():
    return ReviewResult(
        review_id="rev.1",
        target_ref="out.1",
        verdict=ReviewVerdict.PASS.value,
        reviewer="human.1",
        criteria=["compiles"],
        score=0.95,
        evidence_refs=["ev.1"],
        plan_version="p1",
        run_version="r1",
    )


@pytest.fixture
def work_lease():
    return WorkLease(
        lease_id="lease.1",
        run_id="run.1",
        node_id="node.a",
        execution_id="exec.1",
        attempt_id="att.1",
        holder=ProviderRef("prov.local.chatgpt.py"),
        fencing_token="ft-abc",
        granted_at="2026-08-13T00:00:00Z",
        expires_at="2026-08-13T01:00:00Z",
        resource_ref="node.a",
        status=LeaseStatus.ACTIVE.value,
    )


@pytest.fixture
def team_run_state(work_lease):
    return TeamRunState(
        run_id="run.1",
        status=RunStatus.RUNNING.value,
        nodes={
            "node.a": NodeState(
                status="RUNNING",
                contract_ref="tc.1",
                current_attempt=1,
                lease_ref="lease.1",
                artifact_refs=["out.1"],
            )
        },
        active_attempts=["exec.1"],
        active_leases=["lease.1"],
        artifact_refs=["out.1"],
        last_event_cursor=EventCursor(last_event_id="evt.1", sequence=1),
        checkpoint=Checkpoint(state_version=1, checkpoint_ref="ck.1"),
        plan_version="p1",
        run_version="r1",
        updated_at="2026-08-13T00:01:00Z",
    )


@pytest.fixture
def controller_decision():
    return ControllerDecision(
        decision_id="dec.1",
        run_ref="run.1",
        decision_type=DecisionType.CONTINUE.value,
        rationale="node progressed",
        selected_option="opt.1",
        evidence_refs=["evt.1"],
        plan_version="p1",
        run_version="r1",
    )
