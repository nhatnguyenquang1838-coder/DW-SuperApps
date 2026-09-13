"""Deterministic pre-Mixer conflict detection and adjudication."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from taskcontroller.domain.enums import DecisionType, ReviewVerdict
from taskcontroller.execution.errors import ExecutionFabricError
from taskcontroller.execution.result_normalizer import NormalizedFinding


CONFLICT_ADJUDICATOR_PROTOCOL = "dw.taskcontroller.conflict-adjudicator/v1"
_HIGH_SEVERITIES = frozenset({"critical", "major"})
_INCOMPATIBLE_DISPOSITIONS = frozenset({"OPEN", "ACCEPTED", "REJECTED", "DEFERRED", "ESCALATED"})


class ConflictAdjudicationError(ExecutionFabricError):
    """Raised when conflict input or adjudication evidence is invalid."""


class ConflictDisposition(str, Enum):
    """Machine disposition for one detected conflict group."""

    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    NOT_MATERIAL = "NOT_MATERIAL"


def _text(field: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConflictAdjudicationError(f"{field} must be a non-empty string")
    return value.strip()


def _refs(field: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise ConflictAdjudicationError(f"{field} must be a sequence")
    refs = tuple(_text(f"{field} item", item) for item in value)
    if len(set(refs)) != len(refs):
        raise ConflictAdjudicationError(f"{field} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_text(value: str) -> str:
    return " ".join(value.split()).casefold()


@dataclass(frozen=True, slots=True)
class ConflictResolution:
    """Explicit Controller/Human disposition and evidence for a conflict."""

    disposition: ConflictDisposition
    evidence_refs: tuple[str, ...] = ()
    rationale: str | None = None
    residual_risk: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, ConflictDisposition):
            raise ConflictAdjudicationError("resolution.disposition must be a ConflictDisposition")
        object.__setattr__(self, "evidence_refs", _refs("resolution evidence_refs", self.evidence_refs))
        if self.rationale is not None:
            object.__setattr__(self, "rationale", _text("resolution.rationale", self.rationale))
        if self.residual_risk is not None:
            object.__setattr__(self, "residual_risk", _text("resolution.residual_risk", self.residual_risk))
        if self.disposition in {ConflictDisposition.RESOLVED, ConflictDisposition.ESCALATED}:
            if not self.evidence_refs:
                raise ConflictAdjudicationError(
                    "resolution evidence_refs are required for resolved or escalated conflicts"
                )
            if self.rationale is None:
                raise ConflictAdjudicationError(
                    "resolution rationale is required for resolved or escalated conflicts"
                )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "disposition": self.disposition.value,
            "evidence_refs": list(self.evidence_refs),
        }
        if self.rationale is not None:
            result["rationale"] = self.rationale
        if self.residual_risk is not None:
            result["residual_risk"] = self.residual_risk
        return result


@dataclass(frozen=True, slots=True)
class ConflictGroup:
    """Immutable conflict evidence retained for Mixer/Controller consumption."""

    conflict_id: str
    finding_ids: tuple[str, ...]
    reviewers: tuple[str, ...]
    severities: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    material: bool
    disposition: ConflictDisposition
    resolution_evidence_refs: tuple[str, ...] = ()
    rationale: str | None = None
    residual_risk: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "conflict_id", _text("conflict_id", self.conflict_id))
        finding_ids = _refs("finding_ids", self.finding_ids)
        reviewers = _refs("reviewers", self.reviewers)
        severities = _refs("severities", self.severities)
        evidence_refs = _refs("evidence_refs", self.evidence_refs)
        if not finding_ids or len(finding_ids) < 2:
            raise ConflictAdjudicationError("finding_ids must contain at least two findings")
        if not reviewers:
            raise ConflictAdjudicationError("reviewers must not be empty")
        if not severities:
            raise ConflictAdjudicationError("severities must not be empty")
        if not evidence_refs:
            raise ConflictAdjudicationError("evidence_refs must not be empty")
        if not isinstance(self.material, bool):
            raise ConflictAdjudicationError("material must be boolean")
        if not isinstance(self.disposition, ConflictDisposition):
            raise ConflictAdjudicationError("disposition must be a ConflictDisposition")
        object.__setattr__(self, "finding_ids", finding_ids)
        object.__setattr__(self, "reviewers", reviewers)
        object.__setattr__(self, "severities", severities)
        object.__setattr__(self, "evidence_refs", evidence_refs)
        object.__setattr__(self, "resolution_evidence_refs", _refs("resolution_evidence_refs", self.resolution_evidence_refs))
        if self.rationale is not None:
            object.__setattr__(self, "rationale", _text("rationale", self.rationale))
        if self.residual_risk is not None:
            object.__setattr__(self, "residual_risk", _text("residual_risk", self.residual_risk))
        if self.material and self.disposition in {
            ConflictDisposition.RESOLVED,
            ConflictDisposition.ESCALATED,
        } and not self.resolution_evidence_refs:
            raise ConflictAdjudicationError(
                "resolution evidence_refs are required for material conflict disposition"
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "conflict_id": self.conflict_id,
            "finding_ids": list(self.finding_ids),
            "reviewers": list(self.reviewers),
            "severities": list(self.severities),
            "evidence_refs": list(self.evidence_refs),
            "material": self.material,
            "disposition": self.disposition.value,
            "resolution_evidence_refs": list(self.resolution_evidence_refs),
        }
        if self.rationale is not None:
            result["rationale"] = self.rationale
        if self.residual_risk is not None:
            result["residual_risk"] = self.residual_risk
        return result


@dataclass(frozen=True, slots=True)
class ConflictAdjudicationResult:
    """Immutable normalized conflict result for a future parent synthesis step."""

    proposed_verdict: ReviewVerdict
    final_verdict: ReviewVerdict
    decision: DecisionType
    active_finding_ids: tuple[str, ...]
    conflicts: tuple[ConflictGroup, ...]
    residual_risks: tuple[str, ...] = ()
    protocol: str = CONFLICT_ADJUDICATOR_PROTOCOL

    def __post_init__(self) -> None:
        if not isinstance(self.proposed_verdict, ReviewVerdict):
            raise ConflictAdjudicationError("proposed_verdict must be a ReviewVerdict")
        if not isinstance(self.final_verdict, ReviewVerdict):
            raise ConflictAdjudicationError("final_verdict must be a ReviewVerdict")
        if not isinstance(self.decision, DecisionType):
            raise ConflictAdjudicationError("decision must be a DecisionType")
        object.__setattr__(self, "active_finding_ids", _refs("active_finding_ids", self.active_finding_ids))
        conflicts = tuple(self.conflicts)
        if any(not isinstance(item, ConflictGroup) for item in conflicts):
            raise ConflictAdjudicationError("conflicts must contain ConflictGroup values")
        object.__setattr__(self, "conflicts", tuple(sorted(conflicts, key=lambda item: item.conflict_id)))
        object.__setattr__(self, "residual_risks", _refs("residual_risks", self.residual_risks))
        object.__setattr__(self, "protocol", _text("protocol", self.protocol))

    @property
    def material_conflict_count(self) -> int:
        return sum(1 for conflict in self.conflicts if conflict.material)

    @property
    def unresolved_material_conflict_count(self) -> int:
        return sum(
            1
            for conflict in self.conflicts
            if conflict.material
            and conflict.disposition in {
                ConflictDisposition.UNRESOLVED,
                ConflictDisposition.ESCALATED,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "proposed_verdict": self.proposed_verdict.value,
            "final_verdict": self.final_verdict.value,
            "status": self.final_verdict.value,
            "decision": self.decision.value,
            "active_finding_ids": list(self.active_finding_ids),
            "material_conflict_count": self.material_conflict_count,
            "unresolved_material_conflict_count": self.unresolved_material_conflict_count,
            "residual_risks": list(self.residual_risks),
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
        }


def _normalize_findings(findings: Iterable[NormalizedFinding]) -> tuple[NormalizedFinding, ...]:
    if isinstance(findings, (str, bytes)):
        raise ConflictAdjudicationError("findings must be an iterable of NormalizedFinding values")
    try:
        values = tuple(findings)
    except TypeError as exc:
        raise ConflictAdjudicationError("findings must be iterable") from exc
    if any(not isinstance(item, NormalizedFinding) for item in values):
        raise ConflictAdjudicationError("findings must contain NormalizedFinding values")
    by_id: dict[str, NormalizedFinding] = {}
    for finding in values:
        previous = by_id.get(finding.finding_id)
        if previous is not None and previous != finding:
            raise ConflictAdjudicationError(
                f"conflicting finding evidence for finding_id={finding.finding_id}"
            )
        by_id[finding.finding_id] = finding
    return tuple(sorted(by_id.values(), key=lambda item: item.finding_id))


def _stance(finding: NormalizedFinding) -> tuple[str, str, str, str]:
    return (
        _canonical_text(finding.claim),
        finding.severity,
        _canonical_text(finding.recommendation),
        finding.disposition,
    )


def _is_material(findings: tuple[NormalizedFinding, ...]) -> bool:
    if any(finding.severity in _HIGH_SEVERITIES for finding in findings):
        return True
    claims = {_canonical_text(finding.claim) for finding in findings}
    recommendations = {_canonical_text(finding.recommendation) for finding in findings}
    dispositions = {finding.disposition for finding in findings}
    return (
        len(claims) > 1
        or len(recommendations) > 1
        or bool(dispositions & _INCOMPATIBLE_DISPOSITIONS and len(dispositions) > 1)
    )


def _conflict_group(
    conflict_id: str,
    findings: tuple[NormalizedFinding, ...],
    resolution: ConflictResolution | None,
) -> ConflictGroup:
    material = _is_material(findings)
    if resolution is None:
        disposition = ConflictDisposition.UNRESOLVED if material else ConflictDisposition.NOT_MATERIAL
        resolution_refs: tuple[str, ...] = ()
        rationale = None
        residual_risk = (
            "Material conflict remains unresolved and requires Controller/Human adjudication"
            if material
            else None
        )
    else:
        if material and resolution.disposition is ConflictDisposition.NOT_MATERIAL:
            raise ConflictAdjudicationError(
                f"material conflict cannot use NOT_MATERIAL disposition: {conflict_id}"
            )
        disposition = resolution.disposition
        resolution_refs = resolution.evidence_refs
        rationale = resolution.rationale
        residual_risk = resolution.residual_risk
        if material and disposition in {
            ConflictDisposition.UNRESOLVED,
            ConflictDisposition.ESCALATED,
        } and residual_risk is None:
            residual_risk = "Material conflict remains unresolved and requires Controller/Human adjudication"

    return ConflictGroup(
        conflict_id=conflict_id,
        finding_ids=tuple(finding.finding_id for finding in findings),
        reviewers=tuple(finding.reviewer for finding in findings),
        severities=tuple(finding.severity for finding in findings),
        evidence_refs=tuple(
            ref for finding in findings for ref in finding.evidence_refs
        ),
        material=material,
        disposition=disposition,
        resolution_evidence_refs=resolution_refs,
        rationale=rationale,
        residual_risk=residual_risk,
    )


def adjudicate_conflicts(
    findings: Iterable[NormalizedFinding],
    *,
    proposed_verdict: ReviewVerdict = ReviewVerdict.PASS,
    resolutions: Mapping[str, ConflictResolution] | None = None,
) -> ConflictAdjudicationResult:
    """Detect explicit conflict groups and apply only explicit dispositions."""

    if not isinstance(proposed_verdict, ReviewVerdict):
        raise ConflictAdjudicationError("proposed_verdict must be a ReviewVerdict")
    normalized = _normalize_findings(findings)
    if resolutions is None:
        resolution_map: dict[str, ConflictResolution] = {}
    elif not isinstance(resolutions, Mapping):
        raise ConflictAdjudicationError("resolutions must be a mapping")
    else:
        resolution_map = dict(resolutions)
        if any(not isinstance(key, str) or not key for key in resolution_map):
            raise ConflictAdjudicationError("resolution keys must be non-empty strings")
        if any(not isinstance(value, ConflictResolution) for value in resolution_map.values()):
            raise ConflictAdjudicationError("resolutions must contain ConflictResolution values")

    grouped: dict[str, list[NormalizedFinding]] = {}
    for finding in normalized:
        if finding.conflict_group is not None:
            grouped.setdefault(finding.conflict_group, []).append(finding)

    conflicts: list[ConflictGroup] = []
    for conflict_id in sorted(grouped):
        group_findings = tuple(grouped[conflict_id])
        if len(group_findings) < 2 or len({_stance(finding) for finding in group_findings}) < 2:
            continue
        conflicts.append(
            _conflict_group(
                conflict_id,
                group_findings,
                resolution_map.get(conflict_id),
            )
        )

    unknown_resolutions = sorted(set(resolution_map) - {conflict.conflict_id for conflict in conflicts})
    if unknown_resolutions:
        raise ConflictAdjudicationError(
            f"unknown conflict resolution group(s): {', '.join(unknown_resolutions)}"
        )

    unresolved_material = any(
        conflict.material
        and conflict.disposition in {
            ConflictDisposition.UNRESOLVED,
            ConflictDisposition.ESCALATED,
        }
        for conflict in conflicts
    )
    final_verdict = ReviewVerdict.NEEDS_CLARIFICATION if unresolved_material else proposed_verdict
    decision = DecisionType.ESCALATE if unresolved_material else DecisionType.CONTINUE
    residual_risks = tuple(
        conflict.residual_risk
        for conflict in conflicts
        if conflict.residual_risk is not None
    )
    return ConflictAdjudicationResult(
        proposed_verdict=proposed_verdict,
        final_verdict=final_verdict,
        decision=decision,
        active_finding_ids=tuple(finding.finding_id for finding in normalized),
        conflicts=tuple(conflicts),
        residual_risks=residual_risks,
    )


# Short alias for callers that use the detection-first terminology.
detect_and_adjudicate = adjudicate_conflicts


__all__ = [
    "CONFLICT_ADJUDICATOR_PROTOCOL",
    "ConflictAdjudicationError",
    "ConflictAdjudicationResult",
    "ConflictDisposition",
    "ConflictGroup",
    "ConflictResolution",
    "adjudicate_conflicts",
    "detect_and_adjudicate",
]
