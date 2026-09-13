"""TC-MBX-606: deterministic evidence-only parent synthesis.

The parent result is a bounded projection of normalized child evidence.  It is
provider-neutral, contains no transcript/raw chat content, and does not write
mailbox, Slack, GitHub, or runtime state.  Controller decisions remain explicit
and are validated against the synthesized semantic result.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from taskcontroller.domain.enums import DecisionType, ReviewVerdict
from taskcontroller.execution.conflict_adjudicator import (
    ConflictAdjudicationResult,
    ConflictDisposition,
    ConflictGroup as AdjudicatedConflictGroup,
)
from taskcontroller.execution.errors import ExecutionFabricError
from taskcontroller.execution.finding_deduplicator import (
    DeduplicatedFinding,
    deduplicate_findings,
)
from taskcontroller.execution.result_normalizer import (
    NormalizationStatus,
    NormalizedChildResult,
    NormalizedFinding,
)


PARENT_SYNTHESIS_PROTOCOL = "dw.taskcontroller.parent-synthesis/v1"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_HIGH_SEVERITIES = frozenset({"critical", "major"})
_VERDICT_ORDER = {
    ReviewVerdict.PASS: 0,
    ReviewVerdict.NEEDS_CLARIFICATION: 1,
    ReviewVerdict.NEEDS_FIX: 2,
    ReviewVerdict.FAIL: 3,
}
_ESCALATING_DECISIONS = frozenset(
    {DecisionType.WAIT, DecisionType.REPLAN, DecisionType.ESCALATE}
)


class ParentSynthesisError(ExecutionFabricError):
    """Raised when parent synthesis cannot produce a trustworthy result."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _text(field: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ParentSynthesisError("PARENT_SYNTHESIS_INVALID", f"{field} must be non-empty")
    normalized = value.strip()
    if "\x00" in normalized:
        raise ParentSynthesisError("PARENT_SYNTHESIS_INVALID", f"{field} must not contain NUL")
    return normalized


def _identifier(field: str, value: Any) -> str:
    normalized = _text(field, value)
    if not _ID_RE.fullmatch(normalized):
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_INVALID",
            f"{field} must be a stable identifier",
        )
    return normalized


def _digest(field: str, value: Any) -> str:
    normalized = _text(field, value)
    if not _DIGEST_RE.fullmatch(normalized):
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_INVALID",
            f"{field} must be sha256:<64 lowercase hex>",
        )
    return normalized


def _optional_digest(field: str, value: Any) -> str | None:
    if value is None:
        return None
    return _digest(field, value)


def _unique_sorted_texts(field: str, values: Iterable[Any], *, allow_empty: bool) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ParentSynthesisError("PARENT_SYNTHESIS_INVALID", f"{field} must be a sequence")
    try:
        items = tuple(values)
    except TypeError as exc:
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_INVALID", f"{field} must be a sequence"
        ) from exc
    if not items and not allow_empty:
        raise ParentSynthesisError("PARENT_SYNTHESIS_INVALID", f"{field} must not be empty")
    normalized = tuple(sorted({_text(f"{field} item", item) for item in items}))
    if not allow_empty and not normalized:
        raise ParentSynthesisError("PARENT_SYNTHESIS_INVALID", f"{field} must not be empty")
    return normalized


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_NOT_SERIALIZABLE",
            f"canonical result is not JSON serializable: {type(exc).__name__}",
        ) from exc


def _sha256_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _as_verdict(field: str, value: Any) -> ReviewVerdict:
    if isinstance(value, ReviewVerdict):
        return value
    try:
        return ReviewVerdict(value)
    except (TypeError, ValueError) as exc:
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_INVALID",
            f"{field} must be a ReviewVerdict",
        ) from exc


def _as_decision_type(value: Any) -> DecisionType:
    if isinstance(value, DecisionType):
        return value
    try:
        return DecisionType(value)
    except (TypeError, ValueError) as exc:
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_INVALID",
            "decision_type must be a DecisionType",
        ) from exc


@dataclass(frozen=True, slots=True)
class ControllerDecision:
    """Explicit semantic decision retained in the parent result."""

    decision_id: str
    run_ref: str
    decision_type: DecisionType
    rationale: str
    evidence_refs: tuple[str, ...]
    selected_option: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _identifier("decision_id", self.decision_id))
        object.__setattr__(self, "run_ref", _text("run_ref", self.run_ref))
        object.__setattr__(self, "decision_type", _as_decision_type(self.decision_type))
        object.__setattr__(self, "rationale", _text("rationale", self.rationale))
        object.__setattr__(
            self,
            "evidence_refs",
            _unique_sorted_texts("evidence_refs", self.evidence_refs, allow_empty=False),
        )
        if self.selected_option is not None:
            object.__setattr__(
                self,
                "selected_option",
                _text("selected_option", self.selected_option),
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ControllerDecision":
        if not isinstance(value, Mapping):
            raise ParentSynthesisError(
                "PARENT_SYNTHESIS_INVALID",
                "controller_decision must be a ControllerDecision or mapping",
            )
        required = {"decision_id", "run_ref", "decision_type", "rationale", "evidence_refs"}
        missing = sorted(required - set(value))
        if missing:
            raise ParentSynthesisError(
                "PARENT_SYNTHESIS_INVALID",
                f"controller_decision missing fields: {', '.join(missing)}",
            )
        return cls(
            decision_id=value["decision_id"],
            run_ref=value["run_ref"],
            decision_type=value["decision_type"],
            rationale=value["rationale"],
            evidence_refs=tuple(value["evidence_refs"]),
            selected_option=value.get("selected_option"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "decision_id": self.decision_id,
            "run_ref": self.run_ref,
            "decision_type": self.decision_type.value,
            "rationale": self.rationale,
            "evidence_refs": list(self.evidence_refs),
        }
        if self.selected_option is not None:
            result["selected_option"] = self.selected_option
        return result


@dataclass(frozen=True, slots=True)
class ChildEvidenceRef:
    """Digest-only reference to one accepted normalized child result."""

    child_id: str
    status: NormalizationStatus
    result_digest: str
    raw_output_digest: str | None = None
    child_contract_digest: str | None = None
    source_digest: str | None = None
    lens: str | None = None
    reviewer: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "child_id", _identifier("child_id", self.child_id))
        if not isinstance(self.status, NormalizationStatus):
            try:
                object.__setattr__(self, "status", NormalizationStatus(self.status))
            except (TypeError, ValueError) as exc:
                raise ParentSynthesisError(
                    "PARENT_SYNTHESIS_INVALID", "child status must be a NormalizationStatus"
                ) from exc
        if self.status is not NormalizationStatus.SUCCEEDED:
            raise ParentSynthesisError(
                "INCOMPLETE_CHILD_RESULT",
                f"child {self.child_id} is not SUCCEEDED",
            )
        object.__setattr__(self, "result_digest", _digest("result_digest", self.result_digest))
        object.__setattr__(
            self,
            "raw_output_digest",
            _optional_digest("raw_output_digest", self.raw_output_digest),
        )
        object.__setattr__(
            self,
            "child_contract_digest",
            _optional_digest("child_contract_digest", self.child_contract_digest),
        )
        object.__setattr__(self, "source_digest", _optional_digest("source_digest", self.source_digest))
        if self.lens is not None:
            object.__setattr__(self, "lens", _text("lens", self.lens))
        if self.reviewer is not None:
            object.__setattr__(self, "reviewer", _identifier("reviewer", self.reviewer))

    @classmethod
    def from_result(cls, result: NormalizedChildResult) -> "ChildEvidenceRef":
        if not isinstance(result, NormalizedChildResult):
            raise ParentSynthesisError(
                "PARENT_SYNTHESIS_INVALID",
                "child results must contain NormalizedChildResult values",
            )
        return cls(
            child_id=result.child_id,
            status=result.status,
            result_digest=result.normalization_digest,
            raw_output_digest=result.raw_output_digest,
            child_contract_digest=result.child_contract_digest,
            source_digest=result.source_digest,
            lens=result.lens,
            reviewer=result.reviewer,
        )

    @property
    def normalization_digest(self) -> str:
        """Compatibility name for the canonical normalized child digest."""

        return self.result_digest

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "status": self.status.value,
            "result_digest": self.result_digest,
            "normalization_digest": self.result_digest,
            "raw_output_digest": self.raw_output_digest,
            "child_contract_digest": self.child_contract_digest,
            "source_digest": self.source_digest,
            "lens": self.lens,
            "reviewer": self.reviewer,
        }


@dataclass(frozen=True, slots=True)
class ParentConflictGroup:
    """Conflict evidence with repeated reviewer severities preserved safely.

    The earlier pre-Mixer conflict object rejects repeated values in its
    ``severities`` tuple.  Parent synthesis must still represent a valid
    same-severity disagreement, so this local projection keeps the finding
    identities/evidence authoritative and stores distinct summary values.
    """

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
        object.__setattr__(self, "conflict_id", _identifier("conflict_id", self.conflict_id))
        finding_ids = _unique_sorted_texts("finding_ids", self.finding_ids, allow_empty=False)
        if len(finding_ids) < 2:
            raise ParentSynthesisError(
                "PARENT_SYNTHESIS_INVALID",
                "finding_ids must contain at least two findings",
            )
        object.__setattr__(self, "finding_ids", finding_ids)
        object.__setattr__(
            self,
            "reviewers",
            _unique_sorted_texts("reviewers", self.reviewers, allow_empty=False),
        )
        object.__setattr__(
            self,
            "severities",
            _unique_sorted_texts("severities", self.severities, allow_empty=False),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _unique_sorted_texts("evidence_refs", self.evidence_refs, allow_empty=False),
        )
        if not isinstance(self.material, bool):
            raise ParentSynthesisError("PARENT_SYNTHESIS_INVALID", "material must be boolean")
        if not isinstance(self.disposition, ConflictDisposition):
            try:
                object.__setattr__(self, "disposition", ConflictDisposition(self.disposition))
            except (TypeError, ValueError) as exc:
                raise ParentSynthesisError(
                    "PARENT_SYNTHESIS_INVALID", "disposition must be a ConflictDisposition"
                ) from exc
        object.__setattr__(
            self,
            "resolution_evidence_refs",
            _unique_sorted_texts(
                "resolution_evidence_refs",
                self.resolution_evidence_refs,
                allow_empty=True,
            ),
        )
        if self.rationale is not None:
            object.__setattr__(self, "rationale", _text("rationale", self.rationale))
        if self.residual_risk is not None:
            object.__setattr__(self, "residual_risk", _text("residual_risk", self.residual_risk))
        if self.material and self.disposition in {
            ConflictDisposition.RESOLVED,
            ConflictDisposition.ESCALATED,
        } and not self.resolution_evidence_refs:
            raise ParentSynthesisError(
                "PARENT_SYNTHESIS_INVALID",
                "resolution evidence_refs are required for material conflict",
            )

    @classmethod
    def from_adjudicated(cls, conflict: AdjudicatedConflictGroup) -> "ParentConflictGroup":
        return cls(
            conflict_id=conflict.conflict_id,
            finding_ids=conflict.finding_ids,
            reviewers=conflict.reviewers,
            severities=conflict.severities,
            evidence_refs=conflict.evidence_refs,
            material=conflict.material,
            disposition=conflict.disposition,
            resolution_evidence_refs=conflict.resolution_evidence_refs,
            rationale=conflict.rationale,
            residual_risk=conflict.residual_risk,
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
class _ConflictEvaluation:
    conflicts: tuple[ParentConflictGroup, ...]
    final_verdict: ReviewVerdict
    residual_risks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParentSynthesisResult:
    """Immutable normalized parent evidence and Controller decision."""

    proposed_verdict: ReviewVerdict
    final_verdict: ReviewVerdict
    findings: tuple[DeduplicatedFinding, ...]
    child_refs: tuple[ChildEvidenceRef, ...]
    residual_risks: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    controller_decision: ControllerDecision
    conflicts: tuple[ParentConflictGroup, ...] = ()
    protocol: str = PARENT_SYNTHESIS_PROTOCOL

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed_verdict", _as_verdict("proposed_verdict", self.proposed_verdict))
        object.__setattr__(self, "final_verdict", _as_verdict("final_verdict", self.final_verdict))
        if not isinstance(self.controller_decision, ControllerDecision):
            raise ParentSynthesisError(
                "PARENT_SYNTHESIS_INVALID",
                "controller_decision must be a ControllerDecision",
            )
        findings = tuple(self.findings)
        if any(not isinstance(item, DeduplicatedFinding) for item in findings):
            raise ParentSynthesisError(
                "PARENT_SYNTHESIS_INVALID",
                "findings must contain DeduplicatedFinding values",
            )
        object.__setattr__(
            self,
            "findings",
            tuple(sorted(findings, key=lambda item: item.representative.finding_id)),
        )
        child_refs = tuple(self.child_refs)
        if any(not isinstance(item, ChildEvidenceRef) for item in child_refs):
            raise ParentSynthesisError(
                "PARENT_SYNTHESIS_INVALID",
                "child_refs must contain ChildEvidenceRef values",
            )
        child_ids = [item.child_id for item in child_refs]
        if len(set(child_ids)) != len(child_ids):
            raise ParentSynthesisError("DUPLICATE_CHILD_ID", "child_refs contain duplicate child_id")
        object.__setattr__(self, "child_refs", tuple(sorted(child_refs, key=lambda item: item.child_id)))
        conflicts = tuple(self.conflicts)
        if any(not isinstance(item, ParentConflictGroup) for item in conflicts):
            raise ParentSynthesisError(
                "PARENT_SYNTHESIS_INVALID",
                "conflicts must contain ParentConflictGroup values",
            )
        object.__setattr__(self, "conflicts", tuple(sorted(conflicts, key=lambda item: item.conflict_id)))
        object.__setattr__(
            self,
            "residual_risks",
            _unique_sorted_texts("residual_risks", self.residual_risks, allow_empty=True),
        )
        object.__setattr__(
            self,
            "unresolved_questions",
            _unique_sorted_texts("unresolved_questions", self.unresolved_questions, allow_empty=True),
        )
        object.__setattr__(self, "protocol", _text("protocol", self.protocol))

    @property
    def verdict(self) -> ReviewVerdict:
        return self.final_verdict

    @property
    def status(self) -> str:
        return self.final_verdict.value

    @property
    def decision(self) -> ControllerDecision:
        """Short alias used by Controller adapters."""

        return self.controller_decision

    @property
    def active_findings(self) -> tuple[NormalizedFinding, ...]:
        return tuple(item.representative for item in self.findings)

    @property
    def child_result_digests(self) -> tuple[str, ...]:
        return tuple(item.result_digest for item in self.child_refs)

    @property
    def material_conflict_count(self) -> int:
        return sum(1 for conflict in self.conflicts if conflict.material)

    @property
    def unresolved_material_conflict_count(self) -> int:
        return sum(
            1
            for conflict in self.conflicts
            if conflict.material
            and conflict.disposition
            in {ConflictDisposition.UNRESOLVED, ConflictDisposition.ESCALATED}
        )

    def _canonical_payload(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "proposed_verdict": self.proposed_verdict.value,
            "final_verdict": self.final_verdict.value,
            "verdict": self.final_verdict.value,
            "status": self.final_verdict.value,
            "findings": [item.to_dict() for item in self.findings],
            "child_refs": [item.to_dict() for item in self.child_refs],
            "child_result_digests": list(self.child_result_digests),
            "residual_risks": list(self.residual_risks),
            "unresolved_questions": list(self.unresolved_questions),
            "conflicts": [item.to_dict() for item in self.conflicts],
            "controller_decision": self.controller_decision.to_dict(),
        }

    @property
    def result_digest(self) -> str:
        return _sha256_digest(self._canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        result = self._canonical_payload()
        result["result_digest"] = self.result_digest
        return result


def _child_sequence(value: Iterable[NormalizedChildResult]) -> tuple[NormalizedChildResult, ...]:
    if isinstance(value, (str, bytes)):
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_INVALID",
            "child_results must be an iterable of NormalizedChildResult values",
        )
    try:
        children = tuple(value)
    except TypeError as exc:
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_INVALID", "child_results must be iterable"
        ) from exc
    if not children:
        raise ParentSynthesisError("NO_CHILD_RESULTS", "child_results must not be empty")
    if any(not isinstance(item, NormalizedChildResult) for item in children):
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_INVALID",
            "child results must contain NormalizedChildResult values",
        )
    return children


def _accepted_children(
    children: tuple[NormalizedChildResult, ...],
) -> tuple[ChildEvidenceRef, ...]:
    refs: list[ChildEvidenceRef] = []
    seen: set[str] = set()
    for child in children:
        if child.child_id in seen:
            raise ParentSynthesisError(
                "DUPLICATE_CHILD_ID",
                f"duplicate child_id: {child.child_id}",
            )
        seen.add(child.child_id)
        if child.status is not NormalizationStatus.SUCCEEDED:
            raise ParentSynthesisError(
                "INCOMPLETE_CHILD_RESULT",
                f"incomplete child result: {child.child_id} has status {child.status.value}",
            )
        refs.append(ChildEvidenceRef.from_result(child))
    return tuple(refs)


def _collect_findings(children: tuple[NormalizedChildResult, ...]) -> tuple[NormalizedFinding, ...]:
    findings = tuple(item for child in children for item in child.findings)
    by_id: dict[str, NormalizedFinding] = {}
    for finding in findings:
        previous = by_id.get(finding.finding_id)
        if previous is not None and previous != finding:
            raise ParentSynthesisError(
                "CONFLICTING_FINDING_ID",
                f"conflicting finding evidence for finding_id={finding.finding_id}",
            )
        by_id[finding.finding_id] = finding
    return tuple(sorted(by_id.values(), key=lambda item: item.finding_id))


def _controller_decision(
    value: ControllerDecision | Mapping[str, Any] | None,
    alias: ControllerDecision | Mapping[str, Any] | None,
) -> ControllerDecision:
    selected = value if value is not None else alias
    if selected is None:
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_INVALID",
            "controller_decision is required",
        )
    if isinstance(selected, ControllerDecision):
        return selected
    if isinstance(selected, Mapping):
        try:
            return ControllerDecision.from_dict(selected)
        except (KeyError, TypeError) as exc:
            raise ParentSynthesisError(
                "PARENT_SYNTHESIS_INVALID",
                "controller_decision mapping is malformed",
            ) from exc
    raise ParentSynthesisError(
        "PARENT_SYNTHESIS_INVALID",
        "controller_decision must be a ControllerDecision or mapping",
    )


def _semantic_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _finding_stance(finding: NormalizedFinding) -> tuple[str, str, str, str]:
    return (
        _semantic_text(finding.claim),
        finding.severity,
        _semantic_text(finding.recommendation),
        finding.disposition,
    )


def _is_material_conflict(findings: tuple[NormalizedFinding, ...]) -> bool:
    if any(finding.severity in _HIGH_SEVERITIES for finding in findings):
        return True
    claims = {_semantic_text(finding.claim) for finding in findings}
    recommendations = {_semantic_text(finding.recommendation) for finding in findings}
    dispositions = {finding.disposition for finding in findings}
    return (
        len(claims) > 1
        or len(recommendations) > 1
        or (len(dispositions) > 1 and bool(dispositions))
    )


def _detect_conflicts(
    findings: tuple[NormalizedFinding, ...],
    proposed: ReviewVerdict,
) -> _ConflictEvaluation:
    """Detect explicit conflicts without inheriting a lossy summary validator."""

    grouped: dict[str, list[NormalizedFinding]] = {}
    for finding in findings:
        if finding.conflict_group is not None:
            grouped.setdefault(finding.conflict_group, []).append(finding)

    conflicts: list[ParentConflictGroup] = []
    for conflict_id in sorted(grouped):
        group = tuple(sorted(grouped[conflict_id], key=lambda item: item.finding_id))
        if len(group) < 2 or len({_finding_stance(item) for item in group}) < 2:
            continue
        material = _is_material_conflict(group)
        residual_risk = (
            "Material conflict remains unresolved and requires Controller/Human adjudication"
            if material
            else None
        )
        conflicts.append(
            ParentConflictGroup(
                conflict_id=conflict_id,
                finding_ids=tuple(item.finding_id for item in group),
                reviewers=tuple(item.reviewer for item in group),
                severities=tuple(item.severity for item in group),
                evidence_refs=tuple(
                    ref for item in group for ref in item.evidence_refs
                ),
                material=material,
                disposition=(
                    ConflictDisposition.UNRESOLVED
                    if material
                    else ConflictDisposition.NOT_MATERIAL
                ),
                residual_risk=residual_risk,
            )
        )

    normalized_conflicts = tuple(sorted(conflicts, key=lambda item: item.conflict_id))
    unresolved = any(
        conflict.material
        and conflict.disposition in {ConflictDisposition.UNRESOLVED, ConflictDisposition.ESCALATED}
        for conflict in normalized_conflicts
    )
    return _ConflictEvaluation(
        conflicts=normalized_conflicts,
        final_verdict=ReviewVerdict.NEEDS_CLARIFICATION if unresolved else proposed,
        residual_risks=tuple(
            conflict.residual_risk
            for conflict in normalized_conflicts
            if conflict.residual_risk is not None
        ),
    )


def _external_conflict_evaluation(
    conflict_result: ConflictAdjudicationResult,
) -> _ConflictEvaluation:
    return _ConflictEvaluation(
        conflicts=tuple(
            ParentConflictGroup.from_adjudicated(item)
            for item in conflict_result.conflicts
        ),
        final_verdict=conflict_result.final_verdict,
        residual_risks=tuple(conflict_result.residual_risks),
    )


def _effective_verdict(
    proposed: ReviewVerdict,
    conflict_result: _ConflictEvaluation,
    findings: tuple[DeduplicatedFinding, ...],
) -> ReviewVerdict:
    unresolved = any(
        conflict.material
        and conflict.disposition in {ConflictDisposition.UNRESOLVED, ConflictDisposition.ESCALATED}
        for conflict in conflict_result.conflicts
    )
    if unresolved:
        return ReviewVerdict.NEEDS_CLARIFICATION
    candidate = max(
        (proposed, conflict_result.final_verdict),
        key=_VERDICT_ORDER.__getitem__,
    )
    has_high = any(item.representative.severity in _HIGH_SEVERITIES for item in findings)
    if has_high and candidate is ReviewVerdict.PASS:
        return ReviewVerdict.NEEDS_FIX
    return candidate


def _derived_risks(
    explicit: Iterable[Any],
    conflict_result: _ConflictEvaluation,
    final_verdict: ReviewVerdict,
    findings: tuple[DeduplicatedFinding, ...],
) -> tuple[str, ...]:
    risks = list(_unique_sorted_texts("residual_risks", explicit, allow_empty=True))
    risks.extend(conflict_result.residual_risks)
    if final_verdict is ReviewVerdict.NEEDS_FIX and any(
        item.representative.severity in _HIGH_SEVERITIES for item in findings
    ):
        risks.append("Critical or major findings remain active and require Controller action")
    return _unique_sorted_texts("residual_risks", risks, allow_empty=True)


def _derived_questions(
    explicit: Iterable[Any],
    conflict_result: _ConflictEvaluation,
) -> tuple[str, ...]:
    questions = list(_unique_sorted_texts("unresolved_questions", explicit, allow_empty=True))
    questions.extend(
        f"Controller/Human adjudication required for conflict group {conflict.conflict_id}"
        for conflict in conflict_result.conflicts
        if conflict.material
        and conflict.disposition in {ConflictDisposition.UNRESOLVED, ConflictDisposition.ESCALATED}
    )
    return _unique_sorted_texts("unresolved_questions", questions, allow_empty=True)


def _validate_controller_compatibility(
    decision: ControllerDecision,
    final_verdict: ReviewVerdict,
) -> None:
    if final_verdict is ReviewVerdict.NEEDS_CLARIFICATION and decision.decision_type not in _ESCALATING_DECISIONS:
        raise ParentSynthesisError(
            "CONTROLLER_DECISION_MISMATCH",
            "Controller decision must WAIT, REPLAN, or ESCALATE for NEEDS_CLARIFICATION",
        )
    if final_verdict in {ReviewVerdict.NEEDS_FIX, ReviewVerdict.FAIL} and decision.decision_type is DecisionType.COMPLETE:
        raise ParentSynthesisError(
            "CONTROLLER_DECISION_MISMATCH",
            "Controller decision cannot COMPLETE while findings require action",
        )


def synthesize_parent_result(
    child_results: Iterable[NormalizedChildResult],
    *,
    proposed_verdict: ReviewVerdict = ReviewVerdict.PASS,
    residual_risks: Iterable[str] = (),
    unresolved_questions: Iterable[str] = (),
    controller_decision: ControllerDecision | Mapping[str, Any] | None = None,
    decision: ControllerDecision | Mapping[str, Any] | None = None,
    conflict_result: ConflictAdjudicationResult | None = None,
) -> ParentSynthesisResult:
    """Synthesize bounded child evidence into one deterministic parent result.

    This function only consumes normalized evidence.  It never invokes a
    provider, reads a transcript, mutates external state, or changes runtime
    activation.  Every accepted child remains addressable by its digest.
    """

    proposed = _as_verdict("proposed_verdict", proposed_verdict)
    children = _child_sequence(child_results)
    child_refs = _accepted_children(children)
    raw_findings = _collect_findings(children)
    deduplicated = deduplicate_findings(raw_findings)

    if conflict_result is None:
        adjudicated = _detect_conflicts(raw_findings, proposed)
    elif isinstance(conflict_result, ConflictAdjudicationResult):
        expected_ids = tuple(item.finding_id for item in raw_findings)
        if tuple(conflict_result.active_finding_ids) != expected_ids:
            raise ParentSynthesisError(
                "CONFLICT_RESULT_MISMATCH",
                "conflict result active finding IDs do not match child evidence",
            )
        adjudicated = _external_conflict_evaluation(conflict_result)
    else:
        raise ParentSynthesisError(
            "PARENT_SYNTHESIS_INVALID",
            "conflict_result must be a ConflictAdjudicationResult",
        )

    final_verdict = _effective_verdict(proposed, adjudicated, deduplicated.findings)
    controller = _controller_decision(controller_decision, decision)
    _validate_controller_compatibility(controller, final_verdict)

    return ParentSynthesisResult(
        proposed_verdict=proposed,
        final_verdict=final_verdict,
        findings=deduplicated.findings,
        child_refs=child_refs,
        residual_risks=_derived_risks(
            residual_risks,
            adjudicated,
            final_verdict,
            deduplicated.findings,
        ),
        unresolved_questions=_derived_questions(unresolved_questions, adjudicated),
        controller_decision=controller,
        conflicts=adjudicated.conflicts,
    )


# Concise aliases for adapters that use the parent-result terminology.
synthesize_parent = synthesize_parent_result
build_parent_result = synthesize_parent_result


__all__ = [
    "PARENT_SYNTHESIS_PROTOCOL",
    "ChildEvidenceRef",
    "ControllerDecision",
    "ParentSynthesisError",
    "ParentSynthesisResult",
    "build_parent_result",
    "synthesize_parent",
    "synthesize_parent_result",
]
