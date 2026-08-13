"""WP0 model construction + invariant tests."""

from __future__ import annotations

import pytest

from taskcontroller.errors import TaskControllerValidationError


def test_task_contract_requires_acceptance_criteria(task_contract):
    assert task_contract.contract_id == "tc.1"
    assert task_contract.run_version == "r1"


def test_task_contract_rejects_self_dependency(cap_req):
    from taskcontroller.domain.ids import TaskRef
    from taskcontroller.domain.models import TaskContract
    from taskcontroller.domain.values import ScopeSpec

    # empty acceptance criteria is rejected
    with pytest.raises(TaskControllerValidationError):
        TaskContract(
            contract_id="tc.2",
            run_id="run.1",
            node_id="node.a",
            objective="x",
            scope=ScopeSpec(),
            acceptance_criteria=[],
            capability_requirement=cap_req,
            dependencies=[],
        )
    # self-dependency
    with pytest.raises(TaskControllerValidationError):
        TaskContract(
            contract_id="tc.2",
            run_id="run.1",
            node_id="node.a",
            objective="x",
            scope=ScopeSpec(),
            acceptance_criteria=["ok"],
            capability_requirement=cap_req,
            dependencies=[TaskRef(run_id="run.1", node_id="node.a")],
        )


def test_execution_request_requires_attempt_gte_1(exec_request):
    assert exec_request.attempt == 1
    from taskcontroller.domain.models import ExecutionRequest

    bad = exec_request.__dict__.copy()
    # build via from_dict with attempt=0
    d = exec_request.to_dict()
    d["attempt"] = 0
    with pytest.raises(TaskControllerValidationError):
        ExecutionRequest.from_dict(d)


def test_execution_receipt_uses_generic_provider(exec_receipt):
    # selected_provider is generic ProviderRef, NOT an agent-only ref
    assert exec_receipt.selected_provider.provider_id == "prov.local.chatgpt.py"


def test_work_lease_holder_is_provider_ref(work_lease):
    assert work_lease.holder.provider_id == "prov.local.chatgpt.py"


def test_unknown_enum_value_rejected(host_profile):
    from taskcontroller.domain.models import ControllerHostProfile

    d = host_profile.to_dict()
    d["actor_kind"] = "ROBOT"  # not in enum
    with pytest.raises(TaskControllerValidationError):
        ControllerHostProfile.from_dict(d)


def test_node_status_wide_enum_accepts_all():
    from taskcontroller.domain.enums import NodeStatus

    for v in ["PENDING", "READY", "CLAIMED", "RUNNING", "REVIEWING", "DONE",
              "BLOCKED", "FAILED", "RETRY_READY", "CANCELLED", "LEASE_EXPIRED"]:
        assert NodeStatus(v).value == v


def test_run_status_wide_enum_accepts_all():
    from taskcontroller.domain.enums import RunStatus

    for v in ["CREATED", "PLANNED", "RUNNING", "PAUSED", "BLOCKED", "COMPLETED",
              "FAILED", "CANCELLED"]:
        assert RunStatus(v).value == v


def test_review_verdict_values():
    from taskcontroller.domain.enums import ReviewVerdict

    for v in ["PASS", "FAIL", "NEEDS_FIX", "NEEDS_CLARIFICATION"]:
        assert ReviewVerdict(v).value == v


def test_decision_type_values():
    from taskcontroller.domain.enums import DecisionType

    for v in ["CONTINUE", "WAIT", "RETRY", "REPLAN", "CANCEL", "COMPLETE", "ESCALATE"]:
        assert DecisionType(v).value == v
