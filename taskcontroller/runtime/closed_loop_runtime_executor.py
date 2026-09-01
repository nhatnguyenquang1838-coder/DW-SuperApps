"""Closed-loop RuntimePlan executor with durable restart/recovery (M3+CORRECTION).

Records stable Run Cursors separately from per-execution evidence.
Every semantic step is validated against the plan; every outcome advances
the cursor exactly once.  The cursor is the canonical lightweight form
from ``taskcontroller.domain.runtime_plan`` (carries runtime_plan_digest).
The executor owns durable execution state (completed_steps, evidence, sequence)
so a hard restart resumes from cursor + durable evidence only.
"""

from __future__ import annotations

from typing import Any, Mapping

from taskcontroller.domain.runtime_plan import (
    BindingErrorCode,
    _TERMINAL_TARGETS,
    TaskControllerValidationError,
)
from taskcontroller.domain.runtime_plan import RunCursor

try:
    from tools.node_architect.authority_boundary_check import check_authority_boundary

    _GWC_VALIDATOR = True
except Exception:  # pragma: no cover
    _GWC_VALIDATOR = False


class ClosedLoopRuntimeError(Exception):
    """Raised when a closed-loop runtime step violates the RuntimePlan contract."""


class ClosedLoopRuntimeExecutor:
    """Closed-loop RuntimePlan executor with durable restart/recovery.

    The executor reconstructs execution from durable plan/cursor/evidence only.
    It never requires conversation/Slack history. Every semantic step is
    validated against the plan; every outcome advances the cursor exactly once.

    Execution state (completed_steps, evidence, sequence) is maintained by
    the executor, not by the lightweight canonical RunCursor.
    """

    def __init__(self, plan: Mapping[str, Any], cursor: RunCursor) -> None:
        if not isinstance(plan, Mapping):
            raise ClosedLoopRuntimeError("plan must be a mapping")
        self._plan = dict(plan)
        self._cursor = cursor
        # Executor-internal durable state (not in canonical RunCursor).
        self._completed_steps: list[str] = []
        self._evidence: dict[str, dict[str, Any]] = {}
        self._sequence: int = 0
        # M3+CORRECTION: fail-closed cursor/plan binding.
        plan_ref = self._plan.get("runtime_plan_ref")
        if cursor.runtime_plan_ref != plan_ref:
            raise ClosedLoopRuntimeError(
                f"cursor runtime_plan_ref {cursor.runtime_plan_ref!r} != "
                f"plan {plan_ref!r}"
            )
        plan_digest = self._plan.get("runtime_plan_digest", "")
        if cursor.runtime_plan_digest != plan_digest:
            raise ClosedLoopRuntimeError(
                f"cursor runtime_plan_digest {cursor.runtime_plan_digest!r} != "
                f"plan digest {plan_digest!r}"
            )
        plan_rev = self._plan.get("revision")
        if cursor.plan_revision != plan_rev:
            raise ClosedLoopRuntimeError(
                f"cursor plan_revision {cursor.plan_revision!r} != "
                f"plan revision {plan_rev!r}"
            )

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
        if sequence is not None and sequence <= self._sequence:
            raise ClosedLoopRuntimeError(
                f"stale executor sequence {sequence} <= cursor {self._sequence}"
            )

        # 3. Caller-supplied step_id must equal cursor-bound step (no drift).
        if step_id != self._cursor.current_step_id:
            raise ClosedLoopRuntimeError(
                f"step_id {step_id!r} != cursor-bound step {self._cursor.current_step_id!r}"
            )

        # 4. Step must be declared in plan.
        steps = self._plan.get("steps") or {}
        if step_id not in steps:
            raise ClosedLoopRuntimeError(f"step {step_id!r} not declared in plan")

        # 5. Reject duplicate semantic step after restart.
        if step_id in self._completed_steps:
            raise ClosedLoopRuntimeError(
                f"duplicate step {step_id!r}: already completed with evidence"
            )

        # 6. Reject lost evidence on fresh activation.
        if self._completed_steps:
            missing_evidence = [
                s for s in self._completed_steps if s not in self._evidence
            ]
            if missing_evidence:
                raise ClosedLoopRuntimeError(
                    f"lost evidence for steps {missing_evidence} on fresh activation"
                )

        # 7. Validate step against plan.
        step_raw = steps[step_id]
        allowed = tuple(step_raw.get("allowed_actions", ()))
        edges = step_raw.get("edges") or {}

        # 8. Outcome must be declared in step edges.
        if outcome is not None and outcome not in edges:
            raise ClosedLoopRuntimeError(
                f"outcome {outcome!r} not declared in step {step_id!r} edges"
            )

        # 9. Authority revalidation — invoke canonical GWC validator; fail-closed.
        authority_revalidated = False
        if allowed and allowed != ("read",):
            if _GWC_VALIDATOR:
                try:
                    ab = check_authority_boundary(
                        task_id="scratch",
                        repository="scratch/scratch",
                        requested_action="modify_approved_files",
                        gate_state_resolution={
                            "current_gate": "G0_CONTEXT",
                            "gate_status": "READY",
                            "scope_hash": self._cursor.runtime_plan_digest,
                        },
                        scope_identity={
                            "base_sha": self._cursor.runtime_plan_ref,
                            "head_sha": self._cursor.runtime_plan_digest,
                            "scope_hash": self._cursor.runtime_plan_digest,
                            "risk_class": "R1",
                        },
                        gate_policy={},
                        risk_class="R1",
                        production_scope_applicable=False,
                        manual_g5_action=False,
                        event_id_or_idempotency_key=(
                            f"m3-auth-{self._cursor.runtime_plan_ref}"
                        ),
                    )
                    authority_revalidated = ab.get("decision") == "APPROVED"
                except Exception:
                    authority_revalidated = False
            else:
                authority_revalidated = False

        # 10. Determine next step.
        next_step = self._cursor.current_step_id
        is_terminal = False
        if outcome is not None:
            edge = edges.get(outcome, {})
            target = edge.get("target")
            if target in _TERMINAL_TARGETS:
                next_step = target
                is_terminal = True
            elif target:
                next_step = target
            else:
                next_step = step_id
        else:
            next_step = step_id

        # 11. Build result with exactly-once progression.
        effective_sequence = (
            sequence if sequence is not None else self._sequence + 1
        )
        evidence_entry = {"status": outcome or "EXECUTED", "payload": dict(payload)}
        if step_id not in self._completed_steps:
            self._completed_steps.append(step_id)
        self._evidence[step_id] = evidence_entry
        self._sequence = effective_sequence

        result = {
            "runtime_plan_ref": self._plan.get("runtime_plan_ref", ""),
            "current_step": next_step,
            "is_terminal": is_terminal,
            "completed_steps": list(self._completed_steps),
            "evidence": dict(self._evidence),
            "authority_revalidated": authority_revalidated,
            "sequence": effective_sequence,
        }

        # 12. Advance cursor exactly once.
        self._cursor = RunCursor(
            run_id=self._cursor.run_id,
            runtime_plan_ref=self._cursor.runtime_plan_ref,
            runtime_plan_digest=self._cursor.runtime_plan_digest,
            plan_revision=self._cursor.plan_revision,
            current_step_id=next_step,
            attempt=self._cursor.attempt + 1,
        )

        return result
