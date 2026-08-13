"""WP1 version guards: plan_version + run_version stale rejection.

Applies to objects carrying plan_version / run_version entering kernel
decision-making: ExecutionRequest, ReviewResult, TaskContract, ControllerDecision.
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import RunStatus
from taskcontroller.domain.models import (
    CapabilityRequirement,
    ControllerDecision,
    ExecutionRequest,
    ReviewResult,
    ScopeSpec,
    TaskContract,
)
from taskcontroller.domain.values import CapabilityRequirement as CapReq
from taskcontroller.kernel.errors import VersionConflict
from taskcontroller.kernel.plans import check_version
from taskcontroller.kernel.transitions import is_run_terminal


# ---------------------------------------------------------------------------
# helper run state with versions
# ---------------------------------------------------------------------------

def _run_state(plan_version: str = "p1", run_version: str = "r1", status: str = RunStatus.RUNNING.value):
    from taskcontroller.domain.models import TeamRunState

    return TeamRunState(
        run_id="run.1",
        status=status,
        nodes={},
        plan_version=plan_version,
        run_version=run_version,
    )


def _task_contract(plan_version: str = "p1", run_version: str = "r1"):
    return TaskContract(
        contract_id="tc.1",
        run_id="run.1",
        node_id="n1",
        objective="x",
        scope=ScopeSpec(allowed_work=["build"]),
        acceptance_criteria=["ok"],
        capability_requirement=CapReq(capability_id="cap.build"),
        plan_version=plan_version,
        run_version=run_version,
    )


# ---------------------------------------------------------------------------
# stale version rejection (both axes)
# ---------------------------------------------------------------------------

def test_check_version_matching_ok():
    run = _run_state(plan_version="p1", run_version="r1")
    obj = _task_contract(plan_version="p1", run_version="r1")
    check_version(run, obj)


def test_check_version_stale_plan_version_rejected():
    run = _run_state(plan_version="p1", run_version="r1")
    obj = _task_contract(plan_version="p2", run_version="r1")
    with pytest.raises(VersionConflict):
        check_version(run, obj)


def test_check_version_stale_run_version_rejected():
    run = _run_state(plan_version="p1", run_version="r1")
    obj = _task_contract(plan_version="p1", run_version="r2")
    with pytest.raises(VersionConflict):
        check_version(run, obj)


def test_check_version_stale_both_rejected():
    run = _run_state(plan_version="p1", run_version="r1")
    obj = _task_contract(plan_version="p2", run_version="r2")
    with pytest.raises(VersionConflict):
        check_version(run, obj)


def test_check_version_empty_versions_match_empty_run():
    run = _run_state(plan_version="", run_version="")
    obj = _task_contract(plan_version="", run_version="")
    check_version(run, obj)


def test_check_version_empty_obj_version_matches_set_run_version():
    # obj has no version set; run has version set -> ok (obj is unconstrained)
    run = _run_state(plan_version="p1", run_version="r1")
    obj = _task_contract(plan_version="", run_version="")
    check_version(run, obj)


def test_check_version_obj_with_empty_run_version_is_ok_when_run_empty():
    run = _run_state(plan_version="p1", run_version="")
    obj = _task_contract(plan_version="p1", run_version="")
    check_version(run, obj)


def test_check_version_exec_request_version_guarded():
    run = _run_state(plan_version="p1", run_version="r1")
    from taskcontroller.domain.models import EnvironmentRequirement, RoutingPref
    from taskcontroller.domain.values import CapabilityRequirement as CReq

    req = ExecutionRequest(
        execution_id="exec.1",
        contract_ref="tc.1",
        attempt=1,
        attempt_id="att.1",
        fencing_token="ft.1",
        capability_requirements=CReq(capability_id="cap.build"),
        environment_requirements=EnvironmentRequirement(),
        routing_preferences=RoutingPref(),
        plan_version="p2",
        run_version="r1",
    )
    with pytest.raises(VersionConflict):
        check_version(run, req)


def test_check_version_review_result_version_guarded():
    run = _run_state(plan_version="p1", run_version="r1")
    rev = ReviewResult(
        review_id="rev.1",
        target_ref="n1",
        verdict="PASS",
        reviewer="human.1",
        criteria=["ok"],
        evidence_refs=["ev.1"],
        plan_version="p1",
        run_version="r2",
    )
    with pytest.raises(VersionConflict):
        check_version(run, rev)


def test_check_version_controller_decision_version_guarded():
    run = _run_state(plan_version="p1", run_version="r1")
    dec = ControllerDecision(
        decision_id="dec.1",
        run_ref="run.1",
        decision_type="CONTINUE",
        rationale="ok",
        plan_version="p2",
        run_version="r1",
    )
    with pytest.raises(VersionConflict):
        check_version(run, dec)


def test_check_version_terminal_run_still_version_guarded():
    run = _run_state(plan_version="p1", run_version="r1", status=RunStatus.COMPLETED.value)
    obj = _task_contract(plan_version="p2", run_version="r1")
    with pytest.raises(VersionConflict):
        check_version(run, obj)


def test_check_version_terminal_run_with_matching_versions_ok():
    run = _run_state(plan_version="p1", run_version="r1", status=RunStatus.CANCELLED.value)
    obj = _task_contract(plan_version="p1", run_version="r1")
    check_version(run, obj)
