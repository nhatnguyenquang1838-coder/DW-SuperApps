"""Canonical, plan-bound RuntimePlan primitives (M0 integration wave).

Single model across W1/W2/W4:

- W1 frozen primitives: PlanEdge, RuntimePlan, RuntimePlanStep, RunCursor,
  FilePlanStore, require_semantic_binding, BindingErrorCode.
- W2 bounded-step fields on RuntimePlanStep: allowed_inputs / allowed_actions
  / evidence_refs.
- W4 blueprint-bound fields: node_binding on the step; source_bindings,
  runbooks, authority_requirements, blueprint_id/blueprint_digest, task_id,
  scenario on the plan.
- M0 additions: canonical runtime_plan_digest covers the WHOLE plan content
  (steps + bindings + runbooks + authority + blueprint + task/scenario), and
  every plan edge target is validated for membership (declared step or
  terminal set) at construction time (the W4 compiler gap).

RuntimePlan constrains semantic topology; it never grants GWC authority.
The module is deliberately transport- and policy-neutral so TaskController can
use it as a durable execution contract without making the plan an approval
source.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from taskcontroller.errors import TaskControllerValidationError


class BindingErrorCode:
    PLAN_REQUIRED = "RUNTIME_PLAN_REQUIRED"
    REF_MISMATCH = "RUNTIME_PLAN_REF_MISMATCH"
    DIGEST_MISMATCH = "RUNTIME_PLAN_DIGEST_MISMATCH"
    STEP_MISSING = "RUNTIME_PLAN_STEP_MISSING"
    STEP_STALE = "RUNTIME_PLAN_STEP_STALE"
    EDGE_NOT_ALLOWED = "RUNTIME_PLAN_EDGE_NOT_ALLOWED"
    IMMUTABLE = "RUNTIME_PLAN_IMMUTABLE"
    PATH_TRAVERSAL = "RUNTIME_PLAN_PATH_TRAVERSAL"


_ALLOWED_EDGE_KINDS = frozenset(
    {"continue", "conditional", "retry", "blocked", "human_required", "terminal"}
)
_TERMINAL_TARGETS = frozenset({"terminal", "wait", "replan"})


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(f"{field} must be a non-empty string")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@dataclass(frozen=True)
class PlanEdge:
    """One explicitly declared typed transition from a plan step."""

    outcome: str
    target: str
    kind: str = "continue"
    source_step_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.outcome, "edge.outcome")
        _require_text(self.target, "edge.target")
        if self.kind not in _ALLOWED_EDGE_KINDS:
            raise TaskControllerValidationError(
                f"unsupported plan edge kind: {self.kind!r}"
            )
        if self.source_step_id is not None:
            _require_text(self.source_step_id, "edge.source_step_id")
        if self.target in _TERMINAL_TARGETS and self.kind != "terminal":
            object.__setattr__(self, "kind", "terminal")

    @property
    def is_terminal(self) -> bool:
        return self.target in _TERMINAL_TARGETS or self.kind == "terminal"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "outcome": self.outcome,
            "target": self.target,
            "kind": self.kind,
        }
        if self.source_step_id is not None:
            payload["source_step_id"] = self.source_step_id
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlanEdge":
        return cls(
            outcome=payload["outcome"],
            target=payload["target"],
            kind=payload.get("kind", "continue"),
            source_step_id=payload.get("source_step_id"),
        )


@dataclass(frozen=True)
class RuntimePlanStep:
    """A semantic action, the edges it may take, and its bounded inputs/actions.

    Merges the W2 bounded-step contract (allowed_inputs / allowed_actions /
    evidence_refs) with the W4 blueprint-bound node binding.
    """

    step_id: str
    semantic_action: str
    edges: Mapping[str, PlanEdge] | None = None
    node_binding: Mapping[str, Any] | None = None
    allowed_inputs: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.step_id, "step.step_id")
        _require_text(self.semantic_action, "step.semantic_action")
        for name in ("allowed_inputs", "allowed_actions", "evidence_refs"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not all(isinstance(v, str) for v in values):
                raise TaskControllerValidationError(f"step.{name} must be a tuple of str")
        if self.node_binding is not None and not isinstance(self.node_binding, Mapping):
            raise TaskControllerValidationError("step.node_binding must be a mapping")
        raw_edges: Mapping[str, PlanEdge] = self.edges or {}
        normalized: dict[str, PlanEdge] = {}
        for outcome, edge in raw_edges.items():
            _require_text(outcome, "step.edge outcome")
            if not isinstance(edge, PlanEdge):
                raise TaskControllerValidationError("step.edges must contain PlanEdge values")
            if edge.outcome != outcome:
                raise TaskControllerValidationError(
                    "step edge mapping key must match edge.outcome"
                )
            bound = edge
            if edge.source_step_id is None:
                bound = PlanEdge(
                    outcome=edge.outcome,
                    target=edge.target,
                    kind=edge.kind,
                    source_step_id=self.step_id,
                )
            elif edge.source_step_id != self.step_id:
                raise TaskControllerValidationError(
                    "plan edge source_step_id does not match its step"
                )
            normalized[outcome] = bound
        object.__setattr__(self, "edges", MappingProxyType(normalized))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "step_id": self.step_id,
            "semantic_action": self.semantic_action,
            "edges": {
                outcome: edge.to_dict()
                for outcome, edge in sorted(self.edges.items())
            },
        }
        if self.node_binding is not None:
            payload["node_binding"] = self.node_binding
        if self.allowed_inputs:
            payload["allowed_inputs"] = list(self.allowed_inputs)
        if self.allowed_actions:
            payload["allowed_actions"] = list(self.allowed_actions)
        if self.evidence_refs:
            payload["evidence_refs"] = list(self.evidence_refs)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimePlanStep":
        raw_edges = payload.get("edges", {})
        if not isinstance(raw_edges, Mapping):
            raise TaskControllerValidationError("step.edges must be a mapping")
        return cls(
            step_id=payload["step_id"],
            semantic_action=payload["semantic_action"],
            edges={
                outcome: PlanEdge.from_dict(edge)
                for outcome, edge in raw_edges.items()
            },
            node_binding=payload.get("node_binding"),
            allowed_inputs=tuple(payload.get("allowed_inputs", ())),
            allowed_actions=tuple(payload.get("allowed_actions", ())),
            evidence_refs=tuple(payload.get("evidence_refs", ())),
        )


@dataclass(frozen=True)
class AuthorityRequirement:
    """A gate that GWC must satisfy before the action proceeds."""

    action: str
    gate: str
    required: bool = False

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "gate": self.gate, "required": self.required}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AuthorityRequirement":
        return cls(
            action=payload.get("action", ""),
            gate=payload.get("gate", ""),
            required=bool(payload.get("required", False)),
        )


@dataclass(frozen=True)
class RunbookBinding:
    """A pinned runbook revision bound to this plan."""

    runbook_id: str
    revision: str = ""
    digest: str = ""

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runbook_id": self.runbook_id,
            "revision": self.revision,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunbookBinding":
        return cls(
            runbook_id=payload.get("runbook_id", ""),
            revision=payload.get("revision", ""),
            digest=payload.get("digest", ""),
        )


class SourceBindingError(TaskControllerValidationError):
    """Raised when source bindings are stale or unreadable."""


@dataclass(frozen=True)
class RuntimePlan:
    """Immutable content-addressed graph for one run/revision.

    Canonical across W1/W2/W4: carries W2 step bounds, W4 blueprint bindings,
    and a digest that covers the full plan content.
    """

    runtime_plan_ref: str
    revision: str
    steps: Mapping[str, RuntimePlanStep]
    source_bindings: Mapping[str, Any] | None = None
    runbooks: Sequence[RunbookBinding] | None = None
    authority_requirements: Sequence[AuthorityRequirement] | None = None
    blueprint_id: str = ""
    blueprint_digest: str = ""
    task_id: str = ""
    scenario: str = ""

    def __post_init__(self) -> None:
        _require_text(self.runtime_plan_ref, "runtime_plan_ref")
        _require_text(self.revision, "revision")
        if not isinstance(self.steps, Mapping) or not self.steps:
            raise TaskControllerValidationError("runtime plan requires at least one step")
        normalized: dict[str, RuntimePlanStep] = {}
        for step_id, step in self.steps.items():
            _require_text(step_id, "plan step id")
            if not isinstance(step, RuntimePlanStep):
                raise TaskControllerValidationError(
                    "runtime plan steps must contain RuntimePlanStep values"
                )
            if step.step_id != step_id:
                raise TaskControllerValidationError(
                    "plan step mapping key must match step.step_id"
                )
            normalized[step_id] = step
        object.__setattr__(self, "steps", MappingProxyType(normalized))
        # M0: edge target membership — every edge target must be a declared
        # step or a terminal target (the W4 compiler gap, enforced here at
        # construction so no plan can carry a dangling edge).
        for step_id, step in normalized.items():
            for outcome, edge in step.edges.items():
                target = edge.target
                if target in _TERMINAL_TARGETS:
                    continue
                if target not in normalized:
                    raise TaskControllerValidationError(
                        f"{BindingErrorCode.EDGE_NOT_ALLOWED}: edge "
                        f"{step_id}/{outcome} targets undeclared step {target!r}"
                    )

    @property
    def runtime_plan_digest(self) -> str:
        payload = {
            "runtime_plan_ref": self.runtime_plan_ref,
            "revision": self.revision,
            "steps": {
                step_id: self.steps[step_id].to_dict()
                for step_id in sorted(self.steps)
            },
            "source_bindings": self.source_bindings,
            "runbooks": [
                rb.to_dict() if isinstance(rb, RunbookBinding) else rb
                for rb in self.runbooks or []
            ],
            "authority_requirements": [
                ar.to_dict() if isinstance(ar, AuthorityRequirement) else ar
                for ar in self.authority_requirements or []
            ],
            "blueprint_id": self.blueprint_id,
            "blueprint_digest": self.blueprint_digest,
            "task_id": self.task_id,
            "scenario": self.scenario,
        }
        return "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()

    def step(self, step_id: str) -> RuntimePlanStep:
        try:
            return self.steps[step_id]
        except KeyError as exc:
            raise TaskControllerValidationError(
                f"{BindingErrorCode.STEP_MISSING}: {step_id}"
            ) from exc

    def resolve_edge(self, step_id: str, outcome: str) -> PlanEdge:
        step = self.step(step_id)
        try:
            return step.edges[outcome]
        except KeyError as exc:
            raise TaskControllerValidationError(
                f"{BindingErrorCode.EDGE_NOT_ALLOWED}: {step_id}/{outcome}"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "runtime_plan_ref": self.runtime_plan_ref,
            "revision": self.revision,
            "runtime_plan_digest": self.runtime_plan_digest,
            "steps": {
                step_id: self.steps[step_id].to_dict()
                for step_id in sorted(self.steps)
            },
        }
        if self.source_bindings is not None:
            payload["source_bindings"] = self.source_bindings
        if self.runbooks is not None:
            payload["runbooks"] = [
                rb.to_dict() if isinstance(rb, RunbookBinding) else rb
                for rb in self.runbooks
            ]
        if self.authority_requirements is not None:
            payload["authority_requirements"] = [
                ar.to_dict() if isinstance(ar, AuthorityRequirement) else ar
                for ar in self.authority_requirements
            ]
        if self.blueprint_id:
            payload["blueprint_id"] = self.blueprint_id
        if self.blueprint_digest:
            payload["blueprint_digest"] = self.blueprint_digest
        if self.task_id:
            payload["task_id"] = self.task_id
        if self.scenario:
            payload["scenario"] = self.scenario
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimePlan":
        if not isinstance(payload, Mapping):
            raise TaskControllerValidationError("runtime plan payload must be an object")
        forbidden = {
            "authority_granted",
            "write_authority_granted",
            "merge_authority_granted",
            "deployment_authority_granted",
            "production_authority_granted",
        }
        present = sorted(key for key in forbidden if key in payload)
        if present:
            raise TaskControllerValidationError(
                f"RuntimePlan authority_granted fields are forbidden: {present}"
            )
        raw_steps = payload.get("steps", {})
        if not isinstance(raw_steps, Mapping):
            raise TaskControllerValidationError("runtime plan steps must be a mapping")
        plan = cls(
            runtime_plan_ref=payload["runtime_plan_ref"],
            revision=payload["revision"],
            steps={
                step_id: RuntimePlanStep.from_dict(step)
                for step_id, step in raw_steps.items()
            },
            source_bindings=payload.get("source_bindings"),
            runbooks=[
                RunbookBinding.from_dict(rb) if isinstance(rb, Mapping) else rb
                for rb in payload.get("runbooks", [])
            ] if "runbooks" in payload else None,
            authority_requirements=[
                AuthorityRequirement.from_dict(ar) if isinstance(ar, Mapping) else ar
                for ar in payload.get("authority_requirements", [])
            ] if "authority_requirements" in payload else None,
            blueprint_id=payload.get("blueprint_id", ""),
            blueprint_digest=payload.get("blueprint_digest", ""),
            task_id=payload.get("task_id", ""),
            scenario=payload.get("scenario", ""),
        )
        supplied_digest = payload.get("runtime_plan_digest")
        if supplied_digest is not None and supplied_digest != plan.runtime_plan_digest:
            raise TaskControllerValidationError(
                f"{BindingErrorCode.DIGEST_MISMATCH}: persisted digest differs"
            )
        return plan


@dataclass(frozen=True)
class RunCursor:
    """Durable pointer to one RuntimePlan revision and its current step."""

    run_id: str
    runtime_plan_ref: str
    runtime_plan_digest: str
    plan_revision: str
    current_step_id: str
    attempt: int = 1

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "runtime_plan_ref",
            "runtime_plan_digest",
            "plan_revision",
            "current_step_id",
        ):
            _require_text(getattr(self, name), f"cursor.{name}")
        if not isinstance(self.attempt, int) or isinstance(self.attempt, bool) or self.attempt < 1:
            raise TaskControllerValidationError("cursor.attempt must be int >= 1")

    def validate_against(self, plan: RuntimePlan) -> None:
        if self.runtime_plan_ref != plan.runtime_plan_ref:
            raise TaskControllerValidationError(
                f"{BindingErrorCode.REF_MISMATCH}: cursor references another plan"
            )
        if self.runtime_plan_digest != plan.runtime_plan_digest:
            raise TaskControllerValidationError(
                f"{BindingErrorCode.DIGEST_MISMATCH}: cursor digest is stale"
            )
        if self.plan_revision != plan.revision:
            raise TaskControllerValidationError(
                f"{BindingErrorCode.STEP_STALE}: cursor revision is stale"
            )
        plan.step(self.current_step_id)

    def advance(self, edge: PlanEdge) -> "RunCursor":
        if not isinstance(edge, PlanEdge) or edge.source_step_id != self.current_step_id:
            raise TaskControllerValidationError(
                f"{BindingErrorCode.EDGE_NOT_ALLOWED}: edge is not declared for current step"
            )
        if edge.is_terminal:
            return self
        return RunCursor(
            run_id=self.run_id,
            runtime_plan_ref=self.runtime_plan_ref,
            runtime_plan_digest=self.runtime_plan_digest,
            plan_revision=self.plan_revision,
            current_step_id=edge.target,
            attempt=self.attempt + 1 if edge.kind == "retry" else 1,
        )


class FilePlanStore:
    """Small durable JSON store keyed by the stable RuntimePlan reference."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, runtime_plan_ref: str) -> Path:
        path = self.root / f"{runtime_plan_ref}.json"
        try:
            resolved = path.resolve()
        except RuntimeError as exc:
            raise TaskControllerValidationError(
                f"{BindingErrorCode.PATH_TRAVERSAL}: unresolved path"
            ) from exc
        root = self.root.resolve()
        if not str(resolved).startswith(str(root)):
            raise TaskControllerValidationError(
                f"{BindingErrorCode.PATH_TRAVERSAL}: ref escapes store root"
            )
        return path

    def put(self, plan: RuntimePlan) -> RuntimePlan:
        if not isinstance(plan, RuntimePlan):
            raise TaskControllerValidationError("plan store accepts RuntimePlan only")
        path = self._path(plan.runtime_plan_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = RuntimePlan.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if existing.runtime_plan_digest != plan.runtime_plan_digest:
                raise TaskControllerValidationError(
                    f"{BindingErrorCode.IMMUTABLE}: {plan.runtime_plan_ref} already exists"
                )
            return existing
        path.write_text(
            json.dumps(plan.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return plan

    def get(self, runtime_plan_ref: str, runtime_plan_digest: str) -> RuntimePlan:
        path = self._path(runtime_plan_ref)
        try:
            plan = RuntimePlan.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError as exc:
            raise TaskControllerValidationError(
                f"{BindingErrorCode.PLAN_REQUIRED}: plan is not persisted"
            ) from exc
        if plan.runtime_plan_digest != runtime_plan_digest:
            raise TaskControllerValidationError(
                f"{BindingErrorCode.DIGEST_MISMATCH}: requested digest is stale"
            )
        return plan


def require_semantic_binding(
    plan: RuntimePlan,
    *,
    runtime_plan_ref: str | None,
    runtime_plan_digest: str | None,
    step_id: str | None,
) -> None:
    """Fail closed before semantic execution when any plan identity is absent."""

    if not isinstance(plan, RuntimePlan):
        raise TaskControllerValidationError(f"{BindingErrorCode.PLAN_REQUIRED}: invalid plan")
    if not runtime_plan_ref or not runtime_plan_digest or not step_id:
        raise TaskControllerValidationError(
            f"{BindingErrorCode.PLAN_REQUIRED}: ref, digest and step are required"
        )
    if runtime_plan_ref != plan.runtime_plan_ref:
        raise TaskControllerValidationError(
            f"{BindingErrorCode.REF_MISMATCH}: semantic action references another plan"
        )
    if runtime_plan_digest != plan.runtime_plan_digest:
        raise TaskControllerValidationError(
            f"{BindingErrorCode.DIGEST_MISMATCH}: semantic action digest is stale"
        )
    plan.step(step_id)


__all__ = [
    "AuthorityRequirement",
    "BindingErrorCode",
    "FilePlanStore",
    "PlanEdge",
    "RunCursor",
    "RunbookBinding",
    "RuntimePlan",
    "RuntimePlanStep",
    "SourceBindingError",
    "require_semantic_binding",
]
