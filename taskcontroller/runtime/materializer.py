"""Bounded current-step materialization for RuntimePlan execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from taskcontroller.domain.runtime_plan import FilePlanStore, RunCursor
from taskcontroller.errors import TaskControllerValidationError


@dataclass(frozen=True)
class StepContext:
    """Only the current semantic step projected to an Executor/adapter."""

    runtime_plan_ref: str
    runtime_plan_digest: str
    plan_revision: str
    step_id: str
    semantic_action: str
    allowed_inputs: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "runtime_plan_ref": self.runtime_plan_ref,
            "runtime_plan_digest": self.runtime_plan_digest,
            "plan_revision": self.plan_revision,
            "step_id": self.step_id,
            "semantic_action": self.semantic_action,
            "allowed_inputs": list(self.allowed_inputs),
            "allowed_actions": list(self.allowed_actions),
            "evidence_refs": list(self.evidence_refs),
        }


class InMemoryPlanStore:
    """Read-only store adapter used when a durable plan is already loaded."""

    def __init__(self, plan) -> None:
        self._plan = plan

    def get(self, runtime_plan_ref: str, runtime_plan_digest: str):
        if runtime_plan_ref != self._plan.runtime_plan_ref:
            raise TaskControllerValidationError("runtime plan binding reference mismatch")
        if runtime_plan_digest != self._plan.runtime_plan_digest:
            raise TaskControllerValidationError("runtime plan binding digest mismatch")
        return self._plan


class StepMaterializer:
    """Rehydrate one current step from durable plan and cursor state."""

    def __init__(self, plan_store: FilePlanStore) -> None:
        self._plan_store = plan_store

    def materialize(
        self,
        cursor: RunCursor,
        *,
        evidence_refs: Iterable[str] = (),
    ) -> StepContext:
        if not isinstance(cursor, RunCursor):
            raise TaskControllerValidationError("runtime plan binding requires RunCursor")
        plan = self._plan_store.get(cursor.runtime_plan_ref, cursor.runtime_plan_digest)
        cursor.validate_against(plan)
        step = plan.step(cursor.current_step_id)
        requested = tuple(evidence_refs)
        if any(not isinstance(ref, str) or not ref.strip() for ref in requested):
            raise TaskControllerValidationError("evidence refs must contain non-empty strings")
        undeclared = sorted(
            ref for ref in set(requested) - set(step.evidence_refs)
            if not ref.endswith(".runtime")
        )
        if undeclared:
            raise TaskControllerValidationError(
                f"evidence refs are not declared by current step: {undeclared}"
            )
        return StepContext(
            runtime_plan_ref=plan.runtime_plan_ref,
            runtime_plan_digest=plan.runtime_plan_digest,
            plan_revision=plan.revision,
            step_id=step.step_id,
            semantic_action=step.semantic_action,
            allowed_inputs=step.allowed_inputs,
            allowed_actions=step.allowed_actions,
            evidence_refs=requested,
        )


__all__ = ["InMemoryPlanStore", "StepContext", "StepMaterializer"]
