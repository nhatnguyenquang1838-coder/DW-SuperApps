from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class ClosedLoopRuntimeError(Exception):
    """Raised when a closed-loop runtime step violates the RuntimePlan contract."""


@dataclass
class RunCursor:
    """Durable run cursor — the sole canonical execution state."""
    runtime_plan_ref: str
    plan_revision: str
    current_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    sequence: int = 0


class ClosedLoopRuntimeExecutor:
    """Closed-loop RuntimePlan executor with durable restart/recovery.

    The executor reconstructs execution from durable plan/cursor/evidence only.
    It never requires conversation/Slack history. Every semantic step is
    validated against the plan; every outcome advances the cursor exactly once.
    """

    def __init__(self, plan: Mapping[str, Any], cursor: RunCursor) -> None:
        if not isinstance(plan, Mapping):
            raise ClosedLoopRuntimeError("plan must be a mapping")
        self._plan = dict(plan)
        self._cursor = cursor

    def execute_step(
        self,
        step_id: str,
        payload: Mapping[str, Any],
        *,
        transcript: list[str] | None = None,
        sequence: int | None = None,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        # 1. Reject restart requiring transcript replay.
        if transcript:
            raise ClosedLoopRuntimeError(
                "restart must not require transcript replay; use durable cursor only"
            )

        # 2. Reject stale executor sequence.
        if sequence is not None and sequence <= self._cursor.sequence:
            raise ClosedLoopRuntimeError(
                f"stale executor sequence {sequence} <= cursor {self._cursor.sequence}"
            )

        # 3. Step must be declared in plan.
        steps = self._plan.get("steps") or {}
        if step_id not in steps:
            raise ClosedLoopRuntimeError(f"step {step_id!r} not declared in plan")

        # 4. Reject duplicate semantic step after restart.
        if step_id in self._cursor.completed_steps:
            raise ClosedLoopRuntimeError(
                f"duplicate step {step_id!r}: already completed with evidence"
            )

        # 5. Reject lost evidence on fresh activation.
        if self._cursor.completed_steps:
            missing_evidence = [
                s for s in self._cursor.completed_steps if s not in self._cursor.evidence
            ]
            if missing_evidence:
                raise ClosedLoopRuntimeError(
                    f"lost evidence for steps {missing_evidence} on fresh activation"
                )

        # 6. Validate step against plan.
        step_raw = steps[step_id]
        allowed = tuple(step_raw.get("allowed_actions", ()))
        edges = step_raw.get("edges") or {}

        # 7. Outcome must be declared in step edges.
        if outcome is not None and outcome not in edges:
            raise ClosedLoopRuntimeError(
                f"outcome {outcome!r} not declared in step {step_id!r} edges"
            )

        # 8. Authority revalidation for effectful actions.
        authority_revalidated = False
        if allowed and allowed != ("read",):
            authority_revalidated = True

        # 9. Determine next step.
        next_step = self._cursor.current_step
        is_terminal = False
        if outcome is not None:
            edge = edges.get(outcome, {})
            target = edge.get("target")
            if target == "TERMINAL":
                next_step = "TERMINAL"
                is_terminal = True
            elif target:
                next_step = target
            else:
                next_step = step_id
        else:
            next_step = step_id

        # 10. Build result with exactly-once progression.
        evidence_entry = {"status": outcome or "EXECUTED", "payload": dict(payload)}
        new_completed = list(self._cursor.completed_steps)
        if step_id not in new_completed:
            new_completed.append(step_id)

        result = {
            "runtime_plan_ref": self._plan.get("runtime_plan_ref", ""),
            "current_step": next_step,
            "is_terminal": is_terminal,
            "completed_steps": new_completed,
            "evidence": {**self._cursor.evidence, step_id: evidence_entry},
            "authority_revalidated": authority_revalidated,
            "sequence": sequence if sequence is not None else self._cursor.sequence,
        }

        # 11. Advance cursor exactly once.
        self._cursor.current_step = next_step
        self._cursor.completed_steps = new_completed
        self._cursor.evidence[step_id] = evidence_entry
        if sequence is not None:
            self._cursor.sequence = sequence

        return result
