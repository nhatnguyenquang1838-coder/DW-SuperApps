"""Immutable, plan-bound RuntimePlan primitives.

RuntimePlan constrains semantic topology; it never grants GWC authority. The
module is transport- and policy-neutral so TaskController can use it as a
durable execution contract without making the plan an approval source.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from taskcontroller.errors import TaskControllerValidationError


class BindingErrorCode:
    PLAN_REQUIRED = "RUNTIME_PLAN_REQUIRED"
    REF_MISMATCH = "RUNTIME_PLAN_REF_MISMATCH"
    DIGEST_MISMATCH = "RUNTIME_PLAN_DIGEST_MISMATCH"
    STEP_MISSING = "RUNTIME_PLAN_STEP_MISSING"
    STEP_STALE = "RUNTIME_PLAN_STEP_STALE"
    EDGE_NOT_ALLOWED = "RUNTIME_PLAN_EDGE_NOT_ALLOWED"
    IMMUTABLE = "RUNTIME_PLAN_IMMUTABLE"


_ALLOWED_EDGE_KINDS = frozenset(
    {"continue", "conditional", "retry", "blocked", "human_required", "terminal"}
)
_TERMINAL_TARGETS = frozenset({"terminal", "wait", "replan"})


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(f"{field} must be a non-empty string")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class PlanEdge:
    outcome: str
    target: str
    kind: str = "continue"
    source_step_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.outcome, "edge.outcome")
        _require_text(self.target, "edge.target")
        if self.kind not in _ALLOWED_EDGE_KINDS:
            raise TaskControllerValidationError(f"unsupported plan edge kind: {self.kind!r}")
        if self.source_step_id is not None:
            _require_text(self.source_step_id, "edge.source_step_id")
        if self.target in _TERMINAL_TARGETS and self.kind != "terminal":
            object.__setattr__(self, "kind", "terminal")

    @property
    def is_terminal(self) -> bool:
        return self.target in _TERMINAL_TARGETS or self.kind == "terminal"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"outcome": self.outcome, "target": self.target, "kind": self.kind}
        if self.source_step_id is not None:
            payload["source_step_id"] = self.source_step_id
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlanEdge":
        return cls(
            outcome=payload["outcome"], target=payload["target"],
            kind=payload.get("kind", "continue"), source_step_id=payload.get("source_step_id"),
        )


@dataclass(frozen=True)
class RuntimePlanStep:
    """One semantic action and its bounded execution contract."""

    step_id: str
    semantic_action: str
    allowed_inputs: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    edges: Mapping[str, PlanEdge] | None = None

    def __post_init__(self) -> None:
        _require_text(self.step_id, "step.step_id")
        _require_text(self.semantic_action, "step.semantic_action")
        for name in ("allowed_inputs", "allowed_actions", "evidence_refs"):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise TaskControllerValidationError(f"step.{name} must contain non-empty strings")
            object.__setattr__(self, name, tuple(values))
        raw_edges = self.edges or {}
        if not isinstance(raw_edges, Mapping):
            raise TaskControllerValidationError("step.edges must be a mapping")
        normalized: dict[str, PlanEdge] = {}
        for outcome, edge in raw_edges.items():
            _require_text(outcome, "step.edge outcome")
            if not isinstance(edge, PlanEdge):
                raise TaskControllerValidationError("step.edges must contain PlanEdge values")
            if edge.outcome != outcome:
                raise TaskControllerValidationError("step edge mapping key must match edge.outcome")
            bound = edge if edge.source_step_id is not None else PlanEdge(
                outcome=edge.outcome, target=edge.target, kind=edge.kind, source_step_id=self.step_id
            )
            if bound.source_step_id != self.step_id:
                raise TaskControllerValidationError("plan edge source_step_id does not match its step")
            normalized[outcome] = bound
        object.__setattr__(self, "edges", MappingProxyType(normalized))

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "semantic_action": self.semantic_action,
            "allowed_inputs": list(self.allowed_inputs),
            "allowed_actions": list(self.allowed_actions),
            "evidence_refs": list(self.evidence_refs),
            "edges": {outcome: edge.to_dict() for outcome, edge in sorted(self.edges.items())},
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimePlanStep":
        raw_edges = payload.get("edges", {})
        if not isinstance(raw_edges, Mapping):
            raise TaskControllerValidationError("step.edges must be a mapping")
        return cls(
            step_id=payload["step_id"],
            semantic_action=payload["semantic_action"],
            allowed_inputs=tuple(payload.get("allowed_inputs", ())),
            allowed_actions=tuple(payload.get("allowed_actions", ())),
            evidence_refs=tuple(payload.get("evidence_refs", ())),
            edges={outcome: PlanEdge.from_dict(edge) for outcome, edge in raw_edges.items()},
        )


@dataclass(frozen=True)
class RuntimePlan:
    runtime_plan_ref: str
    revision: str
    steps: Mapping[str, RuntimePlanStep]

    def __post_init__(self) -> None:
        _require_text(self.runtime_plan_ref, "runtime_plan_ref")
        _require_text(self.revision, "revision")
        if not isinstance(self.steps, Mapping) or not self.steps:
            raise TaskControllerValidationError("runtime plan requires at least one step")
        normalized: dict[str, RuntimePlanStep] = {}
        for step_id, step in self.steps.items():
            _require_text(step_id, "plan step id")
            if not isinstance(step, RuntimePlanStep):
                raise TaskControllerValidationError("runtime plan steps must contain RuntimePlanStep values")
            if step.step_id != step_id:
                raise TaskControllerValidationError("plan step mapping key must match step.step_id")
            normalized[step_id] = step
        object.__setattr__(self, "steps", MappingProxyType(normalized))

    @property
    def runtime_plan_digest(self) -> str:
        payload = {
            "runtime_plan_ref": self.runtime_plan_ref,
            "revision": self.revision,
            "steps": {step_id: self.steps[step_id].to_dict() for step_id in sorted(self.steps)},
        }
        return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()

    def step(self, step_id: str) -> RuntimePlanStep:
        try:
            return self.steps[step_id]
        except KeyError as exc:
            raise TaskControllerValidationError(f"{BindingErrorCode.STEP_MISSING}: {step_id}") from exc

    def resolve_edge(self, step_id: str, outcome: str) -> PlanEdge:
        try:
            return self.step(step_id).edges[outcome]
        except KeyError as exc:
            raise TaskControllerValidationError(f"{BindingErrorCode.EDGE_NOT_ALLOWED}: {step_id}/{outcome}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_plan_ref": self.runtime_plan_ref,
            "revision": self.revision,
            "runtime_plan_digest": self.runtime_plan_digest,
            "steps": {step_id: self.steps[step_id].to_dict() for step_id in sorted(self.steps)},
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimePlan":
        if not isinstance(payload, Mapping):
            raise TaskControllerValidationError("runtime plan payload must be an object")
        forbidden = {
            "authority_granted", "write_authority_granted", "merge_authority_granted",
            "deployment_authority_granted", "production_authority_granted",
        }
        present = sorted(key for key in forbidden if key in payload)
        if present:
            raise TaskControllerValidationError(f"RuntimePlan authority_granted fields are forbidden: {present}")
        raw_steps = payload.get("steps", {})
        if not isinstance(raw_steps, Mapping):
            raise TaskControllerValidationError("runtime plan steps must be a mapping")
        plan = cls(
            runtime_plan_ref=payload["runtime_plan_ref"], revision=payload["revision"],
            steps={step_id: RuntimePlanStep.from_dict(step) for step_id, step in raw_steps.items()},
        )
        supplied_digest = payload.get("runtime_plan_digest")
        if supplied_digest is not None and supplied_digest != plan.runtime_plan_digest:
            raise TaskControllerValidationError(f"{BindingErrorCode.DIGEST_MISMATCH}: persisted digest differs")
        return plan


@dataclass(frozen=True)
class RunCursor:
    run_id: str
    runtime_plan_ref: str
    runtime_plan_digest: str
    plan_revision: str
    current_step_id: str
    attempt: int = 1

    def __post_init__(self) -> None:
        for name in ("run_id", "runtime_plan_ref", "runtime_plan_digest", "plan_revision", "current_step_id"):
            _require_text(getattr(self, name), f"cursor.{name}")
        if not isinstance(self.attempt, int) or isinstance(self.attempt, bool) or self.attempt < 1:
            raise TaskControllerValidationError("cursor.attempt must be int >= 1")

    def validate_against(self, plan: RuntimePlan) -> None:
        if self.runtime_plan_ref != plan.runtime_plan_ref:
            raise TaskControllerValidationError(f"{BindingErrorCode.REF_MISMATCH}: cursor references another plan")
        if self.runtime_plan_digest != plan.runtime_plan_digest:
            raise TaskControllerValidationError(f"{BindingErrorCode.DIGEST_MISMATCH}: cursor digest is stale")
        if self.plan_revision != plan.revision:
            raise TaskControllerValidationError(f"{BindingErrorCode.STEP_STALE}: cursor revision is stale")
        plan.step(self.current_step_id)

    def advance(self, edge: PlanEdge) -> "RunCursor":
        if not isinstance(edge, PlanEdge) or edge.source_step_id != self.current_step_id:
            raise TaskControllerValidationError(f"{BindingErrorCode.EDGE_NOT_ALLOWED}: edge is not declared for current step")
        if edge.is_terminal:
            return self
        return RunCursor(
            run_id=self.run_id, runtime_plan_ref=self.runtime_plan_ref,
            runtime_plan_digest=self.runtime_plan_digest, plan_revision=self.plan_revision,
            current_step_id=edge.target, attempt=self.attempt + 1 if edge.kind == "retry" else 1,
        )


class FilePlanStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, runtime_plan_ref: str) -> Path:
        return self.root / f"{runtime_plan_ref}.json"

    def put(self, plan: RuntimePlan) -> RuntimePlan:
        if not isinstance(plan, RuntimePlan):
            raise TaskControllerValidationError("plan store accepts RuntimePlan only")
        path = self._path(plan.runtime_plan_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = RuntimePlan.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if existing.runtime_plan_digest != plan.runtime_plan_digest:
                raise TaskControllerValidationError(f"{BindingErrorCode.IMMUTABLE}: {plan.runtime_plan_ref} already exists")
            return existing
        path.write_text(json.dumps(plan.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return plan

    def get(self, runtime_plan_ref: str, runtime_plan_digest: str) -> RuntimePlan:
        try:
            plan = RuntimePlan.from_dict(json.loads(self._path(runtime_plan_ref).read_text(encoding="utf-8")))
        except FileNotFoundError as exc:
            raise TaskControllerValidationError(f"{BindingErrorCode.PLAN_REQUIRED}: plan is not persisted") from exc
        if plan.runtime_plan_digest != runtime_plan_digest:
            raise TaskControllerValidationError(f"{BindingErrorCode.DIGEST_MISMATCH}: requested digest is stale")
        return plan


def require_semantic_binding(plan: RuntimePlan, *, runtime_plan_ref: str | None, runtime_plan_digest: str | None, step_id: str | None) -> None:
    if not isinstance(plan, RuntimePlan):
        raise TaskControllerValidationError(f"{BindingErrorCode.PLAN_REQUIRED}: invalid plan")
    if not runtime_plan_ref or not runtime_plan_digest or not step_id:
        raise TaskControllerValidationError(f"{BindingErrorCode.PLAN_REQUIRED}: ref, digest and step are required")
    if runtime_plan_ref != plan.runtime_plan_ref:
        raise TaskControllerValidationError(f"{BindingErrorCode.REF_MISMATCH}: semantic action references another plan")
    if runtime_plan_digest != plan.runtime_plan_digest:
        raise TaskControllerValidationError(f"{BindingErrorCode.DIGEST_MISMATCH}: semantic action digest is stale")
    plan.step(step_id)


__all__ = ["BindingErrorCode", "FilePlanStore", "PlanEdge", "RunCursor", "RuntimePlan", "RuntimePlanStep", "require_semantic_binding"]
