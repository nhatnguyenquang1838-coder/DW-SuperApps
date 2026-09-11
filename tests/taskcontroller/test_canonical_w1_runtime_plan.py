from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskcontroller.domain.runtime_plan import (
    BindingErrorCode,
    FilePlanStore,
    PlanEdge,
    RunCursor,
    RuntimePlan,
    RuntimePlanStep,
    require_semantic_binding,
)
from taskcontroller.errors import TaskControllerValidationError


PLAN_REF = "runtime-plan/run.1"
PLAN_DIGEST = "sha256:placeholder"


def _plan() -> RuntimePlan:
    return RuntimePlan(
        runtime_plan_ref=PLAN_REF,
        revision="r1",
        steps={
            "STEP-001": RuntimePlanStep(
                step_id="STEP-001",
                semantic_action="inspect",
                edges={"PASS": PlanEdge(outcome="PASS", target="STEP-002")},
            ),
            "STEP-002": RuntimePlanStep(
                step_id="STEP-002",
                semantic_action="validate",
                edges={"PASS": PlanEdge(outcome="PASS", target="terminal")},
            ),
        },
    )


def test_runtime_plan_has_deterministic_immutable_digest():
    first = _plan()
    second = RuntimePlan(
        runtime_plan_ref=PLAN_REF,
        revision="r1",
        steps=dict(reversed(list(_plan().steps.items()))),
    )

    assert first.runtime_plan_digest == second.runtime_plan_digest
    with pytest.raises(TypeError):
        first.steps["STEP-003"] = RuntimePlanStep(
            step_id="STEP-003", semantic_action="other"
        )


def test_runtime_plan_rejects_authority_grant():
    with pytest.raises(TaskControllerValidationError, match="authority_granted"):
        RuntimePlan.from_dict(
            {
                "runtime_plan_ref": PLAN_REF,
                "revision": "r1",
                "authority_granted": True,
                "steps": {},
            }
        )


def test_runtime_plan_rejects_undeclared_edge():
    plan = _plan()
    with pytest.raises(TaskControllerValidationError) as exc:
        plan.resolve_edge("STEP-001", "FAIL")
    assert str(exc.value).startswith(BindingErrorCode.EDGE_NOT_ALLOWED)


def test_runtime_plan_rejects_missing_step():
    with pytest.raises(TaskControllerValidationError) as exc:
        _plan().step("STEP-999")
    assert str(exc.value).startswith(BindingErrorCode.STEP_MISSING)


def test_semantic_binding_requires_all_identity_fields():
    plan = _plan()
    for kwargs in (
        {"runtime_plan_ref": None, "runtime_plan_digest": plan.runtime_plan_digest, "step_id": "STEP-001"},
        {"runtime_plan_ref": PLAN_REF, "runtime_plan_digest": None, "step_id": "STEP-001"},
        {"runtime_plan_ref": PLAN_REF, "runtime_plan_digest": plan.runtime_plan_digest, "step_id": None},
    ):
        with pytest.raises(TaskControllerValidationError) as exc:
            require_semantic_binding(plan, **kwargs)
        assert str(exc.value).startswith(BindingErrorCode.PLAN_REQUIRED)


def test_semantic_binding_rejects_stale_digest_and_step():
    plan = _plan()
    with pytest.raises(TaskControllerValidationError) as digest_error:
        require_semantic_binding(
            plan,
            runtime_plan_ref=PLAN_REF,
            runtime_plan_digest="sha256:stale",
            step_id="STEP-001",
        )
    assert str(digest_error.value).startswith(BindingErrorCode.DIGEST_MISMATCH)

    with pytest.raises(TaskControllerValidationError) as step_error:
        require_semantic_binding(
            plan,
            runtime_plan_ref=PLAN_REF,
            runtime_plan_digest=plan.runtime_plan_digest,
            step_id="STEP-999",
        )
    assert str(step_error.value).startswith(BindingErrorCode.STEP_MISSING)


def test_semantic_binding_rejects_wrong_plan_reference():
    plan = _plan()
    with pytest.raises(TaskControllerValidationError) as exc:
        require_semantic_binding(
            plan,
            runtime_plan_ref="runtime-plan/other",
            runtime_plan_digest=plan.runtime_plan_digest,
            step_id="STEP-001",
        )
    assert str(exc.value).startswith(BindingErrorCode.REF_MISMATCH)


def test_run_cursor_binds_plan_identity_and_current_step():
    plan = _plan()
    cursor = RunCursor(
        run_id="run.1",
        runtime_plan_ref=PLAN_REF,
        runtime_plan_digest=plan.runtime_plan_digest,
        plan_revision=plan.revision,
        current_step_id="STEP-001",
    )

    cursor.validate_against(plan)
    advanced = cursor.advance(plan.resolve_edge("STEP-001", "PASS"))
    assert advanced.current_step_id == "STEP-002"
    assert advanced.attempt == 1


def test_run_cursor_rejects_edge_from_another_plan_step():
    plan = _plan()
    cursor = RunCursor(
        run_id="run.1",
        runtime_plan_ref=PLAN_REF,
        runtime_plan_digest=plan.runtime_plan_digest,
        plan_revision=plan.revision,
        current_step_id="STEP-001",
    )
    edge = PlanEdge(outcome="PASS", target="terminal")
    with pytest.raises(TaskControllerValidationError) as exc:
        cursor.advance(edge)
    assert str(exc.value).startswith(BindingErrorCode.EDGE_NOT_ALLOWED)


def test_file_plan_store_round_trips_and_rejects_revision_overwrite(tmp_path: Path):
    plan = _plan()
    store = FilePlanStore(tmp_path)
    stored = store.put(plan)
    loaded = store.get(PLAN_REF, plan.runtime_plan_digest)

    assert stored == plan
    assert loaded == plan
    assert json.loads((tmp_path / "runtime-plan" / "run.1.json").read_text())[
        "runtime_plan_digest"
    ] == plan.runtime_plan_digest

    changed = RuntimePlan(
        runtime_plan_ref=PLAN_REF,
        revision="r2",
        steps=plan.steps,
    )
    with pytest.raises(TaskControllerValidationError) as exc:
        store.put(changed)
    assert str(exc.value).startswith(BindingErrorCode.IMMUTABLE)


def test_plan_edge_is_typed_and_terminal_target_is_explicit():
    edge = PlanEdge(outcome="PASS", target="terminal", kind="terminal")
    assert edge.kind == "terminal"
    assert edge.is_terminal

    with pytest.raises(TaskControllerValidationError):
        PlanEdge(outcome="PASS", target="STEP-1", kind="unknown")
