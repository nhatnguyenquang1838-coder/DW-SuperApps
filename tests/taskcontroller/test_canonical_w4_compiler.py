from __future__ import annotations

import copy
import hashlib
import importlib
import json

import pytest

from taskcontroller.domain.runtime_plan import RuntimePlan
from taskcontroller.errors import TaskControllerValidationError


DIGEST = "sha256:" + "a" * 64


def _blueprint() -> dict:
    """Fixture shaped from W3 commit 0f2ba5b2's actual contract."""
    return {
        "schema_version": "1.0",
        "artifact_type": "governed-execution-blueprint",
        "blueprint_id": "blueprint.scrum-673",
        "task_id": "SCRUM-673",
        "scenario": "standard_pr_delivery",
        "source_bindings": {
            "gwc_sha": "0f2ba5b2aeedc50d428f552fd30822f8bada04ca",
            "flow_ref": "core/node-architect/profile-registry.json",
            "flow_revision": "flow-r1",
            "flow_digest": DIGEST,
            "policy_ref": "core/node-architect/gate-applicability-policy-registry.json",
            "policy_revision": "policy-r1",
            "policy_digest": DIGEST,
            "project_profile_ref": "projects/gwc/project-profile.yaml",
        },
        "runbooks": [
            {"runbook_id": "standard-pr-delivery", "revision": "1.0.0", "digest": DIGEST}
        ],
        "nodes": [
            {
                "action": "inspect",
                "node_id": "reference.inspect",
                "node_instruction_ref": "core/node-architect/node-instructions/reference/inspect.node-instruction.yaml",
                "node_instruction_digest": DIGEST,
                "implementation_ref": "tools/node_architect/inspect.py",
                "route_profile_revision": "route-r1",
                "graph_revision": "graph-r1",
                "node_registry_revision": "nodes-r1",
            },
            {
                "action": "validate",
                "node_id": "validation.validate",
                "node_instruction_ref": "core/node-architect/node-instructions/validation/validate.node-instruction.yaml",
                "node_instruction_digest": DIGEST,
                "implementation_ref": "tools/node_architect/validate.py",
                "route_profile_revision": "route-r1",
                "graph_revision": "graph-r1",
                "node_registry_revision": "nodes-r1",
            },
        ],
        "topology": [
            {"action": "inspect", "node_id": "reference.inspect", "next": "validate"},
            {
                "action": "validate",
                "node_id": "validation.validate",
                "next": "terminal",
                "edges": {
                    "PASS": {"target": "terminal", "kind": "terminal"},
                    "RETRY": {"target": "validate", "kind": "retry"},
                },
            },
        ],
        "authority_requirements": [
            {"action": "validate", "gate": "G3_PR", "required": True}
        ],
        "implementation_plan_ref": "implementation-plan/SCRUM-673/r1",
    }


def _compile(payload: dict, **kwargs):
    """Import inside the test so RED is an assertion about the missing feature."""
    try:
        compiler = importlib.import_module("taskcontroller.compiler")
    except ModuleNotFoundError as exc:
        pytest.fail(f"W4 compiler is not implemented: {exc}")
    return compiler.compile_blueprint(payload, **kwargs)


def test_compiles_pinned_w3_blueprint_to_bound_runtime_plan():
    plan = _compile(_blueprint())

    assert isinstance(plan, RuntimePlan)
    assert plan.runtime_plan_ref == "implementation-plan/SCRUM-673/r1"
    assert plan.revision.startswith("sha256:")
    assert list(plan.steps) == ["inspect", "validate"]
    assert plan.step("inspect").semantic_action == "inspect"
    assert plan.step("validate").node_binding["node_instruction_digest"] == DIGEST
    assert plan.resolve_edge("inspect", "NEXT").target == "validate"
    assert plan.resolve_edge("validate", "PASS").target == "terminal"
    assert plan.resolve_edge("validate", "RETRY").kind == "retry"
    assert plan.source_bindings["gwc_sha"] == "0f2ba5b2aeedc50d428f552fd30822f8bada04ca"
    assert plan.runbooks[0]["runbook_id"] == "standard-pr-delivery"
    assert plan.authority_requirements[0]["gate"] == "G3_PR"


def test_identical_canonical_blueprints_have_identical_plan_identity_and_payload():
    first = _compile(_blueprint())
    second = _compile(copy.deepcopy(_blueprint()))

    assert first.blueprint_digest == second.blueprint_digest
    assert first.runtime_plan_digest == second.runtime_plan_digest
    assert first.to_dict() == second.to_dict()


def test_rejects_stale_blueprint_and_source_inputs():
    with pytest.raises(TaskControllerValidationError, match="blueprint digest"):
        _compile(_blueprint(), expected_blueprint_digest="sha256:" + "b" * 64)

    expected = dict(_blueprint()["source_bindings"])
    expected["flow_revision"] = "stale"
    with pytest.raises(TaskControllerValidationError, match="source binding"):
        _compile(_blueprint(), expected_source_bindings=expected)


def test_rejects_topology_edge_not_declared_by_blueprint():
    payload = _blueprint()
    payload["topology"][0]["next"] = "ghost-action"

    with pytest.raises(TaskControllerValidationError, match="edge"):
        _compile(payload)


def test_authority_requirements_never_become_authority_grant():
    plan = _compile(_blueprint())
    serialized = plan.to_dict()

    assert "authority_granted" not in serialized
    assert "write_authority_granted" not in serialized
    assert serialized["authority_requirements"] == _blueprint()["authority_requirements"]


def test_compiled_plan_can_be_persisted_and_round_tripped():
    plan = _compile(_blueprint())
    restored = RuntimePlan.from_dict(json.loads(json.dumps(plan.to_dict())))

    assert restored == plan
    assert restored.runtime_plan_digest == plan.runtime_plan_digest


def test_compile_edges_sequence_preserves_route_semantics():
    """seq=13 M1 interop: blueprint with list-valued edges compiles losslessly,
    preserving kind, runtime_executable, source/target gate, and condition_id."""
    payload = _blueprint()
    payload["topology"] = [
        {
            "action": "inspect",
            "node_id": "reference.inspect",
            "edges": [
                {
                    "target": "validate",
                    "kind": "continue",
                    "condition_id": None,
                    "runtime_executable": True,
                    "source_gate": "G3_PR",
                    "target_gate": "G3_PR",
                },
            ],
        },
        {
            "action": "validate",
            "node_id": "validation.validate",
            "edges": [
                {
                    "target": "terminal",
                    "kind": "terminal",
                    "condition_id": None,
                    "runtime_executable": False,
                    "source_gate": "G3_PR",
                    "target_gate": None,
                },
            ],
        },
    ]

    plan = _compile(payload)
    step = plan.step("inspect")
    edge = step.edges["CONTINUE"]
    assert edge.target == "validate"
    assert edge.kind == "continue"
    assert edge.runtime_executable is True
    assert edge.source_gate == "G3_PR"
    assert edge.target_gate == "G3_PR"
    assert edge.condition_id is None


def test_compile_fails_closed_on_ambiguous_multi_route_without_discriminator():
    """seq=13 M1: >1 executable route of same kind without condition_id
    must raise BLUEPRINT_ROUTE_DISCRIMINATOR_REQUIRED."""
    payload = _blueprint()
    payload["topology"] = [
        {
            "action": "inspect",
            "node_id": "reference.inspect",
            "edges": [
                {
                    "target": "validate",
                    "kind": "continue",
                    "condition_id": None,
                    "runtime_executable": True,
                    "source_gate": "G3_PR",
                    "target_gate": "G3_PR",
                },
                {
                    "target": "validate",
                    "kind": "continue",
                    "condition_id": None,
                    "runtime_executable": True,
                    "source_gate": "G3_PR",
                    "target_gate": "G3_PR",
                },
            ],
        },
        {
            "action": "validate",
            "node_id": "validation.validate",
            "edges": [
                {
                    "target": "terminal",
                    "kind": "terminal",
                    "runtime_executable": False,
                },
            ],
        },
    ]

    with pytest.raises(TaskControllerValidationError, match="BLUEPRINT_ROUTE_DISCRIMINATOR_REQUIRED"):
        _compile(payload)


def test_compile_ci_run_capture_active_route_preserves_non_executable():
    """seq=13 cross-repo fixture: blueprint with mixed executable/non-executable
    routes compiles losslessly — all route semantics are preserved in the plan,
    with runtime_executable marking each edge's executability."""
    payload = _blueprint()
    payload["topology"] = [
        {
            "action": "inspect",
            "node_id": "reference.inspect",
            "edges": [
                {
                    "target": "validate",
                    "kind": "continue",
                    "condition_id": None,
                    "runtime_executable": True,
                    "source_gate": "G3_PR",
                    "target_gate": "G3_PR",
                },
                {
                    "target": "validate",
                    "kind": "human_required",
                    "condition_id": None,
                    "runtime_executable": False,
                    "source_gate": "G3_PR",
                    "target_gate": None,
                },
            ],
        },
        {
            "action": "validate",
            "node_id": "validation.validate",
            "edges": [
                {
                    "target": "terminal",
                    "kind": "terminal",
                    "runtime_executable": False,
                },
            ],
        },
    ]

    plan = _compile(payload)
    # Executable route preserved as CONTINUE.
    edge = plan.resolve_edge("inspect", "CONTINUE")
    assert edge.target == "validate"
    assert edge.kind == "continue"
    assert edge.runtime_executable is True
    # Non-executable route also preserved in plan with runtime_executable=False.
    hr_edge = plan.resolve_edge("inspect", "HUMAN_REQUIRED")
    assert hr_edge.kind == "human_required"
    assert hr_edge.runtime_executable is False
    # Round-trip preserves both route semantics.
    restored = RuntimePlan.from_dict(json.loads(json.dumps(plan.to_dict())))
    assert restored == plan


def test_compile_fails_closed_when_same_kind_routes_collide_despite_condition_id():
    """seq=14 W4: edge_map is keyed by edge.outcome; two executable 'continue'
    routes (even with DIFFERENT condition_ids) both resolve to outcome
    'CONTINUE' and the mapping cannot hold both. The compiler must FAIL CLOSED
    with BLUEPRINT_ROUTE_DISCRIMINATOR_REQUIRED — never silently overwrite/drop
    the second distinct route on the first's outcome slot."""
    payload = _blueprint()
    payload["topology"] = [
        {
            "action": "inspect",
            "node_id": "reference.inspect",
            "edges": [
                {
                    "target": "validate",
                    "kind": "continue",
                    "condition_id": "cond-main",
                    "runtime_executable": True,
                    "source_gate": "G3_PR",
                    "target_gate": "G3_PR",
                },
                {
                    "target": "validate",
                    "kind": "continue",
                    "condition_id": "cond-fallback",
                    "runtime_executable": True,
                    "source_gate": "G3_PR",
                    "target_gate": "G3_PR",
                },
            ],
        },
        {
            "action": "validate",
            "node_id": "validation.validate",
            "edges": [
                {
                    "target": "terminal",
                    "kind": "terminal",
                    "runtime_executable": False,
                },
            ],
        },
    ]

    # Two distinct executable continue routes collide on outcome 'CONTINUE'.
    # Failing closed beats silently overwriting one route.
    with pytest.raises(TaskControllerValidationError, match="BLUEPRINT_ROUTE_DISCRIMINATOR_REQUIRED"):
        _compile(payload)


def test_compile_preserves_distinct_kind_routes_with_condition_ids():
    """seq=14 W4: routes that do NOT collide on outcome (different kinds) are
    each preserved with their own condition_id — no false-positive fail."""
    payload = _blueprint()
    payload["topology"] = [
        {
            "action": "inspect",
            "node_id": "reference.inspect",
            "edges": [
                {
                    "target": "validate",
                    "kind": "continue",
                    "condition_id": "cond-main",
                    "runtime_executable": True,
                    "source_gate": "G3_PR",
                    "target_gate": "G3_PR",
                },
                {
                    "target": "validate",
                    "kind": "human_required",
                    "condition_id": "cond-escalate",
                    "runtime_executable": False,
                    "source_gate": "G3_PR",
                    "target_gate": None,
                },
            ],
        },
        {
            "action": "validate",
            "node_id": "validation.validate",
            "edges": [
                {
                    "target": "terminal",
                    "kind": "terminal",
                    "runtime_executable": False,
                },
            ],
        },
    ]

    plan = _compile(payload)
    edges = plan.step("inspect").edges
    assert len(edges) == 2, f"expected both distinct-kind routes preserved, got {list(edges)}"
    continue_edge = edges["CONTINUE"]
    hr_edge = edges["HUMAN_REQUIRED"]
    assert continue_edge.condition_id == "cond-main"
    assert hr_edge.condition_id == "cond-escalate"
    # Round-trip preserves both routes + condition discriminators.
    restored = RuntimePlan.from_dict(json.loads(json.dumps(plan.to_dict())))
    assert restored == plan
