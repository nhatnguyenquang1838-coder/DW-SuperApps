"""M0: canonical RuntimePlan model contract.

One model across W1/W2/W4: a single RuntimePlanStep carries the W2 bounded
step fields (allowed_inputs/allowed_actions/evidence_refs) AND the W4
blueprint-bound fields (node_binding) plus plan-level source_bindings,
runbooks, authority_requirements, blueprint identity. Plus the canonical
EvidenceRecord schema and the compiler edge-membership validation that
W4 was missing.
"""

from __future__ import annotations

import pytest

from taskcontroller.domain.runtime_plan import (
    AuthorityRequirement,
    BindingErrorCode,
    PlanEdge,
    RuntimePlan,
    RuntimePlanStep,
    RunbookBinding,
)
from taskcontroller.errors import TaskControllerValidationError


def _plan_payload(**overrides):
    payload = {
        "runtime_plan_ref": "plan.test/r1",
        "revision": "rev-1",
        "steps": {
            "inspect": {
                "step_id": "inspect",
                "semantic_action": "read",
                "allowed_inputs": ("target",),
                "allowed_actions": ("read", "search"),
                "evidence_refs": ("inspect.evidence",),
                "edges": {"found": {"outcome": "found", "target": "report", "kind": "continue"}},
            },
            "report": {
                "step_id": "report",
                "semantic_action": "write",
                "allowed_inputs": ("report",),
                "allowed_actions": ("write",),
                "evidence_refs": ("report.evidence",),
                "edges": {"done": {"outcome": "done", "target": "terminal", "kind": "terminal"}},
            },
        },
        "source_bindings": {"paths": ["core/"]},
        "runbooks": [{"runbook_id": "rb-1", "revision": "1", "digest": "d1"}],
        "authority_requirements": [{"action": "write", "gate": "G3", "required": True}],
        "blueprint_id": "bp-1",
        "blueprint_digest": "sha256:abc",
        "task_id": "SCRUM-668",
        "scenario": "cert",
    }
    payload.update(overrides)
    return payload


def test_canonical_step_has_both_w2_and_w4_fields():
    plan = RuntimePlan.from_dict(_plan_payload())
    step = plan.step("inspect")
    # W2 bounded-step fields
    assert step.allowed_inputs == ("target",)
    assert step.allowed_actions == ("read", "search")
    assert step.evidence_refs == ("inspect.evidence",)
    # W4 blueprint-bound field
    assert step.node_binding is None
    assert "inspect" in plan.steps


def test_canonical_plan_has_w4_blueprint_fields():
    plan = RuntimePlan.from_dict(_plan_payload())
    assert plan.source_bindings == {"paths": ["core/"]}
    assert [rb.runbook_id for rb in plan.runbooks] == ["rb-1"]
    assert [ar.action for ar in plan.authority_requirements] == ["write"]
    assert plan.blueprint_id == "bp-1"
    assert plan.blueprint_digest == "sha256:abc"
    assert plan.task_id == "SCRUM-668"
    assert plan.scenario == "cert"


def test_canonical_digest_covers_w2_and_w4_fields():
    a = RuntimePlan.from_dict(_plan_payload())
    b = RuntimePlan.from_dict(
        _plan_payload(runbooks=[{"runbook_id": "rb-1", "revision": "1", "digest": "d1"}])
    )
    # same semantic content -> same digest
    assert a.runtime_plan_digest == b.runtime_plan_digest
    c = RuntimePlan.from_dict(_plan_payload(task_id="SCRUM-999"))
    assert a.runtime_plan_digest != c.runtime_plan_digest


def test_canonical_plan_rejects_authority_granted():
    payload = _plan_payload(authority_granted=True)
    with pytest.raises(TaskControllerValidationError):
        RuntimePlan.from_dict(payload)


def test_canonical_roundtrip_to_dict_from_dict():
    plan = RuntimePlan.from_dict(_plan_payload())
    restored = RuntimePlan.from_dict(plan.to_dict())
    assert restored.to_dict() == plan.to_dict()
    assert restored.runtime_plan_digest == plan.runtime_plan_digest


def test_canonical_compiler_validates_edge_target_membership():
    """W4 gap: raw edge target must be a declared step or terminal set."""
    # terminal target is allowed
    RuntimePlan.from_dict(_plan_payload())
    # target pointing to a step that doesn't exist -> error
    bad = _plan_payload()
    bad["steps"]["inspect"]["edges"]["found"]["target"] = "ghost-step"
    with pytest.raises(TaskControllerValidationError):
        RuntimePlan.from_dict(bad)


def test_evidence_record_schema_fields():
    """Canonical EvidenceRecord schema for W7 certification (designer M1/M2)."""
    from taskcontroller.runtime.evidence_record import EvidenceRecord

    rec = EvidenceRecord(
        expected_output={"status": "ok"},
        actual_output={"status": "ok"},
        verdict_reason="all AC pass",
        authority_revalidated=True,
        readback_digest="sha256:readback",
        plan_digest_at_execution="sha256:plan",
    )
    assert rec.verdict_reason == "all AC pass"
    assert rec.plan_digest_at_execution == "sha256:plan"
    payload = rec.to_dict()
    assert payload["expected_output"] == {"status": "ok"}
    assert payload["authority_revalidated"] is True


def test_evidence_record_roundtrip():
    from taskcontroller.runtime.evidence_record import EvidenceRecord

    rec = EvidenceRecord(
        expected_output="ok",
        actual_output="ok",
        verdict_reason="pass",
        authority_revalidated=True,
        readback_digest="d",
        plan_digest_at_execution="p",
    )
    restored = EvidenceRecord.from_dict(rec.to_dict())
    assert restored.to_dict() == rec.to_dict()
