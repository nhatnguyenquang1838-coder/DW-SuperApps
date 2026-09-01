from __future__ import annotations

import pytest

from taskcontroller.runtime.closed_loop_runtime_executor import (
    ClosedLoopRuntimeExecutor,
    ClosedLoopRuntimeError,
    RunCursor,
)


def _plan(
    *,
    runtime_plan_ref: str = "plan.test/r1",
    revision: str = "sha256:" + "a" * 64,
    steps: dict | None = None,
) -> dict:
    return {
        "runtime_plan_ref": runtime_plan_ref,
        "revision": revision,
        "steps": steps or {},
    }


def _cursor(
    *,
    runtime_plan_ref: str = "plan.test/r1",
    plan_revision: str = "sha256:" + "a" * 64,
    current_step: str | None = None,
    completed_steps: list[str] | None = None,
    evidence: dict | None = None,
    sequence: int = 0,
) -> RunCursor:
    return RunCursor(
        runtime_plan_ref=runtime_plan_ref,
        plan_revision=plan_revision,
        current_step=current_step,
        completed_steps=completed_steps or [],
        evidence=evidence or {},
        sequence=sequence,
    )


def test_rejects_restart_requiring_transcript_replay():
    """Fresh Controller must resume from durable cursor only, not transcript."""
    plan = _plan()
    cursor = _cursor(current_step="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    with pytest.raises(ClosedLoopRuntimeError, match="transcript"):
        executor.execute_step("inspect", {}, transcript=["msg1", "msg2"])


def test_rejects_duplicate_semantic_step_after_restart():
    """Completed step evidence must not be duplicated after restart."""
    plan = _plan(steps={"inspect": {"allowed_actions": ["read"]}})
    cursor = _cursor(current_step="validate", completed_steps=["inspect"], evidence={"inspect": {"status": "PASS"}})
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    with pytest.raises(ClosedLoopRuntimeError, match="duplicate"):
        executor.execute_step("inspect", {})


def test_rejects_lost_evidence_on_fresh_activation():
    """Fresh Controller activation with lost evidence for prior steps must be rejected."""
    plan = _plan(steps={
        "inspect": {"allowed_actions": ["read"]},
        "validate": {"allowed_actions": ["search"]},
    })
    # Cursor at "validate" but no evidence for "inspect" → lost evidence
    cursor = _cursor(current_step="validate", completed_steps=["inspect"], evidence={})
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    with pytest.raises(ClosedLoopRuntimeError, match="evidence"):
        executor.execute_step("validate", {})


def test_rejects_stale_executor_sequence():
    """Stale executor report (lower sequence) must not advance cursor."""
    plan = _plan(steps={"inspect": {"allowed_actions": ["read"]}})
    cursor = _cursor(current_step="inspect", sequence=5)
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    with pytest.raises(ClosedLoopRuntimeError, match="stale"):
        executor.execute_step("inspect", {}, sequence=3)


def test_same_canonical_inputs_produce_same_next_result():
    """Same canonical inputs must produce identical next/terminal result (deterministic)."""
    plan = _plan(steps={
        "inspect": {"allowed_actions": ["read"], "edges": {"PASS": {"target": "validate"}}},
        "validate": {"allowed_actions": ["search"], "edges": {"PASS": {"target": "TERMINAL"}}},
    })
    cursor = _cursor(current_step="inspect")
    executor1 = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    result1 = executor1.execute_step("inspect", {}, outcome="PASS")

    cursor2 = _cursor(current_step="inspect")
    executor2 = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor2)
    result2 = executor2.execute_step("inspect", {}, outcome="PASS")

    assert result1["current_step"] == result2["current_step"]
    assert result1["current_step"] == "validate"


def test_fresh_controller_resumes_same_run_without_transcript():
    """Fresh Controller resumes same run/plan revision/current step without transcript replay."""
    plan = _plan(steps={"inspect": {"allowed_actions": ["read"]}})
    cursor = _cursor(current_step="inspect", plan_revision="sha256:" + "a" * 64)
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    result = executor.execute_step("inspect", {})
    assert result["runtime_plan_ref"] == "plan.test/r1"
    assert result["current_step"] == "inspect"
    assert result["authority_revalidated"] is False


def test_exactly_once_semantic_progression():
    """Completed step evidence is not duplicated; cursor advances exactly once."""
    plan = _plan(steps={
        "inspect": {"allowed_actions": ["read"], "edges": {"PASS": {"target": "validate"}}},
    })
    cursor = _cursor(current_step="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    result = executor.execute_step("inspect", {}, outcome="PASS")
    assert result["current_step"] == "validate"
    assert "inspect" in result["completed_steps"]
    assert result["evidence"]["inspect"]["status"] == "PASS"


def test_terminal_step_returns_terminal():
    """Terminal step returns terminal status."""
    plan = _plan(steps={
        "inspect": {"allowed_actions": ["read"], "edges": {"PASS": {"target": "TERMINAL"}}},
    })
    cursor = _cursor(current_step="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    result = executor.execute_step("inspect", {}, outcome="PASS")
    assert result["current_step"] == "TERMINAL"
    assert result["is_terminal"] is True
