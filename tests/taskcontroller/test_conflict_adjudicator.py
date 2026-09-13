"""TC-MBX-605: detect and adjudicate material finding conflicts."""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import DecisionType, ReviewVerdict
from taskcontroller.execution.conflict_adjudicator import (
    ConflictAdjudicationError,
    ConflictDisposition,
    ConflictResolution,
    adjudicate_conflicts,
)
from taskcontroller.execution.result_normalizer import NormalizedFinding


def _finding(
    *,
    finding_id: str,
    reviewer: str,
    claim: str,
    recommendation: str,
    severity: str = "major",
    evidence_refs: tuple[str, ...] = (),
    conflict_group: str | None = "boundary-1",
    disposition: str = "OPEN",
) -> NormalizedFinding:
    return NormalizedFinding(
        finding_id=finding_id,
        severity=severity,
        category="boundary",
        lens="security-reliability",
        claim=claim,
        evidence_refs=evidence_refs or (f"evidence-{finding_id}",),
        recommendation=recommendation,
        reviewer=reviewer,
        disposition=disposition,
        conflict_group=conflict_group,
    )


def _conflicting_findings() -> tuple[NormalizedFinding, NormalizedFinding]:
    return (
        _finding(
            finding_id="finding-a",
            reviewer="reviewer-a",
            claim="Boundary permits an unsafe mutation",
            recommendation="Block release",
            severity="critical",
            evidence_refs=("artifact-a", "line-10"),
        ),
        _finding(
            finding_id="finding-b",
            reviewer="reviewer-b",
            claim="Boundary prevents the unsafe mutation",
            recommendation="Allow release",
            severity="major",
            evidence_refs=("artifact-b", "line-20"),
        ),
    )


def test_unresolved_material_conflict_escalates_and_needs_clarification() -> None:
    result = adjudicate_conflicts(
        _conflicting_findings(),
        proposed_verdict=ReviewVerdict.PASS,
    )

    assert result.final_verdict is ReviewVerdict.NEEDS_CLARIFICATION
    assert result.decision is DecisionType.ESCALATE
    assert result.material_conflict_count == 1
    conflict = result.conflicts[0]
    assert conflict.conflict_id == "boundary-1"
    assert conflict.finding_ids == ("finding-a", "finding-b")
    assert conflict.reviewers == ("reviewer-a", "reviewer-b")
    assert conflict.severities == ("critical", "major")
    assert conflict.evidence_refs == ("artifact-a", "artifact-b", "line-10", "line-20")
    assert conflict.disposition is ConflictDisposition.UNRESOLVED
    assert conflict.residual_risk
    assert result.to_dict()["status"] == "NEEDS_CLARIFICATION"


def test_resolved_material_conflict_requires_resolution_evidence() -> None:
    findings = _conflicting_findings()

    with pytest.raises(ConflictAdjudicationError, match="resolution evidence"):
        adjudicate_conflicts(
            findings,
            resolutions={
                "boundary-1": ConflictResolution(
                    disposition=ConflictDisposition.RESOLVED,
                    rationale="Controller selected the evidence-backed position",
                )
            },
        )

    result = adjudicate_conflicts(
        findings,
        proposed_verdict=ReviewVerdict.PASS,
        resolutions={
            "boundary-1": ConflictResolution(
                disposition=ConflictDisposition.RESOLVED,
                evidence_refs=("controller-decision",),
                rationale="Controller selected the evidence-backed position",
                residual_risk="Residual risk is monitored in the next bounded task",
            )
        },
    )

    assert result.final_verdict is ReviewVerdict.PASS
    assert result.decision is DecisionType.CONTINUE
    assert result.conflicts[0].disposition is ConflictDisposition.RESOLVED
    assert result.conflicts[0].resolution_evidence_refs == ("controller-decision",)
    assert result.conflicts[0].residual_risk == (
        "Residual risk is monitored in the next bounded task"
    )


def test_findings_without_explicit_conflict_group_are_not_invented_into_conflicts() -> None:
    findings = (
        _finding(
            finding_id="finding-a",
            reviewer="reviewer-a",
            claim="One boundary is unsafe",
            recommendation="Block release",
            conflict_group=None,
        ),
        _finding(
            finding_id="finding-b",
            reviewer="reviewer-b",
            claim="A different boundary is safe",
            recommendation="Allow release",
            conflict_group=None,
        ),
    )

    result = adjudicate_conflicts(findings, proposed_verdict=ReviewVerdict.PASS)

    assert result.conflicts == ()
    assert result.final_verdict is ReviewVerdict.PASS
    assert result.decision is DecisionType.CONTINUE


def test_non_material_explicit_group_is_recorded_without_escalation() -> None:
    findings = (
        _finding(
            finding_id="finding-a",
            reviewer="reviewer-a",
            claim="Naming differs",
            recommendation="Use the canonical name",
            severity="minor",
            conflict_group="style-1",
        ),
        _finding(
            finding_id="finding-b",
            reviewer="reviewer-b",
            claim="Naming differs",
            recommendation="Use the canonical name",
            severity="info",
            conflict_group="style-1",
        ),
    )

    result = adjudicate_conflicts(findings)

    assert result.conflicts[0].material is False
    assert result.conflicts[0].disposition is ConflictDisposition.NOT_MATERIAL
    assert result.final_verdict is ReviewVerdict.PASS
    assert result.decision is DecisionType.CONTINUE


def test_escalated_conflict_retains_resolution_evidence_and_residual_risk() -> None:
    result = adjudicate_conflicts(
        _conflicting_findings(),
        resolutions={
            "boundary-1": ConflictResolution(
                disposition=ConflictDisposition.ESCALATED,
                evidence_refs=("controller-escalation",),
                rationale="Human decision is required",
                residual_risk="Release decision remains blocked",
            )
        },
    )

    assert result.final_verdict is ReviewVerdict.NEEDS_CLARIFICATION
    assert result.decision is DecisionType.ESCALATE
    assert result.conflicts[0].disposition is ConflictDisposition.ESCALATED
    assert result.conflicts[0].resolution_evidence_refs == ("controller-escalation",)
    assert result.residual_risks == ("Release decision remains blocked",)


def test_unknown_resolution_group_fails_closed() -> None:
    with pytest.raises(ConflictAdjudicationError, match="unknown conflict"):
        adjudicate_conflicts(
            _conflicting_findings(),
            resolutions={
                "not-present": ConflictResolution(
                    disposition=ConflictDisposition.RESOLVED,
                    evidence_refs=("decision",),
                    rationale="Controller selected an evidence-backed position",
                )
            },
        )


def test_conflicting_duplicate_finding_id_fails_closed() -> None:
    first, _ = _conflicting_findings()
    duplicate = _finding(
        finding_id=first.finding_id,
        reviewer="reviewer-c",
        claim="A materially different claim",
        recommendation="Allow release",
    )

    with pytest.raises(ConflictAdjudicationError, match="conflicting finding"):
        adjudicate_conflicts((first, duplicate))


def test_result_is_deterministic_and_immutable() -> None:
    first, second = _conflicting_findings()
    left = adjudicate_conflicts((first, second))
    right = adjudicate_conflicts((second, first))

    assert left.to_dict() == right.to_dict()
    with pytest.raises(Exception):
        left.final_verdict = ReviewVerdict.PASS  # type: ignore[misc]
