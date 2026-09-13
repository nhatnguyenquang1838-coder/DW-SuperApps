"""Deterministic pre-Mixer preservation of high-severity review evidence."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from taskcontroller.domain.enums import ReviewVerdict
from taskcontroller.execution.errors import ExecutionFabricError
from taskcontroller.execution.result_normalizer import NormalizedFinding


SEVERITY_PRESERVATION_PROTOCOL = "dw.taskcontroller.severity-preservation/v1"
_HIGH_SEVERITIES = frozenset({"critical", "major"})
_VERDICT_ORDER = {
    ReviewVerdict.PASS: 0,
    ReviewVerdict.NEEDS_CLARIFICATION: 1,
    ReviewVerdict.NEEDS_FIX: 2,
    ReviewVerdict.FAIL: 3,
}


class SeverityPreservationError(ExecutionFabricError):
    """Raised when severity-preservation input or evidence is invalid."""


def _require_text(field: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SeverityPreservationError(f"{field} must be a non-empty string")
    return value.strip()


def _require_refs(field: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise SeverityPreservationError(f"{field} must be a sequence")
    refs = tuple(_require_text(f"{field} item", item) for item in value)
    if len(set(refs)) != len(refs):
        raise SeverityPreservationError(f"{field} must not contain duplicates")
    return tuple(sorted(refs))


@dataclass(frozen=True, slots=True)
class ReviewerOutcome:
    """Immutable outcome and optional findings from one reviewer."""

    review_id: str
    reviewer: str
    verdict: ReviewVerdict
    target_ref: str
    evidence_refs: tuple[str, ...] = ()
    findings: tuple[NormalizedFinding, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "review_id", _require_text("review_id", self.review_id))
        object.__setattr__(self, "reviewer", _require_text("reviewer", self.reviewer))
        object.__setattr__(self, "target_ref", _require_text("target_ref", self.target_ref))
        if not isinstance(self.verdict, ReviewVerdict):
            raise SeverityPreservationError("verdict must be a ReviewVerdict")
        object.__setattr__(self, "evidence_refs", _require_refs("evidence_refs", self.evidence_refs))
        if not isinstance(self.findings, (tuple, list)):
            raise SeverityPreservationError("findings must be a sequence")
        findings = tuple(self.findings)
        if any(not isinstance(finding, NormalizedFinding) for finding in findings):
            raise SeverityPreservationError("findings must contain NormalizedFinding values")
        object.__setattr__(self, "findings", findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "reviewer": self.reviewer,
            "verdict": self.verdict.value,
            "target_ref": self.target_ref,
            "evidence_refs": list(self.evidence_refs),
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True, slots=True)
class SeverityPreservationResult:
    """Immutable normalized result after applying severity precedence."""

    final_verdict: ReviewVerdict
    proposed_verdict: ReviewVerdict
    active_findings: tuple[NormalizedFinding, ...]
    high_severity_ids: tuple[str, ...]
    high_severity_count: int
    proposed_pass_overridden: bool
    reviewer_account: Mapping[str, int]
    protocol: str = SEVERITY_PRESERVATION_PROTOCOL

    def __post_init__(self) -> None:
        if not isinstance(self.final_verdict, ReviewVerdict):
            raise SeverityPreservationError("final_verdict must be a ReviewVerdict")
        if not isinstance(self.proposed_verdict, ReviewVerdict):
            raise SeverityPreservationError("proposed_verdict must be a ReviewVerdict")
        findings = tuple(self.active_findings)
        if any(not isinstance(finding, NormalizedFinding) for finding in findings):
            raise SeverityPreservationError("active_findings must contain NormalizedFinding values")
        object.__setattr__(self, "active_findings", findings)
        high_ids = tuple(self.high_severity_ids)
        if any(not isinstance(item, str) or not item for item in high_ids):
            raise SeverityPreservationError("high_severity_ids must contain non-empty strings")
        object.__setattr__(self, "high_severity_ids", high_ids)
        if not isinstance(self.high_severity_count, int) or isinstance(self.high_severity_count, bool):
            raise SeverityPreservationError("high_severity_count must be an integer")
        if self.high_severity_count != len(high_ids):
            raise SeverityPreservationError("high_severity_count must match high_severity_ids")
        if not isinstance(self.proposed_pass_overridden, bool):
            raise SeverityPreservationError("proposed_pass_overridden must be boolean")
        if not isinstance(self.reviewer_account, Mapping):
            raise SeverityPreservationError("reviewer_account must be a mapping")
        account = {
            _require_text("reviewer", reviewer): count
            for reviewer, count in self.reviewer_account.items()
        }
        if any(not isinstance(count, int) or isinstance(count, bool) or count < 1 for count in account.values()):
            raise SeverityPreservationError("reviewer_account counts must be positive integers")
        object.__setattr__(self, "reviewer_account", MappingProxyType(dict(sorted(account.items()))))
        object.__setattr__(self, "protocol", _require_text("protocol", self.protocol))

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "proposed_verdict": self.proposed_verdict.value,
            "final_verdict": self.final_verdict.value,
            "proposed_pass_overridden": self.proposed_pass_overridden,
            "high_severity_count": self.high_severity_count,
            "high_severity_ids": list(self.high_severity_ids),
            "reviewer_account": dict(self.reviewer_account),
            "findings": [finding.to_dict() for finding in self.active_findings],
        }


def _validated_sequence(name: str, value: Iterable[Any]) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)):
        raise SeverityPreservationError(f"{name} must be an iterable of domain values")
    try:
        return tuple(value)
    except TypeError as exc:
        raise SeverityPreservationError(f"{name} must be iterable") from exc


def _active_findings(
    seed_findings: tuple[NormalizedFinding, ...],
    outcomes: tuple[ReviewerOutcome, ...],
) -> tuple[NormalizedFinding, ...]:
    by_id: dict[str, NormalizedFinding] = {}
    candidates = (*seed_findings, *(finding for outcome in outcomes for finding in outcome.findings))
    for finding in candidates:
        if finding.disposition == "REJECTED":
            continue
        previous = by_id.get(finding.finding_id)
        if previous is not None and previous != finding:
            raise SeverityPreservationError(
                f"conflicting finding evidence for finding_id={finding.finding_id}"
            )
        by_id[finding.finding_id] = finding
    return tuple(
        sorted(
            by_id.values(),
            key=lambda finding: (
                finding.finding_id,
                finding.severity,
                finding.reviewer,
                finding.evidence_refs,
            ),
        )
    )


def _proposed_verdict(
    outcomes: tuple[ReviewerOutcome, ...],
    proposed_verdict: ReviewVerdict | None,
) -> ReviewVerdict:
    if proposed_verdict is not None:
        if not isinstance(proposed_verdict, ReviewVerdict):
            raise SeverityPreservationError("proposed_verdict must be a ReviewVerdict")
        return proposed_verdict
    if not outcomes:
        return ReviewVerdict.PASS
    return max((outcome.verdict for outcome in outcomes), key=_VERDICT_ORDER.__getitem__)


def preserve_severity(
    *,
    outcomes: Iterable[ReviewerOutcome],
    findings: Iterable[NormalizedFinding] = (),
    proposed_verdict: ReviewVerdict | None = None,
) -> SeverityPreservationResult:
    """Apply fail-closed severity precedence without dropping evidence."""

    normalized_outcomes = _validated_sequence("outcomes", outcomes)
    if any(not isinstance(outcome, ReviewerOutcome) for outcome in normalized_outcomes):
        raise SeverityPreservationError("outcomes must contain ReviewerOutcome values")
    normalized_findings = _validated_sequence("findings", findings)
    if any(not isinstance(finding, NormalizedFinding) for finding in normalized_findings):
        raise SeverityPreservationError("findings must contain NormalizedFinding values")

    active_findings = _active_findings(normalized_findings, normalized_outcomes)
    high_findings = tuple(
        finding for finding in active_findings if finding.severity in _HIGH_SEVERITIES
    )
    proposed = _proposed_verdict(normalized_outcomes, proposed_verdict)
    outcome_verdict = _proposed_verdict(normalized_outcomes, None)
    final_verdict = max((proposed, outcome_verdict), key=_VERDICT_ORDER.__getitem__)
    overridden = False
    if high_findings and final_verdict is ReviewVerdict.PASS:
        final_verdict = ReviewVerdict.NEEDS_FIX
        overridden = True

    account: dict[str, int] = {}
    for outcome in normalized_outcomes:
        account[outcome.reviewer] = account.get(outcome.reviewer, 0) + 1

    return SeverityPreservationResult(
        final_verdict=final_verdict,
        proposed_verdict=proposed,
        active_findings=active_findings,
        high_severity_ids=tuple(finding.finding_id for finding in high_findings),
        high_severity_count=len(high_findings),
        proposed_pass_overridden=overridden,
        reviewer_account=account,
    )


# Explicit alias for callers that use the reducer terminology.
reduce_severity = preserve_severity


__all__ = [
    "ReviewerOutcome",
    "SEVERITY_PRESERVATION_PROTOCOL",
    "SeverityPreservationError",
    "SeverityPreservationResult",
    "preserve_severity",
    "reduce_severity",
]
