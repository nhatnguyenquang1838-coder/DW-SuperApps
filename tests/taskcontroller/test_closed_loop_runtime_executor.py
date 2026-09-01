"""M3+CORRECTION: W6 closed-loop executor — canonical cursor binding + terminal case.

Tests verify:
- transcript replay rejected
- duplicate steps rejected
- lost evidence rejected
- stale sequence rejected
- terminal case uses lowercase domain value
- caller step_id drift rejected
- authority_revalidated fail-closed when no GWC validator
"""

from __future__ import annotations

import pytest

from taskcontroller.runtime.closed_loop_runtime_executor import (
    ClosedLoopRuntimeExecutor,
    ClosedLoopRuntimeError,
    RunCursor,
)


def _digest() -> str:
    return "sha256:" + "a" * 64


def _plan(
    *,
    runtime_plan_ref: str = "plan.test/r1",
    revision: str = "sha256:" + "a" * 64,
    steps: dict | None = None,
) -> dict:
    return {
        "runtime_plan_ref": runtime_plan_ref,
        "revision": revision,
        "runtime_plan_digest": _digest(),
        "steps": steps or {},
    }


def _cursor(
    *,
    runtime_plan_ref: str = "plan.test/r1",
    plan_revision: str = "sha256:" + "a" * 64,
    current_step_id: str = "inspect",
) -> RunCursor:
    return RunCursor(
        run_id=f"run-{runtime_plan_ref}",
        runtime_plan_ref=runtime_plan_ref,
        runtime_plan_digest=_digest(),
        plan_revision=plan_revision,
        current_step_id=current_step_id,
        attempt=1,
    )


def test_rejects_restart_requiring_transcript_replay():
    """Fresh Controller must resume from durable cursor only, not transcript."""
    plan = _plan(steps={"inspect": {"allowed_actions": ["read"]}})
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    with pytest.raises(ClosedLoopRuntimeError, match="transcript"):
        executor.execute_step("inspect", {}, transcript=["msg1", "msg2"])


def test_rejects_duplicate_semantic_step_after_restart():
    """Completed step evidence must not be duplicated after restart."""
    plan = _plan(steps={"inspect": {"allowed_actions": ["read"]}})
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    # Simulate prior execution
    executor._completed_steps.append("inspect")
    executor._evidence["inspect"] = {"status": "PASS"}
    with pytest.raises(ClosedLoopRuntimeError, match="duplicate"):
        executor.execute_step("inspect", {})


def test_rejects_lost_evidence_on_fresh_activation():
    """Fresh Controller activation with lost evidence for prior steps must be rejected."""
    plan = _plan(steps={
        "inspect": {"allowed_actions": ["read"]},
        "validate": {"allowed_actions": ["search"]},
    })
    cursor = _cursor(current_step_id="validate")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    # Cursor at validate but no evidence for inspect → lost evidence
    executor._completed_steps.append("inspect")
    with pytest.raises(ClosedLoopRuntimeError, match="evidence"):
        executor.execute_step("validate", {})


def test_rejects_stale_executor_sequence():
    """Stale executor report (lower sequence) must not advance cursor."""
    plan = _plan(steps={"inspect": {"allowed_actions": ["read"]}})
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    executor._sequence = 5
    with pytest.raises(ClosedLoopRuntimeError, match="stale"):
        executor.execute_step("inspect", {}, sequence=3)


def test_same_canonical_inputs_produce_same_next_result():
    """Same canonical inputs must produce identical next/terminal result."""
    plan = _plan(steps={
        "inspect": {"allowed_actions": ["read"], "edges": {"PASS": {"target": "validate"}}},
        "validate": {"allowed_actions": ["search"], "edges": {"PASS": {"target": "terminal"}}},
    })
    cursor1 = _cursor(current_step_id="inspect")
    executor1 = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor1)
    result1 = executor1.execute_step("inspect", {}, outcome="PASS")

    cursor2 = _cursor(current_step_id="inspect")
    executor2 = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor2)
    result2 = executor2.execute_step("inspect", {}, outcome="PASS")

    assert result1["current_step"] == result2["current_step"]
    assert result1["current_step"] == "validate"


def test_fresh_controller_resumes_same_run_without_transcript():
    """Fresh Controller resumes a canonical terminal step without transcript replay."""
    plan = _plan(steps={"inspect": {"allowed_actions": ["read"], "terminal": True, "edges": {}}})
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    result = executor.execute_step("inspect", {})
    assert result["runtime_plan_ref"] == "plan.test/r1"
    assert result["current_step"] == "terminal"
    assert result["is_terminal"] is True
    assert result["authority_revalidated"] is False


def test_exactly_once_semantic_progression():
    """Completed step evidence is not duplicated; cursor advances exactly once."""
    plan = _plan(steps={
        "inspect": {"allowed_actions": ["read"], "edges": {"PASS": {"target": "validate"}}},
    })
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    result = executor.execute_step("inspect", {}, outcome="PASS")
    assert result["current_step"] == "validate"
    assert "inspect" in result["completed_steps"]
    assert result["evidence"]["inspect"]["status"] == "PASS"


def test_terminal_step_returns_terminal():
    """Terminal step returns terminal status (lowercase)."""
    plan = _plan(steps={
        "inspect": {"allowed_actions": ["read"], "edges": {"PASS": {"target": "terminal"}}},
    })
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    result = executor.execute_step("inspect", {}, outcome="PASS")
    assert result["current_step"] == "terminal"
    assert result["is_terminal"] is True


def test_caller_step_id_drift_rejected():
    """Caller-supplied step_id != cursor-bound step_id is rejected."""
    plan = _plan(steps={"inspect": {"allowed_actions": ["read"]}})
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    with pytest.raises(ClosedLoopRuntimeError, match="step_id"):
        executor.execute_step("OTHER", {})


def test_authority_revalidated_false_without_gwc():
    """Without exact GWC authority, effectful execution is rejected fail-closed."""
    from unittest.mock import patch
    plan = _plan(steps={"inspect": {"allowed_actions": ["write"], "edges": {"PASS": {"target": "validate"}}}})
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    with patch("taskcontroller.runtime.closed_loop_runtime_executor._GWC_VALIDATOR", False):
        with pytest.raises(ClosedLoopRuntimeError, match="AUTHORITY_REQUIRED"):
            executor.execute_step("inspect", {}, outcome="PASS")


def test_arch_p0_h_invalid_outcome_has_zero_effect_and_state_change(tmp_path):
    from taskcontroller.runtime.closed_loop_runtime_executor import FileRuntimeExecutionStateStore

    plan = _plan(steps={
        "inspect": {
            "allowed_actions": ["read"],
            "edges": {"PASS": {"target": "validate"}},
        },
        "validate": {"allowed_actions": ["read"]},
    })
    executor = ClosedLoopRuntimeExecutor(
        plan, _cursor(current_step_id="inspect"),
    )
    effects: list[str] = []
    before = executor.state.to_dict()
    with pytest.raises(ClosedLoopRuntimeError, match="OUTCOME"):
        executor.execute_step(
            "inspect", {}, outcome="UNDECLARED", requested_action="read", sequence=1,
            effect=lambda _: effects.append("effect"),
            side_effect=lambda: effects.append("side_effect"),
        )
    assert effects == []
    assert executor.state.to_dict() == before
    assert not list(tmp_path.glob("*.json"))


def test_arch_p0_h_non_executable_route_has_zero_effect_and_state_change(tmp_path):
    from taskcontroller.runtime.closed_loop_runtime_executor import FileRuntimeExecutionStateStore

    plan = _plan(steps={
        "inspect": {
            "allowed_actions": ["read"],
            "edges": {"NEXT": {"target": "validate", "runtime_executable": False}},
        },
        "validate": {"allowed_actions": ["read"]},
    })
    executor = ClosedLoopRuntimeExecutor(
        plan, _cursor(current_step_id="inspect"),
    )
    effects: list[str] = []
    before = executor.state.to_dict()
    with pytest.raises(ClosedLoopRuntimeError, match="non-executable"):
        executor.execute_step(
            "inspect", {}, outcome="NEXT", requested_action="read", sequence=1,
            effect=lambda _: effects.append("effect"),
            side_effect=lambda: effects.append("side_effect"),
        )
    assert effects == []
    assert executor.state.to_dict() == before
    assert not list(tmp_path.glob("*.json"))


def test_arch_p0_h_routed_nonterminal_requires_outcome_before_effect():
    plan = _plan(steps={
        "inspect": {
            "allowed_actions": ["read"],
            "edges": {"PASS": {"target": "validate"}},
        },
        "validate": {"allowed_actions": ["read"]},
    })
    executor = ClosedLoopRuntimeExecutor(plan, _cursor(current_step_id="inspect"))
    effects: list[str] = []
    with pytest.raises(ClosedLoopRuntimeError, match="ROUTE_OUTCOME_REQUIRED"):
        executor.execute_step(
            "inspect", {}, requested_action="read", sequence=1,
            effect=lambda _: effects.append("effect"),
            side_effect=lambda: effects.append("side_effect"),
        )
    assert effects == []
    assert executor.cursor.current_step_id == "inspect"
    assert executor.completed_steps == ()
    assert executor.sequence == 0


def test_arch_p0_i_terminal_step_reaches_final_terminal_without_route_selector():
    plan = _plan(steps={
        "finalize": {
            "allowed_actions": ["read"],
            "terminal": True,
            "edges": {},
        },
    })
    executor = ClosedLoopRuntimeExecutor(plan, _cursor(current_step_id="finalize"))
    effects: list[str] = []
    result = executor.execute_step(
        "finalize", {}, requested_action="read", sequence=1,
        side_effect=lambda: effects.append("side_effect"),
    )
    assert effects == ["side_effect"]
    assert result["current_step"] == "terminal"
    assert result["is_terminal"] is True
    assert result["completed_steps"] == ["finalize"]
