from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskcontroller.domain.runtime_plan import (
    AuthorityRequirement,
    PlanEdge,
    RunCursor,
    RuntimePlan,
    RuntimePlanStep,
)
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.runtime.closed_loop_runtime_executor import (
    ClosedLoopRuntimeError,
    ClosedLoopRuntimeExecutor,
    FileRuntimeExecutionStateStore,
    RuntimeExecutionState,
)
from taskcontroller.runtime.evidence_record import EvidenceRecord, EvidenceRecordError


def _runtime_plan(*, action: str = "read", task_id: str = "TASK-A") -> RuntimePlan:
    return RuntimePlan(
        runtime_plan_ref="plan.safety-b/r1",
        revision="revision-safety-b",
        task_id=task_id,
        source_bindings={
            "repository": "repo-A",
            "base_sha": "base-A",
            "head_sha": "head-A",
            "scope_hash": "scope-A",
        },
        authority_requirements=(
            AuthorityRequirement(action=action, gate="G4", required=True),
        ),
        steps={
            "inspect": RuntimePlanStep(
                step_id="inspect",
                semantic_action=action or "noop",
                terminal=True,
                allowed_actions=(action,) if action else (),
            )
        },
    )


def _cursor(plan: RuntimePlan, *, run_id: str = "run-A") -> RunCursor:
    return RunCursor(
        run_id=run_id,
        runtime_plan_ref=plan.runtime_plan_ref,
        runtime_plan_digest=plan.runtime_plan_digest,
        plan_revision=plan.revision,
        current_step_id="inspect",
    )


def _authority_context(*, task_id: str = "TASK-A") -> dict[str, str]:
    return {
        "task_id": task_id,
        "repository": "repo-A",
        "base_sha": "base-A",
        "head_sha": "head-A",
        "scope_hash": "scope-A",
        "expires_at": "2099-01-01T00:00:00Z",
    }


def test_executor_recomputes_plan_digest_without_durable_state():
    plan = _runtime_plan()
    payload = plan.to_dict()
    payload["steps"]["inspect"]["semantic_action"] = "tampered"

    with pytest.raises(ClosedLoopRuntimeError, match="digest"):
        ClosedLoopRuntimeExecutor(payload, _cursor(plan))


def test_step_context_must_match_runtime_plan_identity():
    plan = _runtime_plan(action="write", task_id="TASK-A")
    effects: list[str] = []
    executor = ClosedLoopRuntimeExecutor(
        plan.to_dict(),
        _cursor(plan),
        authority_checker=lambda _context: True,
        authority_context=_authority_context(task_id="TASK-B"),
    )

    with pytest.raises(ClosedLoopRuntimeError):
        executor.execute_step(
            "inspect",
            {},
            requested_action="write",
            effect=lambda _payload: effects.append("effect"),
        )

    assert effects == []


def test_authority_denied_overrides_approved_true():
    plan = _runtime_plan(action="write")
    effects: list[str] = []
    executor = ClosedLoopRuntimeExecutor(
        plan.to_dict(),
        _cursor(plan),
        authority_checker=lambda _context: {"decision": "DENIED", "approved": True},
        authority_context=_authority_context(),
    )

    with pytest.raises(ClosedLoopRuntimeError, match="AUTHORITY_REQUIRED"):
        executor.execute_step(
            "inspect",
            {},
            requested_action="write",
            effect=lambda _payload: effects.append("effect"),
        )

    assert effects == []


def test_effect_fails_closed_when_allowed_actions_empty_without_checker():
    plan = _runtime_plan(action="")
    effects: list[str] = []
    executor = ClosedLoopRuntimeExecutor(plan.to_dict(), _cursor(plan))

    with pytest.raises(ClosedLoopRuntimeError):
        executor.execute_step(
            "inspect",
            {},
            effect=lambda _payload: effects.append("effect"),
            side_effect=lambda: effects.append("side_effect"),
        )

    assert effects == []


def test_recovery_cursor_rejects_cross_run_prior_state(tmp_path: Path):
    plan = _runtime_plan()
    cursor_a = _cursor(plan, run_id="run-A")
    cursor_b = _cursor(plan, run_id="run-B")
    state_b = RuntimeExecutionState(
        run_id="run-B",
        runtime_plan_ref=plan.runtime_plan_ref,
        runtime_plan_digest=plan.runtime_plan_digest,
        plan_revision=plan.revision,
        cursor=cursor_b,
    )
    # Simulate a tampered/cross-run record at the requested run-A path.
    (tmp_path / "run-A.json").write_text(
        json.dumps(state_b.to_dict()), encoding="utf-8"
    )

    with pytest.raises(ClosedLoopRuntimeError, match="run_id"):
        ClosedLoopRuntimeExecutor(
            plan.to_dict(),
            cursor_a,
            state_store=FileRuntimeExecutionStateStore(tmp_path),
        )


def test_string_false_is_not_truthy_for_runtime_executable():
    with pytest.raises(TaskControllerValidationError):
        PlanEdge.from_dict(
            {
                "outcome": "NEXT",
                "target": "terminal",
                "kind": "terminal",
                "runtime_executable": "false",
            }
        )


def test_evidence_record_rejects_string_boolean():
    with pytest.raises(EvidenceRecordError, match="bool"):
        EvidenceRecord.from_dict({"authority_revalidated": "false"})
