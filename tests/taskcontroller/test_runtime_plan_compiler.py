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
