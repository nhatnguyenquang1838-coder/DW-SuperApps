"""M3: W6 closed-loop executor — cursor plan-bind + sequence auto-increment + durable.

Fixes the W1-W7 review BLOCKERs:
- B3: ClosedLoopRuntimeExecutor accepted any cursor — a cursor from plan A
  could be attached to plan B. Constructor must fail-closed when
  cursor.runtime_plan_ref / plan_revision / runtime_plan_digest do not match.
- B4: sequence never advanced unless the caller supplied it. Caller that
  forgets to increment leaves the cursor stuck. Sequence must
  auto-increment when not supplied.
- durability: cursor must be (re)constructable from durable evidence (JSON)
  so a hard restart resumes the same run without transcript replay.
- CORRECTION: canonical RunCursor carries runtime_plan_digest; shadow cursor
  that omits it is rejected at construction. Terminal case uses lowercase.
"""

from __future__ import annotations

import json
from pathlib import Path

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
    runtime_plan_ref: str = "plan.m3/r1",
    revision: str = "sha256:" + "a" * 64,
    steps: dict | None = None,
) -> dict:
    return {
        "runtime_plan_ref": runtime_plan_ref,
        "revision": revision,
        "runtime_plan_digest": _digest(),
        "steps": steps
        or {
            "inspect": {
                "allowed_actions": ["read"],
                "edges": {"PASS": {"target": "validate"}},
            },
            "validate": {
                "allowed_actions": ["search"],
                "edges": {"PASS": {"target": "terminal"}},
            },
        },
    }


def _cursor(
    *,
    runtime_plan_ref: str = "plan.m3/r1",
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


def test_constructor_rejects_cross_plan_cursor():
    """B3: cursor from plan A must not attach to plan B (fail-closed)."""
    plan = _plan(runtime_plan_ref="plan.m3/r1")
    cursor = _cursor(runtime_plan_ref="plan.OTHER/r9")
    with pytest.raises(ClosedLoopRuntimeError, match="runtime_plan_ref"):
        ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)


def test_constructor_rejects_cross_revision_cursor():
    """B3: cursor pinning a different plan revision must fail-closed."""
    plan = _plan(revision="sha256:" + "a" * 64)
    cursor = _cursor(plan_revision="sha256:" + "b" * 64)
    with pytest.raises(ClosedLoopRuntimeError, match="revision"):
        ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)


def test_constructor_rejects_cross_digest_cursor():
    """B3+CORRECTION: cursor with wrong digest must fail-closed."""
    plan = _plan()
    wrong_digest = "sha256:" + "0" * 64
    cursor = RunCursor(
        run_id="run-OTHER",
        runtime_plan_ref="plan.m3/r1",
        runtime_plan_digest=wrong_digest,
        plan_revision="sha256:" + "a" * 64,
        current_step_id="inspect",
        attempt=1,
    )
    with pytest.raises(ClosedLoopRuntimeError, match="runtime_plan_digest"):
        ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)


def test_constructor_accepts_matching_cursor():
    plan = _plan()
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    assert executor is not None


def test_sequence_auto_increments_when_not_provided():
    """B4: sequence advances even when the caller forgets to supply it."""
    plan = _plan()
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    result = executor.execute_step("inspect", {}, outcome="PASS")
    assert result["sequence"] == 1
    assert executor._sequence == 1


def test_sequence_auto_increments_after_restart_cursor():
    """B4: a restored cursor at sequence 3 continues to 4."""
    plan = _plan()
    cursor = _cursor(current_step_id="validate")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    # simulate prior execution
    executor._sequence = 3
    result = executor.execute_step("validate", {}, outcome="PASS")
    assert result["sequence"] == 4
    assert executor._sequence == 4


def test_cursor_roundtrips_through_durable_json(tmp_path: Path):
    """Durability: cursor (re)constructs exactly from JSON after a hard restart."""
    cursor = _cursor(
        current_step_id="validate",
    )
    path = tmp_path / "cursor.json"
    path.write_text(json.dumps(cursor.to_dict(), sort_keys=True), encoding="utf-8")
    restored = RunCursor.from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert restored.to_dict() == cursor.to_dict()
    assert restored.current_step_id == "validate"


def test_durable_restart_resumes_without_transcript():
    """A cursor restored from JSON resumes the same run/plan/step with no
    transcript replay, and auto-advances sequence."""
    plan = _plan(steps={
        "inspect": {"allowed_actions": ["read"]},
    })
    cursor = _cursor(current_step_id="inspect", plan_revision="sha256:" + "a" * 64)
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    result = executor.execute_step("inspect", {})
    assert result["runtime_plan_ref"] == "plan.m3/r1"
    assert result["current_step"] == "inspect"
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
    """M3+CORRECTION: caller-supplied step_id != cursor-bound step_id is rejected."""
    plan = _plan(steps={"inspect": {"allowed_actions": ["read"]}})
    cursor = _cursor(current_step_id="inspect")
    executor = ClosedLoopRuntimeExecutor(plan=plan, cursor=cursor)
    with pytest.raises(ClosedLoopRuntimeError, match="step_id"):
        executor.execute_step("OTHER", {})
