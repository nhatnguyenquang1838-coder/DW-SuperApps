"""Closed-loop RuntimePlan execution with durable, fail-closed recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from taskcontroller.domain.runtime_plan import (
    PlanEdge,
    RunCursor,
    RuntimePlan,
    _deep_plain,
)


class ClosedLoopRuntimeError(Exception):
    """Raised when a closed-loop runtime step violates its bound contract."""


_READ_ONLY_ACTIONS = frozenset({
    "read", "search", "inspect", "reconcile_pr_head_state", "capture_ci_evidence",
})


@dataclass(frozen=True)
class RuntimeExecutionState:
    """Durable execution projection needed to restart without conversation replay."""

    run_id: str
    runtime_plan_ref: str
    runtime_plan_digest: str
    plan_revision: str
    cursor: RunCursor
    completed_steps: tuple[str, ...] = ()
    evidence: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "runtime_plan_ref": self.runtime_plan_ref,
            "runtime_plan_digest": self.runtime_plan_digest,
            "plan_revision": self.plan_revision,
            "cursor": self.cursor.to_dict(),
            "completed_steps": list(self.completed_steps),
            "evidence": _deep_plain(self.evidence),
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeExecutionState":
        return cls(
            run_id=str(payload["run_id"]),
            runtime_plan_ref=str(payload["runtime_plan_ref"]),
            runtime_plan_digest=str(payload["runtime_plan_digest"]),
            plan_revision=str(payload["plan_revision"]),
            cursor=RunCursor.from_dict(payload["cursor"]),
            completed_steps=tuple(str(x) for x in payload.get("completed_steps", ())),
            evidence=payload.get("evidence", {}),
            sequence=int(payload.get("sequence", 0)),
        )


class FileRuntimeExecutionStateStore:
    """Atomic JSON state store keyed by run id."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, run_id: str) -> Path:
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            raise ClosedLoopRuntimeError("invalid durable run_id")
        return self.root / f"{run_id}.json"

    def load(self, run_id: str) -> RuntimeExecutionState | None:
        try:
            return RuntimeExecutionState.from_dict(
                json.loads(self._path(run_id).read_text(encoding="utf-8"))
            )
        except FileNotFoundError:
            return None

    def put(self, state: RuntimeExecutionState) -> RuntimeExecutionState:
        path = self._path(state.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        return state


# Kept as a compatibility seam for callers that inspect the old module flag.
_GWC_VALIDATOR = False


class ClosedLoopRuntimeExecutor:
    """Execute only the current immutable plan step and persist every transition."""

    def __init__(
        self,
        plan: Mapping[str, Any],
        cursor: RunCursor,
        *,
        state_store: FileRuntimeExecutionStateStore | None = None,
        authority_checker: Callable[[Mapping[str, Any]], Any] | None = None,
        authority_context: Mapping[str, Any] | None = None,
        node_instruction_resolver: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        if not isinstance(plan, Mapping):
            raise ClosedLoopRuntimeError("plan must be a mapping")
        self._plan = dict(plan)
        self._cursor = cursor
        self._state_store = state_store
        self._authority_checker = authority_checker
        self._authority_context = dict(authority_context or {})
        self._node_instruction_resolver = node_instruction_resolver
        self._completed_steps: list[str] = []
        self._evidence: dict[str, dict[str, Any]] = {}
        self._sequence = 0
        self._validate_binding(cursor, self._plan)
        if state_store is not None:
            prior = state_store.load(cursor.run_id)
            if prior is not None:
                if (prior.runtime_plan_ref != cursor.runtime_plan_ref or
                    prior.runtime_plan_digest != cursor.runtime_plan_digest or
                    prior.plan_revision != cursor.plan_revision):
                    raise ClosedLoopRuntimeError("durable state is bound to a different RuntimePlan")
                prior.cursor.validate_against(self._plan_object())
                self._cursor = prior.cursor
                self._completed_steps = list(prior.completed_steps)
                self._evidence = {k: dict(v) for k, v in prior.evidence.items()}
                self._sequence = prior.sequence

    @property
    def cursor(self) -> RunCursor:
        return self._cursor

    @property
    def state(self) -> RuntimeExecutionState:
        return RuntimeExecutionState(
            run_id=self._cursor.run_id,
            runtime_plan_ref=self._cursor.runtime_plan_ref,
            runtime_plan_digest=self._cursor.runtime_plan_digest,
            plan_revision=self._cursor.plan_revision,
            cursor=self._cursor,
            completed_steps=tuple(self._completed_steps),
            evidence=self._evidence,
            sequence=self._sequence,
        )

    @property
    def completed_steps(self) -> tuple[str, ...]:
        return tuple(self._completed_steps)

    @property
    def evidence(self) -> Mapping[str, Mapping[str, Any]]:
        return json.loads(json.dumps(self._evidence))

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def last_sequence(self) -> int:
        return self._sequence

    def _plan_object(self) -> RuntimePlan:
        try:
            return RuntimePlan.from_dict(self._plan)
        except Exception as exc:
            raise ClosedLoopRuntimeError(f"invalid RuntimePlan payload: {exc}") from exc

    @staticmethod
    def _validate_binding(cursor: RunCursor, plan: Mapping[str, Any]) -> None:
        for field in ("runtime_plan_ref", "runtime_plan_digest", "revision"):
            if not plan.get(field):
                raise ClosedLoopRuntimeError(f"plan missing {field}")
        if cursor.runtime_plan_ref != plan.get("runtime_plan_ref"):
            raise ClosedLoopRuntimeError("cursor runtime_plan_ref does not match plan")
        if cursor.runtime_plan_digest != plan.get("runtime_plan_digest"):
            raise ClosedLoopRuntimeError("cursor runtime_plan_digest does not match plan")
        if cursor.plan_revision != plan.get("revision"):
            raise ClosedLoopRuntimeError("cursor plan_revision does not match plan")

    @staticmethod
    def _normalize_action(value: Any) -> str:
        return str(value).strip().lower().replace("-", "_")

    def _step_capabilities(self, step_raw: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        allowed_actions = tuple(str(x) for x in step_raw.get("allowed_actions", ()))
        allowed_inputs = tuple(str(x) for x in step_raw.get("allowed_inputs", ()))
        evidence_refs = tuple(str(x) for x in step_raw.get("evidence_refs", ()))
        if self._node_instruction_resolver is not None:
            instruction = self._node_instruction_resolver(step_raw)
            if not isinstance(instruction, Mapping):
                raise ClosedLoopRuntimeError("node instruction resolver returned invalid data")
            allowed_actions = tuple(str(x) for x in instruction.get("allowed_actions", allowed_actions))
            allowed_inputs = tuple(str(x) for x in instruction.get("inputs", allowed_inputs))
            evidence_refs = tuple(str(x) for x in instruction.get("evidence_required", evidence_refs))
        return allowed_actions, allowed_inputs, evidence_refs

    def _revalidate_authority(self, action: str) -> bool:
        required = {"task_id", "repository", "base_sha", "head_sha", "scope_hash", "expires_at"}
        if not self._authority_checker or not required.issubset(self._authority_context):
            return False
        context = dict(self._authority_context)
        context["action"] = action
        decision = self._authority_checker(context)
        if isinstance(decision, Mapping):
            return decision.get("decision") == "APPROVED" or decision.get("approved") is True
        return decision is True

    def _persist(self) -> None:
        if self._state_store is not None:
            self._state_store.put(self.state)

    def execute_step(
        self,
        step_id: str,
        payload: Mapping[str, Any],
        *,
        transcript: list[str] | None = None,
        sequence: int | None = None,
        outcome: str | None = None,
        requested_action: str | None = None,
        outcome_resolver: Callable[[Mapping[str, Any], Mapping[str, Any]], str | None] | None = None,
        effect: Callable[[Mapping[str, Any]], Any] | None = None,
        side_effect: Callable[[], Any] | None = None,
    ) -> dict[str, Any]:
        if transcript:
            raise ClosedLoopRuntimeError("restart must not require transcript replay; use durable cursor only")
        if sequence is not None and sequence <= self._sequence:
            raise ClosedLoopRuntimeError(f"stale executor sequence {sequence} <= cursor {self._sequence}")
        if self._cursor.control_state != "RUNNING":
            raise ClosedLoopRuntimeError(f"cursor is {self._cursor.control_state}; resume or replan first")
        if step_id != self._cursor.current_step_id:
            raise ClosedLoopRuntimeError(f"step_id {step_id!r} != cursor-bound step {self._cursor.current_step_id!r}")
        steps = self._plan.get("steps") or {}
        if step_id not in steps:
            raise ClosedLoopRuntimeError(f"step {step_id!r} not declared in plan")
        if step_id in self._completed_steps:
            raise ClosedLoopRuntimeError(f"duplicate step {step_id!r}: already completed with evidence")
        missing_evidence = [s for s in self._completed_steps if s not in self._evidence]
        if missing_evidence:
            raise ClosedLoopRuntimeError(f"lost evidence for steps {missing_evidence} on fresh activation")

        step_raw = steps[step_id]
        allowed, allowed_inputs, evidence_refs = self._step_capabilities(step_raw)
        if allowed_inputs:
            unknown = sorted(set(payload) - set(allowed_inputs) - {"requested_action"})
            if unknown:
                raise ClosedLoopRuntimeError(f"payload inputs not allowed for {step_id}: {unknown}")
        raw_action = requested_action if requested_action is not None else payload.get("requested_action")
        normalized_allowed = {self._normalize_action(x) for x in allowed}
        if raw_action is not None:
            action = self._normalize_action(raw_action)
            if not action or action not in normalized_allowed:
                raise ClosedLoopRuntimeError(f"requested_action {raw_action!r} is not allowed for {step_id}")
        else:
            action = self._normalize_action(allowed[0]) if len(allowed) == 1 else ""

        edges = step_raw.get("edges") or {}
        if not isinstance(edges, Mapping):
            raise ClosedLoopRuntimeError(f"ROUTE_INVALID: edges for {step_id} must be a mapping")
        terminal_step = bool(step_raw.get("terminal", False))
        if terminal_step:
            if edges:
                raise ClosedLoopRuntimeError("terminal step must preserve canonical edges: []")
            if outcome is not None:
                raise ClosedLoopRuntimeError("terminal step does not accept a caller-selected outcome")
            edge = None
            resolved_outcome = None
        else:
            if not edges:
                # Legacy plan payloads may contain an unmarked leaf. Canonical
                # compiler output must use terminal:true; preserve old replay
                # semantics here without treating a routed step as terminal.
                edge = None
                resolved_outcome = None
            else:
                if outcome_resolver is not None:
                    resolved_outcome = outcome_resolver(step_raw, payload)
                elif outcome is not None and len(edges) == 1:
                    # A caller outcome is only an assertion when the topology is
                    # unambiguous; it never selects among multiple routes.
                    resolved_outcome = next(iter(edges))
                else:
                    raise ClosedLoopRuntimeError(
                        "ROUTE_OUTCOME_REQUIRED: routed non-terminal step requires "
                        "an executor-derived outcome"
                    )
                if not isinstance(resolved_outcome, str) or resolved_outcome not in edges:
                    raise ClosedLoopRuntimeError(
                        f"ROUTE_OUTCOME_UNRESOLVED: {resolved_outcome!r} is not declared "
                        f"for step {step_id!r}"
                    )
                if outcome is not None and outcome != resolved_outcome:
                    raise ClosedLoopRuntimeError(
                        f"ROUTE_OUTCOME_ASSERTION_MISMATCH: caller asserted {outcome!r}, "
                        f"resolver produced {resolved_outcome!r}"
                    )
                edge_raw = edges[resolved_outcome]
                if not isinstance(edge_raw, Mapping):
                    raise ClosedLoopRuntimeError(
                        f"ROUTE_INVALID: edge {resolved_outcome!r} for {step_id!r} must be a mapping"
                    )
                edge_payload = {
                    "outcome": resolved_outcome,
                    "source_step_id": step_id,
                    **edge_raw,
                }
                if "runtime_executable" not in edge_raw:
                    edge_payload["runtime_executable"] = True
                edge = PlanEdge.from_dict(edge_payload)
                if not edge.runtime_executable and not edge.is_terminal:
                    raise ClosedLoopRuntimeError(
                        "ROUTE_NOT_EXECUTABLE: declared non-executable route is provenance-only"
                    )

        # Unknown verbs are effectful by default. W5 must not infer that an
        # unfamiliar node action is harmless merely because it is on a plan.
        effectful = bool(action and action not in _READ_ONLY_ACTIONS)
        if effectful and not self._revalidate_authority(action):
            raise ClosedLoopRuntimeError("AUTHORITY_REQUIRED: exact authority revalidation failed; no effect or cursor advance")
        if effect is not None:
            effect(payload)
        if side_effect is not None:
            side_effect()

        target = "terminal" if terminal_step else (edge.target if edge is not None else step_id)
        control_state = self._cursor.control_state
        is_terminal = terminal_step or bool(edge and edge.is_terminal)
        if edge is not None and edge.target == "wait":
            control_state = "WAITING"
            target = step_id
        elif edge is not None and edge.target == "replan":
            control_state = "REPLAN_REQUIRED"
            target = step_id
        effective_sequence = sequence if sequence is not None else self._sequence + 1
        evidence_entry = {
            "status": resolved_outcome if resolved_outcome is not None else ("TERMINAL" if terminal_step else "EXECUTED"),
            "payload": dict(payload),
            "requested_action": action or None,
            "evidence_refs": list(evidence_refs),
        }
        self._completed_steps.append(step_id)
        self._evidence[step_id] = evidence_entry
        self._sequence = effective_sequence
        self._cursor = RunCursor(
            run_id=self._cursor.run_id,
            runtime_plan_ref=self._cursor.runtime_plan_ref,
            runtime_plan_digest=self._cursor.runtime_plan_digest,
            plan_revision=self._cursor.plan_revision,
            current_step_id=target,
            attempt=self._cursor.attempt + 1,
            control_state=control_state,
        )
        self._persist()
        return {
            "runtime_plan_ref": self._plan.get("runtime_plan_ref", ""),
            "implementation_plan_ref": self._plan.get("implementation_plan_ref", ""),
            "current_step": target,
            "is_terminal": is_terminal,
            "completed_steps": list(self._completed_steps),
            "evidence": json.loads(json.dumps(self._evidence)),
            "authority_revalidated": bool(effectful),
            "sequence": effective_sequence,
            "control_state": control_state,
        }

    def resume_wait(self) -> RunCursor:
        self._cursor = self._cursor.resume()
        self._persist()
        return self._cursor

    def switch_plan(self, plan: RuntimePlan | Mapping[str, Any], *, current_step_id: str | None = None) -> RunCursor:
        new_plan = plan if isinstance(plan, RuntimePlan) else RuntimePlan.from_dict(plan)
        self._cursor = self._cursor.switch_to(new_plan, current_step_id=current_step_id)
        self._plan = new_plan.to_dict()
        self._completed_steps = []
        self._evidence = {}
        self._sequence = 0
        self._persist()
        return self._cursor

    replan = switch_plan


# Backward-compatible import surface used by older tests.
__all__ = [
    "ClosedLoopRuntimeError", "ClosedLoopRuntimeExecutor", "FileRuntimeExecutionStateStore",
    "RuntimeExecutionState", "RunCursor",
]
