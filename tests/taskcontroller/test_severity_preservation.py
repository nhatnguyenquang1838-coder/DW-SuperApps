"""TC-MBX-604: preserve CRITICAL/MAJOR findings through review synthesis."""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import ReviewVerdict
from taskcontroller.execution.result_normalizer import NormalizedFinding
from taskcontroller.execution.severity_preservation import (
    ReviewerOutcome,
    SeverityPreservationError,
    preserve_severity,
)


def _finding(
    *,
    finding_id: str = "finding-critical",
    severity: str = "critical",
    reviewer: str = "reviewer-a",
    disposition: str = "OPEN",
) -> NormalizedFinding:
    return NormalizedFinding(
        finding_id=finding_id,
        severity=severity,
        category="security",
        lens="security-reliability",
        claim="Unsafe boundary remains reachable",
        evidence_refs=(f"evidence-{finding_id}",),
        recommendation="Block release until remediated",
        reviewer=reviewer,
        disposition=disposition,
    )


def _pass(*, review_id: str, reviewer: str) -> ReviewerOutcome:
    return ReviewerOutcome(
        review_id=review_id,
        reviewer=reviewer,
        verdict=ReviewVerdict.PASS,
        target_ref="node-604",
    )


def test_one_critical_finding_overrides_three_pass_reviews() -> None:
    result = preserve_severity(
        outcomes=(
            _pass(review_id="review-1", reviewer="reviewer-1"),
            _pass(review_id="review-2", reviewer="reviewer-2"),
            _pass(review_id="review-3", reviewer="reviewer-3"),
        ),
        findings=(_finding(),),
        proposed_verdict=ReviewVerdict.PASS,
    )

    assert result.final_verdict is ReviewVerdict.NEEDS_FIX
    assert result.proposed_pass_overridden is True
    assert result.high_severity_count == 1
    assert result.high_severity_ids == ("finding-critical",)
    assert result.active_findings[0].severity == "critical"
    assert result.reviewer_account == {
        "reviewer-1": 1,
        "reviewer-2": 1,
        "reviewer-3": 1,
    }
    assert result.to_dict()["findings"][0]["severity"] == "critical"


def test_major_finding_cannot_be_downgraded_by_pass_proposal() -> None:
    result = preserve_severity(
        outcomes=(_pass(review_id="review-1", reviewer="reviewer-1"),),
        findings=(_finding(finding_id="finding-major", severity="major"),),
        proposed_verdict=ReviewVerdict.PASS,
    )

    assert result.final_verdict is ReviewVerdict.NEEDS_FIX
    assert result.high_severity_ids == ("finding-major",)
    assert result.proposed_pass_overridden is True


def test_high_severity_finding_attached_to_pass_review_remains_visible() -> None:
    result = preserve_severity(
        outcomes=(
            ReviewerOutcome(
                review_id="review-1",
                reviewer="reviewer-1",
                verdict=ReviewVerdict.PASS,
                target_ref="node-604",
                findings=(_finding(reviewer="reviewer-1"),),
            ),
        ),
        proposed_verdict=ReviewVerdict.PASS,
    )

    assert result.final_verdict is ReviewVerdict.NEEDS_FIX
    assert [finding.finding_id for finding in result.active_findings] == [
        "finding-critical",
    ]


def test_non_high_severity_passes_remain_pass() -> None:
    result = preserve_severity(
        outcomes=(_pass(review_id="review-1", reviewer="reviewer-1"),),
        findings=(_finding(finding_id="finding-minor", severity="minor"),),
        proposed_verdict=ReviewVerdict.PASS,
    )

    assert result.final_verdict is ReviewVerdict.PASS
    assert result.proposed_pass_overridden is False
    assert result.high_severity_count == 0


def test_explicit_fail_verdict_is_not_weakened() -> None:
    result = preserve_severity(
        outcomes=(
            ReviewerOutcome(
                review_id="review-1",
                reviewer="reviewer-1",
                verdict=ReviewVerdict.FAIL,
                target_ref="node-604",
            ),
        ),
        findings=(_finding(),),
        proposed_verdict=ReviewVerdict.PASS,
    )

    assert result.final_verdict is ReviewVerdict.FAIL
    assert result.proposed_pass_overridden is False


def test_rejected_high_severity_finding_does_not_override_pass() -> None:
    result = preserve_severity(
        outcomes=(_pass(review_id="review-1", reviewer="reviewer-1"),),
        findings=(_finding(disposition="REJECTED"),),
        proposed_verdict=ReviewVerdict.PASS,
    )

    assert result.final_verdict is ReviewVerdict.PASS
    assert result.active_findings == ()
    assert result.high_severity_count == 0


def test_conflicting_duplicate_finding_id_fails_closed() -> None:
    with pytest.raises(SeverityPreservationError, match="conflicting finding"):
        preserve_severity(
            outcomes=(),
            findings=(
                _finding(finding_id="same-id", severity="critical"),
                _finding(finding_id="same-id", severity="major", reviewer="reviewer-b"),
            ),
            proposed_verdict=ReviewVerdict.PASS,
        )


def test_result_is_deterministic_and_immutable() -> None:
    findings = (
        _finding(finding_id="finding-z", reviewer="reviewer-z"),
        _finding(finding_id="finding-a", reviewer="reviewer-a", severity="major"),
    )
    left = preserve_severity(
        outcomes=(_pass(review_id="review-1", reviewer="reviewer-1"),),
        findings=findings,
        proposed_verdict=ReviewVerdict.PASS,
    )
    right = preserve_severity(
        outcomes=(_pass(review_id="review-1", reviewer="reviewer-1"),),
        findings=tuple(reversed(findings)),
        proposed_verdict=ReviewVerdict.PASS,
    )

    assert left.to_dict() == right.to_dict()
    with pytest.raises(Exception):
        left.final_verdict = ReviewVerdict.PASS  # type: ignore[misc]
