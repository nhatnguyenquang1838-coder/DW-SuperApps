"""TC-MBX-606: deterministic, evidence-only parent synthesis."""

from __future__ import annotations

import hashlib
import json

import pytest

from taskcontroller.domain.enums import DecisionType, ReviewVerdict
from taskcontroller.execution.parent_synthesis import (
    ControllerDecision,
    ParentSynthesisError,
    synthesize_parent_result,
)
from taskcontroller.execution.result_normalizer import ChildResultNormalizer, NormalizationStatus


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _finding(
    *,
    finding_id: str,
    reviewer: str,
    claim: str,
    recommendation: str,
    severity: str = "minor",
    conflict_group: str | None = None,
) -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "category": "boundary",
        "lens": "reliability",
        "claim": claim,
        "evidence_refs": [f"evidence-{finding_id}"],
        "recommendation": recommendation,
        "reviewer": reviewer,
        "disposition": "OPEN",
        "conflict_group": conflict_group,
    }


def _child(
    *,
    child_id: str,
    reviewer: str,
    findings: list[dict[str, object]],
    contract: str = "child-contract",
    source: str = "source-commit",
):
    normalizer = ChildResultNormalizer(
        child_id=child_id,
        child_contract_digest=_digest(contract),
        source_digest=_digest(source),
        lens="reliability",
        reviewer=reviewer,
    )
    return normalizer.normalize({"findings": findings})


def _decision(
    decision_type: DecisionType,
    *,
    decision_id: str = "decision-1",
    run_ref: str = "run-1",
    evidence_refs: tuple[str, ...] = ("parent-evidence",),
) -> ControllerDecision:
    return ControllerDecision(
        decision_id=decision_id,
        run_ref=run_ref,
        decision_type=decision_type,
        rationale="Controller decision is bound to the synthesized evidence",
        evidence_refs=evidence_refs,
    )


def test_parent_result_is_verifiable_without_raw_subagent_chat() -> None:
    child_a = _child(
        child_id="child-a",
        reviewer="reviewer-a",
        findings=[
            _finding(
                finding_id="finding-a",
                reviewer="reviewer-a",
                claim="Retry boundary is observable",
                recommendation="Keep the audit reference",
            )
        ],
    )
    child_b = _child(
        child_id="child-b",
        reviewer="reviewer-b",
        findings=[
            _finding(
                finding_id="finding-b",
                reviewer="reviewer-b",
                claim="  retry boundary is observable ",
                recommendation="Keep the audit reference",
            )
        ],
    )

    result = synthesize_parent_result(
        (child_b, child_a),
        proposed_verdict=ReviewVerdict.PASS,
        residual_risks=("Monitor the next bounded retry",),
        unresolved_questions=("Should the retry budget be revisited?",),
        controller_decision=_decision(DecisionType.COMPLETE),
    )

    payload = result.to_dict()
    assert result.final_verdict is ReviewVerdict.PASS
    assert result.controller_decision.decision_type is DecisionType.COMPLETE
    assert [item.child_id for item in result.child_refs] == ["child-a", "child-b"]
    assert len(result.findings) == 1
    assert result.findings[0].provenance_count == 2
    assert payload["child_refs"][0]["result_digest"].startswith("sha256:")
    assert payload["result_digest"] == result.result_digest
    serialized = json.dumps(payload)
    assert '"raw_output":' not in serialized
    assert '"transcript":' not in serialized
    assert "retry boundary is observable" not in serialized

    reversed_result = synthesize_parent_result(
        (child_a, child_b),
        proposed_verdict=ReviewVerdict.PASS,
        residual_risks=("Monitor the next bounded retry",),
        unresolved_questions=("Should the retry budget be revisited?",),
        controller_decision=_decision(DecisionType.COMPLETE),
    )
    assert reversed_result.to_dict() == payload


def test_critical_finding_cannot_be_downgraded_to_controller_complete() -> None:
    child = _child(
        child_id="child-critical",
        reviewer="reviewer-security",
        findings=[
            _finding(
                finding_id="critical-1",
                reviewer="reviewer-security",
                claim="Current generation can be bypassed",
                recommendation="Block advancement",
                severity="critical",
            )
        ],
    )

    result = synthesize_parent_result(
        (child,),
        proposed_verdict=ReviewVerdict.PASS,
        controller_decision=_decision(DecisionType.WAIT),
    )

    assert result.final_verdict is ReviewVerdict.NEEDS_FIX
    assert result.controller_decision.decision_type is DecisionType.WAIT
    assert result.findings[0].representative.severity == "critical"

    with pytest.raises(ParentSynthesisError, match="Controller decision"):
        synthesize_parent_result(
            (child,),
            proposed_verdict=ReviewVerdict.PASS,
            controller_decision=_decision(DecisionType.COMPLETE),
        )


def test_unresolved_material_conflict_is_visible_and_escalated() -> None:
    child_a = _child(
        child_id="child-a",
        reviewer="reviewer-a",
        findings=[
            _finding(
                finding_id="finding-a",
                reviewer="reviewer-a",
                claim="Fence is enforced",
                recommendation="Allow continuation",
                severity="major",
                conflict_group="fence-1",
            )
        ],
    )
    child_b = _child(
        child_id="child-b",
        reviewer="reviewer-b",
        findings=[
            _finding(
                finding_id="finding-b",
                reviewer="reviewer-b",
                claim="Fence can be bypassed",
                recommendation="Escalate before continuation",
                severity="major",
                conflict_group="fence-1",
            )
        ],
    )

    result = synthesize_parent_result(
        (child_a, child_b),
        proposed_verdict=ReviewVerdict.PASS,
        controller_decision=_decision(DecisionType.ESCALATE),
    )

    assert result.final_verdict is ReviewVerdict.NEEDS_CLARIFICATION
    assert result.controller_decision.decision_type is DecisionType.ESCALATE
    assert result.conflicts[0].conflict_id == "fence-1"
    assert result.conflicts[0].disposition.value == "UNRESOLVED"
    assert result.unresolved_questions == (
        "Controller/Human adjudication required for conflict group fence-1",
    )
    assert result.residual_risks
    assert result.to_dict()["conflicts"][0]["finding_ids"] == ["finding-a", "finding-b"]


def test_failed_or_retryable_child_is_not_synthesized() -> None:
    failed = ChildResultNormalizer(child_id="failed-child").normalize(
        {"status": "FAILED", "failure_code": "PROVIDER_ERROR", "message": "private detail"}
    )
    assert failed.status is NormalizationStatus.FAILED

    with pytest.raises(ParentSynthesisError, match="incomplete child result"):
        synthesize_parent_result(
            (failed,),
            controller_decision=_decision(DecisionType.WAIT),
        )


def test_duplicate_child_identity_is_rejected_even_when_digest_matches() -> None:
    child = _child(
        child_id="same-child",
        reviewer="reviewer-a",
        findings=[
            _finding(
                finding_id="finding-a",
                reviewer="reviewer-a",
                claim="Stable evidence",
                recommendation="Keep evidence",
            )
        ],
    )

    with pytest.raises(ParentSynthesisError, match="duplicate child_id"):
        synthesize_parent_result(
            (child, child),
            controller_decision=_decision(DecisionType.WAIT),
        )


def test_controller_decision_requires_machine_evidence() -> None:
    with pytest.raises(ParentSynthesisError, match="evidence_refs"):
        _decision(DecisionType.WAIT, evidence_refs=())

    with pytest.raises(ParentSynthesisError, match="decision_type"):
        ControllerDecision(
            decision_id="decision-1",
            run_ref="run-1",
            decision_type="not-a-decision",  # type: ignore[arg-type]
            rationale="invalid",
            evidence_refs=("evidence",),
        )


def test_invalid_child_input_and_conflicting_finding_identity_fail_closed() -> None:
    with pytest.raises(ParentSynthesisError, match="NormalizedChildResult"):
        synthesize_parent_result(
            (object(),),  # type: ignore[arg-type]
            controller_decision=_decision(DecisionType.WAIT),
        )

    child_a = _child(
        child_id="child-a",
        reviewer="reviewer-a",
        findings=[
            _finding(
                finding_id="same-finding",
                reviewer="reviewer-a",
                claim="First claim",
                recommendation="First recommendation",
            )
        ],
    )
    child_b = _child(
        child_id="child-b",
        reviewer="reviewer-b",
        findings=[
            _finding(
                finding_id="same-finding",
                reviewer="reviewer-b",
                claim="Conflicting claim",
                recommendation="Second recommendation",
            )
        ],
    )

    with pytest.raises(ParentSynthesisError, match="conflicting finding"):
        synthesize_parent_result(
            (child_a, child_b),
            controller_decision=_decision(DecisionType.WAIT),
        )


def test_mapping_controller_decision_round_trips_without_raw_context() -> None:
    child = _child(
        child_id="child-a",
        reviewer="reviewer-a",
        findings=[
            _finding(
                finding_id="finding-a",
                reviewer="reviewer-a",
                claim="Evidence is bounded",
                recommendation="Continue",
            )
        ],
    )
    result = synthesize_parent_result(
        (child,),
        controller_decision={
            "decision_id": "decision-map",
            "run_ref": "run-map",
            "decision_type": "COMPLETE",
            "rationale": "Mapped Controller decision",
            "evidence_refs": ["parent-evidence"],
        },
    )

    assert result.controller_decision.decision_id == "decision-map"
    assert result.to_dict()["controller_decision"]["decision_type"] == "COMPLETE"
    assert all("raw_output" not in key for key in result.to_dict())
