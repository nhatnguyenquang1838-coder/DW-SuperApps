"""GWC-governed blueprint compiler: pinned blueprint + exact-read sources → RuntimePlan.

The compiler is the ONLY sanctioned path from a declared GovernedExecutionBlueprint
to an executable RuntimePlan.  It never grants authority; it only records the
authority requirements that GWC must independently satisfy.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from taskcontroller.domain.runtime_plan import (
    AuthorityRequirement,
    PlanEdge,
    RuntimePlan,
    RuntimePlanStep,
    RunbookBinding,
)
from taskcontroller.errors import TaskControllerValidationError


def _digest(value: Any) -> str:
    """Deterministic SHA-256 over canonical JSON (sorted keys)."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(f"{field} must be a non-empty string")
    return value


def compile_blueprint(
    payload: Mapping[str, Any],
    *,
    expected_blueprint_digest: str | None = None,
    expected_source_bindings: Mapping[str, Any] | None = None,
) -> RuntimePlan:
    """Compile a governed execution blueprint into a bound RuntimePlan.

    Args:
        payload: the governed execution blueprint dict.
        expected_blueprint_digest: if present, the blueprint must match exactly.
        expected_source_bindings: if present, source bindings must match exactly.

    Returns:
        A RuntimePlan bound to the exact blueprint + source inputs.

    Raises:
        TaskControllerValidationError: on any digest mismatch, missing binding,
            or topology violation.
    """
    if not isinstance(payload, Mapping):
        raise TaskControllerValidationError("blueprint must be a mapping")

    blueprint = dict(payload)

    # --- Exact-read: blueprint digest (independent of payload identity) -------
    blueprint_digest = _digest(blueprint)
    if expected_blueprint_digest and expected_blueprint_digest != blueprint_digest:
        raise TaskControllerValidationError(
            "blueprint digest mismatch: expected "
            f"{expected_blueprint_digest}, got {blueprint_digest}"
        )

    # --- Exact-read: source bindings must be reproducible --------------------
    raw_bindings = blueprint.get("source_bindings")
    if not isinstance(raw_bindings, Mapping):
        raise TaskControllerValidationError("source_bindings must be a mapping")
    source_bindings = dict(raw_bindings)

    if expected_source_bindings:
        expected = dict(expected_source_bindings)
        if expected != source_bindings:
            diff = {
                k: (expected.get(k), source_bindings.get(k))
                for k in set(expected) | set(source_bindings)
                if expected.get(k) != source_bindings.get(k)
            }
            raise TaskControllerValidationError(
                f"source binding mismatch: {diff}"
            )

    # --- Nodes → steps (bounded current-step only) ---------------------------
    raw_nodes = blueprint.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise TaskControllerValidationError("blueprint.nodes must be a non-empty list")

    steps: dict[str, RuntimePlanStep] = {}
    for node in raw_nodes:
        node_id = _require_text(node.get("node_id"), "node.node_id")
        action = _require_text(node.get("action"), "node.action")
        steps[action] = RuntimePlanStep(
            step_id=action,
            semantic_action=action,
            node_binding=node,
        )

    # --- Topology → edges (fail-closed on undeclared edges) ------------------
    raw_topology = blueprint.get("topology")
    if not isinstance(raw_topology, list):
        raise TaskControllerValidationError("blueprint.topology must be a list")

    declared_actions = set(steps)
    for topo in raw_topology:
        action = topo.get("action")
        if action not in declared_actions:
            raise TaskControllerValidationError(
                f"topology references undeclared action: {action}"
            )

        edge_map: dict[str, PlanEdge] = {}
        next_target = topo.get("next")
        if next_target:
            if next_target not in declared_actions and next_target not in {"terminal", "wait", "replan"}:
                raise TaskControllerValidationError(
                    f"edge target not declared: {next_target}"
                )
            edge_map["NEXT"] = PlanEdge(outcome="NEXT", target=next_target, kind="continue")

        raw_edges = topo.get("edges")
        if isinstance(raw_edges, Mapping):
            for outcome, edge in raw_edges.items():
                target = edge.get("target")
                kind = edge.get("kind", "continue")
                edge_map[outcome.upper()] = PlanEdge(
                    outcome=outcome.upper(), target=target, kind=kind
                )

        if edge_map:
            step = steps[action]
            steps[action] = RuntimePlanStep(
                step_id=step.step_id,
                semantic_action=step.semantic_action,
                edges=edge_map,
                node_binding=step.node_binding,
            )

    # --- Runbooks ------------------------------------------------------------
    raw_runbooks = blueprint.get("runbooks")
    runbooks: list[RunbookBinding] = []
    if isinstance(raw_runbooks, list):
        for rb in raw_runbooks:
            runbooks.append(
                RunbookBinding(
                    runbook_id=rb.get("runbook_id", ""),
                    revision=rb.get("revision", ""),
                    digest=rb.get("digest", ""),
                )
            )

    # --- Authority requirements (recorded, never granted) -------------------
    raw_auth = blueprint.get("authority_requirements")
    authority_requirements: list[AuthorityRequirement] = []
    if isinstance(raw_auth, list):
        for ar in raw_auth:
            authority_requirements.append(
                AuthorityRequirement(
                    action=ar.get("action", ""),
                    gate=ar.get("gate", ""),
                    required=bool(ar.get("required", False)),
                )
            )

    # --- Plan identity (deterministic from blueprint + sources) --------------
    plan_identity = _digest({"blueprint": blueprint, "source_bindings": source_bindings})

    return RuntimePlan(
        runtime_plan_ref=blueprint.get("implementation_plan_ref", ""),
        revision=plan_identity,
        steps=steps,
        source_bindings=source_bindings,
        runbooks=runbooks,
        authority_requirements=authority_requirements,
        blueprint_id=blueprint.get("blueprint_id", ""),
        blueprint_digest=blueprint_digest,
        task_id=blueprint.get("task_id", ""),
        scenario=blueprint.get("scenario", ""),
    )
