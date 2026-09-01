"""GWC-governed blueprint compiler: pinned blueprint + exact-read sources → RuntimePlan.

The compiler is the ONLY sanctioned path from a declared GovernedExecutionBlueprint
to an executable RuntimePlan.  It never grants authority; it only records the
authority requirements that GWC must independently satisfy.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from taskcontroller.domain.runtime_plan import (
    AuthorityRequirement,
    PlanEdge,
    RuntimePlan,
    RuntimePlanStep,
    RunbookBinding,
    _ALLOWED_EDGE_KINDS,
    _NON_STEP_TARGETS,
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


def _load_node_instruction(node: Mapping[str, Any], root: str | Path | None) -> Mapping[str, Any] | None:
    """Dereference a pinned node instruction and verify its content digest."""
    if not root:
        return None
    ref = _require_text(node.get("node_instruction_ref"), "node.node_instruction_ref")
    path = Path(root) / ref
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TaskControllerValidationError(f"node instruction unreadable: {ref}") from exc
    actual = "sha256:" + hashlib.sha256(raw).hexdigest()
    expected = _require_text(node.get("node_instruction_digest"), "node.node_instruction_digest")
    if actual != expected:
        raise TaskControllerValidationError(
            f"node instruction digest mismatch: {ref}: expected {expected}, got {actual}"
        )
    try:
        import yaml
        loaded = yaml.safe_load(raw)
    except Exception as exc:
        raise TaskControllerValidationError(f"node instruction parse failed: {ref}") from exc
    if not isinstance(loaded, Mapping) or loaded.get("node_id") != node.get("node_id"):
        raise TaskControllerValidationError(f"node instruction identity mismatch: {ref}")
    return loaded


def compile_blueprint(
    payload: Mapping[str, Any],
    *,
    expected_blueprint_digest: str | None = None,
    expected_source_bindings: Mapping[str, Any] | None = None,
    node_instruction_root: str | Path | None = None,
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
        instruction = _load_node_instruction(node, node_instruction_root)
        capabilities = instruction or node.get("capabilities") or {}
        allowed_actions = tuple(capabilities.get("allowed_actions", node.get("allowed_actions", ())))
        allowed_inputs = tuple(capabilities.get("inputs", node.get("allowed_inputs", ())))
        evidence_refs = tuple(capabilities.get("evidence_required", node.get("evidence_refs", ())))
        steps[action] = RuntimePlanStep(
            step_id=action,
            semantic_action=action,
            node_binding=node,
            allowed_inputs=allowed_inputs,
            allowed_actions=allowed_actions,
            evidence_refs=evidence_refs,
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

        # seq=13 M1 interop: compile explicit route semantics from blueprint.
        # Priority: "edges" sequence (preserved route rows) over legacy scalar "next".
        raw_edges = topo.get("edges")
        if isinstance(raw_edges, Sequence) and not isinstance(raw_edges, (str, bytes)):
            # New M1 shape: list of route-row mappings with target/kind/etc.
            route_edges: list[PlanEdge] = []
            for row in raw_edges:
                if not isinstance(row, Mapping):
                    raise TaskControllerValidationError(
                        "topology.edges items must be mappings"
                    )
                tgt = row.get("target")
                if not isinstance(tgt, str) or not tgt:
                    raise TaskControllerValidationError(
                        "topology.edges target must be a non-empty string"
                    )
                kind = str(row.get("kind", "continue"))
                if kind not in _ALLOWED_EDGE_KINDS:
                    raise TaskControllerValidationError(
                        f"unsupported route edge kind: {kind!r}"
                    )
                if tgt not in declared_actions and tgt not in _NON_STEP_TARGETS:
                    raise TaskControllerValidationError(
                        f"edge target not declared: {tgt}"
                    )
                route_edges.append(PlanEdge(
                    outcome=kind.upper(),
                    target=tgt,
                    kind=kind,
                    condition_id=row.get("condition_id"),
                    runtime_executable=bool(row.get("runtime_executable", False)),
                    source_gate=row.get("source_gate"),
                    target_gate=row.get("target_gate"),
                ))

            # Fail-closed ambiguity check: if >1 executable route shares the
            # same kind and has no declared condition_id discriminator,
            # the caller must not silently select one.
            executable_by_kind: dict[str, list[PlanEdge]] = {}
            for edge in route_edges:
                if edge.runtime_executable:
                    executable_by_kind.setdefault(edge.kind, []).append(edge)
            for kind, candidates in executable_by_kind.items():
                if len(candidates) > 1 and all(
                    e.condition_id is None for e in candidates
                ):
                    raise TaskControllerValidationError(
                        "BLUEPRINT_ROUTE_DISCRIMINATOR_REQUIRED: "
                        f"{action} has {len(candidates)} executable '{kind}' routes "
                        "without declared condition_id discriminators"
                    )

            # Deterministic ordering: by target name for reproducibility.
            route_edges.sort(key=lambda e: (e.kind, e.target))
            for edge in route_edges:
                # seq=14 W4: never silently overwrite a distinct route. The edge
                # mapping is keyed by outcome; if two distinct routes resolve to
                # the same outcome slot, fail closed rather than drop one.
                existing = edge_map.get(edge.outcome)
                if existing is not None and existing != edge:
                    raise TaskControllerValidationError(
                        "BLUEPRINT_ROUTE_DISCRIMINATOR_REQUIRED: "
                        f"{action} has multiple routes colliding on outcome "
                        f"{edge.outcome!r} (kind={edge.kind!r}) — the edge "
                        "mapping cannot hold both distinct routes; declare "
                        "distinct kinds/outcomes for each route"
                    )
                edge_map[edge.outcome] = edge

        else:
            # Legacy scalar "next" or explicit raw_edges mapping (legacy shape).
            next_target = topo.get("next")
            if next_target:
                if next_target not in declared_actions and next_target not in _NON_STEP_TARGETS:
                    raise TaskControllerValidationError(
                        f"edge target not declared: {next_target}"
                    )
                edge_map["NEXT"] = PlanEdge(outcome="NEXT", target=next_target, kind="continue", runtime_executable=True)

            raw_legacy_edges = topo.get("edges")
            if isinstance(raw_legacy_edges, Mapping):
                for outcome, edge in raw_legacy_edges.items():
                    target = edge.get("target")
                    kind = edge.get("kind", "continue")
                    edge_map[outcome.upper()] = PlanEdge(
                        outcome=outcome.upper(), target=target, kind=kind, runtime_executable=True
                    )

        if edge_map:
            step = steps[action]
            steps[action] = RuntimePlanStep(
                step_id=step.step_id,
                semantic_action=step.semantic_action,
                edges=edge_map,
                route_evidence=tuple(edge.to_dict() for edge in edge_map.values()),
                node_binding=step.node_binding,
                allowed_inputs=step.allowed_inputs,
                allowed_actions=step.allowed_actions,
                evidence_refs=step.evidence_refs,
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
        runtime_plan_ref=blueprint.get("runtime_plan_ref") or f"runtime-plan/{blueprint.get('task_id', 'unknown')}/{blueprint.get('blueprint_id', blueprint_digest[7:23])}",
        revision=plan_identity,
        implementation_plan_ref=blueprint.get("implementation_plan_ref", ""),
        steps=steps,
        source_bindings=source_bindings,
        runbooks=runbooks,
        authority_requirements=authority_requirements,
        blueprint_id=blueprint.get("blueprint_id", ""),
        blueprint_digest=blueprint_digest,
        task_id=blueprint.get("task_id", ""),
        scenario=blueprint.get("scenario", ""),
    )
