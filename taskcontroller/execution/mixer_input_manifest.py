"""TC-MBX-603: immutable Mixer input manifest and evidence policy.

This module is a provider-neutral pre-Mixer seam.  It binds the exact initial
receipt set, normalized reviewer findings, quorum accounting, conflict records,
and bounded raw-evidence references before any future Mixer invocation.  It
never invokes providers, writes mailbox/Slack/GitHub state, or enables runtime
fan-out/cross-review.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from taskcontroller.domain.enums import ReviewVerdict
from taskcontroller.controlplane.generation_fence import (
    GenerationFenceDecision,
    GenerationFenceError,
    evaluate_generation_fence,
)
from taskcontroller.execution.conflict_adjudicator import ConflictDisposition
from taskcontroller.execution.errors import ExecutionFabricError
from taskcontroller.execution.initial_finding_receipt import (
    InitialFindingReceipt,
    InitialFindingReceiptLedger,
    digest_findings,
)
from taskcontroller.execution.result_normalizer import NormalizedFinding
from taskcontroller.execution.severity_preservation import ReviewerOutcome


MIXER_INPUT_MANIFEST_PROTOCOL = "dw.taskcontroller.mixer-input-manifest/v1"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_HIGH_SEVERITIES = frozenset({"critical", "major"})
_MAX_TEXT_BYTES = 2048


class MixerInputManifestError(ExecutionFabricError):
    """Stable fail-closed error for Mixer input validation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class QuorumPolicy(str, Enum):
    """The only supported MVP quorum: every declared reviewer is required."""

    ALL_REQUIRED = "ALL_REQUIRED"


class ConflictPolicy(str, Enum):
    """Conflict handling policy for the immutable Mixer input boundary."""

    PRESERVE_ALL = "PRESERVE_ALL"


class EvidenceKind(str, Enum):
    """Bounded provenance kind; payload content is never stored here."""

    REVIEW_EVIDENCE = "REVIEW_EVIDENCE"
    FINDING_EVIDENCE = "FINDING_EVIDENCE"
    RAW_OUTPUT = "RAW_OUTPUT"


def _fail(code: str, message: str) -> None:
    raise MixerInputManifestError(code, message)


def _text(field: str, value: Any, *, max_bytes: int = _MAX_TEXT_BYTES) -> str:
    if not isinstance(value, str):
        _fail("MIXER_INPUT_INVALID", f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        _fail("MIXER_INPUT_INVALID", f"{field} must be non-empty")
    if "\x00" in normalized:
        _fail("MIXER_INPUT_INVALID", f"{field} must not contain NUL")
    if len(normalized.encode("utf-8")) > max_bytes:
        _fail("MIXER_INPUT_INVALID", f"{field} exceeds its byte limit")
    return normalized


def _identifier(field: str, value: Any) -> str:
    normalized = _text(field, value, max_bytes=128)
    if not _IDENTIFIER_RE.fullmatch(normalized):
        _fail("MIXER_INPUT_INVALID", f"{field} must be a stable identifier")
    return normalized


def _digest(field: str, value: Any) -> str:
    normalized = _text(field, value, max_bytes=80)
    if not _DIGEST_RE.fullmatch(normalized):
        _fail("MIXER_INPUT_INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return normalized


def _optional_digest(field: str, value: Any) -> str | None:
    if value is None:
        return None
    return _digest(field, value)


def _sequence(field: str, value: Any, *, allow_empty: bool = True) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray)):
        _fail("MIXER_INPUT_INVALID", f"{field} must be a sequence")
    try:
        result = tuple(value)
    except TypeError as exc:
        raise MixerInputManifestError("MIXER_INPUT_INVALID", f"{field} must be a sequence") from exc
    if not allow_empty and not result:
        _fail("MIXER_INPUT_INVALID", f"{field} must not be empty")
    return result


def _sorted_unique_texts(field: str, value: Any, *, allow_empty: bool = True) -> tuple[str, ...]:
    items = _sequence(field, value, allow_empty=allow_empty)
    normalized = tuple(sorted({_text(f"{field} item", item) for item in items}))
    if not allow_empty and not normalized:
        _fail("MIXER_INPUT_INVALID", f"{field} must not be empty")
    if len(normalized) != len(items):
        _fail("MIXER_INPUT_DUPLICATE", f"{field} must not contain duplicates")
    return normalized


def _sorted_unique_identifiers(field: str, value: Any) -> tuple[str, ...]:
    items = _sequence(field, value, allow_empty=False)
    normalized = tuple(sorted({_identifier(f"{field} item", item) for item in items}))
    if len(normalized) != len(items):
        _fail("MIXER_INPUT_DUPLICATE", f"{field} must not contain duplicates")
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
        raise MixerInputManifestError(
            "MIXER_INPUT_NOT_SERIALIZABLE",
            f"canonical Mixer input is not JSON serializable: {type(exc).__name__}",
        ) from exc


def _digest_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _enum_value(field: str, value: Any, enum_type: type[Enum]) -> Enum:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        _fail("MIXER_INPUT_INVALID", f"{field} is not a supported value")
        raise AssertionError("_fail must raise") from exc


@dataclass(frozen=True, slots=True)
class RetainedEvidenceRef:
    """Reference/digest-only evidence retained for Mixer provenance."""

    reference: str
    reviewer_id: str
    kind: EvidenceKind | str
    finding_id: str | None = None
    digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference", _text("evidence.reference", self.reference))
        object.__setattr__(self, "reviewer_id", _identifier("evidence.reviewer_id", self.reviewer_id))
        kind = _enum_value("evidence.kind", self.kind, EvidenceKind)
        object.__setattr__(self, "kind", kind)
        if self.finding_id is not None:
            object.__setattr__(self, "finding_id", _identifier("evidence.finding_id", self.finding_id))
        if self.digest is not None:
            object.__setattr__(self, "digest", _digest("evidence.digest", self.digest))
        if kind is EvidenceKind.FINDING_EVIDENCE and self.finding_id is None:
            _fail("MIXER_EVIDENCE_INCOMPLETE", "finding evidence requires finding_id")
        if kind is EvidenceKind.REVIEW_EVIDENCE and self.finding_id is not None:
            _fail("MIXER_EVIDENCE_INVALID", "review evidence must not bind a finding_id")
        if kind is EvidenceKind.RAW_OUTPUT:
            if self.finding_id is not None:
                _fail("MIXER_EVIDENCE_INVALID", "raw output must not bind a finding_id")
            if self.digest is None:
                _fail("MIXER_EVIDENCE_INCOMPLETE", "raw output requires a digest")

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "reviewer_id": self.reviewer_id,
            "kind": self.kind.value,
            "finding_id": self.finding_id,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RetainedEvidenceRef":
        if not isinstance(value, Mapping):
            _fail("MIXER_EVIDENCE_INVALID", "evidence reference must be an object")
        required = {"reference", "reviewer_id", "kind", "finding_id", "digest"}
        if set(value) != required:
            _fail("MIXER_EVIDENCE_INVALID", "evidence reference fields are exact")
        return cls(
            reference=value["reference"],
            reviewer_id=value["reviewer_id"],
            kind=value["kind"],
            finding_id=value["finding_id"],
            digest=value["digest"],
        )


@dataclass(frozen=True, slots=True)
class MixerConflict:
    """Conflict evidence retained even when a later decision resolves it."""

    conflict_id: str
    finding_ids: tuple[str, ...]
    reviewers: tuple[str, ...]
    severities: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    material: bool
    disposition: ConflictDisposition | str = ConflictDisposition.UNRESOLVED
    resolution_evidence_refs: tuple[str, ...] = ()
    rationale: str | None = None
    residual_risk: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "conflict_id", _identifier("conflict_id", self.conflict_id))
        finding_ids = _sorted_unique_identifiers("conflict.finding_ids", self.finding_ids)
        reviewers = _sorted_unique_identifiers("conflict.reviewers", self.reviewers)
        evidence_refs = _sorted_unique_texts("conflict.evidence_refs", self.evidence_refs, allow_empty=False)
        severities = tuple(sorted(_text("conflict.severity", item, max_bytes=32).lower() for item in _sequence("conflict.severities", self.severities, allow_empty=False)))
        if len(finding_ids) < 2:
            _fail("MIXER_CONFLICT_INVALID", "conflict must contain at least two findings")
        if not reviewers:
            _fail("MIXER_CONFLICT_INVALID", "conflict must contain a reviewer")
        if not severities:
            _fail("MIXER_CONFLICT_INVALID", "conflict must contain a severity")
        if not isinstance(self.material, bool):
            _fail("MIXER_CONFLICT_INVALID", "conflict.material must be boolean")
        disposition = _enum_value("conflict.disposition", self.disposition, ConflictDisposition)
        object.__setattr__(self, "finding_ids", finding_ids)
        object.__setattr__(self, "reviewers", reviewers)
        object.__setattr__(self, "severities", severities)
        object.__setattr__(self, "evidence_refs", evidence_refs)
        object.__setattr__(
            self,
            "resolution_evidence_refs",
            _sorted_unique_texts("conflict.resolution_evidence_refs", self.resolution_evidence_refs),
        )
        object.__setattr__(self, "disposition", disposition)
        if self.rationale is not None:
            object.__setattr__(self, "rationale", _text("conflict.rationale", self.rationale))
        if self.residual_risk is not None:
            object.__setattr__(self, "residual_risk", _text("conflict.residual_risk", self.residual_risk))
        if self.material and disposition in {
            ConflictDisposition.RESOLVED,
            ConflictDisposition.ESCALATED,
        } and not self.resolution_evidence_refs:
            _fail("MIXER_CONFLICT_EVIDENCE_MISSING", "material resolution requires evidence")

    @classmethod
    def from_adjudicated(cls, conflict: Any) -> "MixerConflict":
        """Adapt an existing conflict result without dropping any evidence."""

        required = (
            "conflict_id",
            "finding_ids",
            "reviewers",
            "severities",
            "evidence_refs",
            "material",
            "disposition",
        )
        if any(not hasattr(conflict, field) for field in required):
            _fail("MIXER_CONFLICT_INVALID", "adjudicated conflict has incomplete fields")
        return cls(
            conflict_id=conflict.conflict_id,
            finding_ids=tuple(conflict.finding_ids),
            reviewers=tuple(conflict.reviewers),
            severities=tuple(conflict.severities),
            evidence_refs=tuple(conflict.evidence_refs),
            material=conflict.material,
            disposition=conflict.disposition,
            resolution_evidence_refs=tuple(getattr(conflict, "resolution_evidence_refs", ())),
            rationale=getattr(conflict, "rationale", None),
            residual_risk=getattr(conflict, "residual_risk", None),
        )

    @property
    def unresolved_material(self) -> bool:
        return self.material and self.disposition in {
            ConflictDisposition.UNRESOLVED,
            ConflictDisposition.ESCALATED,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "finding_ids": list(self.finding_ids),
            "reviewers": list(self.reviewers),
            "severities": list(self.severities),
            "evidence_refs": list(self.evidence_refs),
            "material": self.material,
            "disposition": self.disposition.value,
            "resolution_evidence_refs": list(self.resolution_evidence_refs),
            "rationale": self.rationale,
            "residual_risk": self.residual_risk,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MixerConflict":
        if not isinstance(value, Mapping):
            _fail("MIXER_CONFLICT_INVALID", "conflict must be an object")
        required = {
            "conflict_id",
            "finding_ids",
            "reviewers",
            "severities",
            "evidence_refs",
            "material",
            "disposition",
            "resolution_evidence_refs",
            "rationale",
            "residual_risk",
        }
        if set(value) != required:
            _fail("MIXER_CONFLICT_INVALID", "conflict fields are exact")
        return cls(
            conflict_id=value["conflict_id"],
            finding_ids=tuple(value["finding_ids"]),
            reviewers=tuple(value["reviewers"]),
            severities=tuple(value["severities"]),
            evidence_refs=tuple(value["evidence_refs"]),
            material=value["material"],
            disposition=value["disposition"],
            resolution_evidence_refs=tuple(value["resolution_evidence_refs"]),
            rationale=value["rationale"],
            residual_risk=value["residual_risk"],
        )


@dataclass(frozen=True, slots=True)
class MixerReviewerInput:
    """One reviewer result bound to its immutable initial receipt."""

    reviewer_id: str
    receipt_digest: str
    finding_digest: str
    verdict: ReviewVerdict | str
    target_ref: str
    findings: tuple[NormalizedFinding, ...]
    retained_evidence: tuple[RetainedEvidenceRef, ...]
    raw_output_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reviewer_id", _identifier("reviewer_id", self.reviewer_id))
        object.__setattr__(self, "receipt_digest", _digest("receipt_digest", self.receipt_digest))
        object.__setattr__(self, "finding_digest", _digest("finding_digest", self.finding_digest))
        object.__setattr__(self, "verdict", _enum_value("verdict", self.verdict, ReviewVerdict))
        object.__setattr__(self, "target_ref", _text("target_ref", self.target_ref))
        findings = _sequence("findings", self.findings)
        if any(not isinstance(item, NormalizedFinding) for item in findings):
            _fail("MIXER_FINDING_INVALID", "findings must contain NormalizedFinding values")
        finding_ids = tuple(item.finding_id for item in findings)
        if len(set(finding_ids)) != len(finding_ids):
            _fail("MIXER_FINDING_ID_CONFLICT", "reviewer input contains duplicate finding IDs")
        if any(item.reviewer != self.reviewer_id for item in findings):
            _fail("MIXER_FINDING_BINDING_MISMATCH", "finding reviewer does not match reviewer input")
        object.__setattr__(self, "findings", tuple(sorted(findings, key=lambda item: item.finding_id)))
        evidence = _sequence("retained_evidence", self.retained_evidence)
        if any(not isinstance(item, RetainedEvidenceRef) for item in evidence):
            _fail("MIXER_EVIDENCE_INVALID", "retained_evidence has invalid values")
        evidence_keys = [self._evidence_key(item) for item in evidence]
        if len(set(evidence_keys)) != len(evidence_keys):
            _fail("MIXER_EVIDENCE_DUPLICATE", "retained_evidence contains duplicate provenance")
        object.__setattr__(self, "retained_evidence", tuple(sorted(evidence, key=self._evidence_key)))
        object.__setattr__(self, "raw_output_digest", _optional_digest("raw_output_digest", self.raw_output_digest))
        if digest_findings(self.findings) != self.finding_digest:
            _fail("MIXER_FINDING_DIGEST_MISMATCH", "finding digest does not match normalized findings")
        self._require_finding_evidence()
        if self.raw_output_digest is not None:
            if not any(
                item.kind is EvidenceKind.RAW_OUTPUT and item.digest == self.raw_output_digest
                for item in self.retained_evidence
            ):
                _fail("MIXER_RAW_EVIDENCE_MISSING", "raw output digest is not retained as evidence")

    @staticmethod
    def _evidence_key(item: RetainedEvidenceRef) -> tuple[str, str, str, str]:
        return (
            item.kind.value,
            item.reviewer_id,
            item.finding_id or "",
            item.reference,
        )

    def _require_finding_evidence(self) -> None:
        retained = {
            (item.finding_id, item.reference)
            for item in self.retained_evidence
            if item.kind is EvidenceKind.FINDING_EVIDENCE
        }
        for finding in self.findings:
            for reference in finding.evidence_refs:
                if (finding.finding_id, reference) not in retained:
                    _fail(
                        "MIXER_FINDING_EVIDENCE_MISSING",
                        f"evidence {reference} for {finding.finding_id} was dropped",
                    )

    @classmethod
    def from_receipt_and_outcome(
        cls,
        receipt: InitialFindingReceipt,
        outcome: ReviewerOutcome,
        *,
        raw_output_digest: str | None = None,
    ) -> "MixerReviewerInput":
        if not isinstance(receipt, InitialFindingReceipt):
            _fail("MIXER_RECEIPT_INVALID", "receipt must be an InitialFindingReceipt")
        if not isinstance(outcome, ReviewerOutcome):
            _fail("MIXER_OUTCOME_INVALID", "outcome must be a ReviewerOutcome")
        if receipt.reviewer_id != outcome.reviewer:
            _fail("MIXER_REVIEWER_BINDING_MISMATCH", "receipt and outcome reviewer differ")
        finding_digest = digest_findings(outcome.findings)
        if finding_digest != receipt.finding_digest:
            _fail("MIXER_FINDING_DIGEST_MISMATCH", "outcome findings differ from receipt")
        evidence: list[RetainedEvidenceRef] = [
            RetainedEvidenceRef(
                reference=reference,
                reviewer_id=outcome.reviewer,
                kind=EvidenceKind.REVIEW_EVIDENCE,
            )
            for reference in outcome.evidence_refs
        ]
        for finding in outcome.findings:
            evidence.extend(
                RetainedEvidenceRef(
                    reference=reference,
                    reviewer_id=outcome.reviewer,
                    kind=EvidenceKind.FINDING_EVIDENCE,
                    finding_id=finding.finding_id,
                )
                for reference in finding.evidence_refs
            )
        if raw_output_digest is not None:
            evidence.append(
                RetainedEvidenceRef(
                    reference=f"raw-output:{outcome.reviewer}",
                    reviewer_id=outcome.reviewer,
                    kind=EvidenceKind.RAW_OUTPUT,
                    digest=raw_output_digest,
                )
            )
        return cls(
            reviewer_id=outcome.reviewer,
            receipt_digest=receipt.receipt_digest or "",
            finding_digest=finding_digest,
            verdict=outcome.verdict,
            target_ref=outcome.target_ref,
            findings=tuple(outcome.findings),
            retained_evidence=tuple(evidence),
            raw_output_digest=raw_output_digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer_id": self.reviewer_id,
            "receipt_digest": self.receipt_digest,
            "finding_digest": self.finding_digest,
            "verdict": self.verdict.value,
            "target_ref": self.target_ref,
            "findings": [item.to_dict() for item in self.findings],
            "retained_evidence": [item.to_dict() for item in self.retained_evidence],
            "raw_output_digest": self.raw_output_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MixerReviewerInput":
        if not isinstance(value, Mapping):
            _fail("MIXER_REVIEWER_INPUT_INVALID", "reviewer input must be an object")
        required = {
            "reviewer_id",
            "receipt_digest",
            "finding_digest",
            "verdict",
            "target_ref",
            "findings",
            "retained_evidence",
            "raw_output_digest",
        }
        if set(value) != required:
            _fail("MIXER_REVIEWER_INPUT_INVALID", "reviewer input fields are exact")
        findings = tuple(_finding_from_dict(item) for item in value["findings"])
        evidence = tuple(RetainedEvidenceRef.from_dict(item) for item in value["retained_evidence"])
        return cls(
            reviewer_id=value["reviewer_id"],
            receipt_digest=value["receipt_digest"],
            finding_digest=value["finding_digest"],
            verdict=value["verdict"],
            target_ref=value["target_ref"],
            findings=findings,
            retained_evidence=evidence,
            raw_output_digest=value["raw_output_digest"],
        )


def _finding_from_dict(value: Any) -> NormalizedFinding:
    if not isinstance(value, Mapping):
        _fail("MIXER_FINDING_INVALID", "finding must be an object")
    required = {
        "finding_id",
        "severity",
        "category",
        "lens",
        "claim",
        "evidence_refs",
        "recommendation",
        "reviewer",
        "disposition",
    }
    optional = {"confidence", "conflict_group"}
    unknown = sorted(set(value) - required - optional)
    missing = sorted(required - set(value))
    if unknown or missing:
        _fail("MIXER_FINDING_INVALID", f"unknown={unknown}, missing={missing}")
    try:
        return NormalizedFinding(
            finding_id=value["finding_id"],
            severity=value["severity"],
            category=value["category"],
            lens=value["lens"],
            claim=value["claim"],
            evidence_refs=tuple(value["evidence_refs"]),
            recommendation=value["recommendation"],
            reviewer=value["reviewer"],
            disposition=value["disposition"],
            confidence=value.get("confidence"),
            conflict_group=value.get("conflict_group"),
        )
    except Exception as exc:
        raise MixerInputManifestError("MIXER_FINDING_INVALID", "finding failed normalization") from exc


@dataclass(frozen=True, slots=True)
class MixerInputManifest:
    """Immutable, quorum-bound input snapshot for a future Mixer."""

    run_id: str
    node_id: str
    attempt_id: str
    source_digest: str
    standards_profile_digest: str
    standards_context_digest: str
    required_reviewer_ids: tuple[str, ...]
    reviewer_inputs: tuple[MixerReviewerInput, ...] = ()
    conflicts: tuple[MixerConflict, ...] = ()
    quorum_policy: QuorumPolicy | str = QuorumPolicy.ALL_REQUIRED
    conflict_policy: ConflictPolicy | str = ConflictPolicy.PRESERVE_ALL
    sealed: bool = False
    protocol: str = MIXER_INPUT_MANIFEST_PROTOCOL
    lease_generation: int | None = None
    fencing_token: str | None = None

    def __post_init__(self) -> None:
        if self.protocol != MIXER_INPUT_MANIFEST_PROTOCOL:
            _fail("MIXER_INPUT_INVALID", "unsupported Mixer input manifest protocol")
        for field in ("run_id", "node_id", "attempt_id"):
            object.__setattr__(self, field, _identifier(field, getattr(self, field)))
        for field in ("source_digest", "standards_profile_digest", "standards_context_digest"):
            object.__setattr__(self, field, _digest(field, getattr(self, field)))
        required = _sorted_unique_identifiers("required_reviewer_ids", self.required_reviewer_ids)
        object.__setattr__(self, "required_reviewer_ids", required)
        quorum = _enum_value("quorum_policy", self.quorum_policy, QuorumPolicy)
        conflict_policy = _enum_value("conflict_policy", self.conflict_policy, ConflictPolicy)
        object.__setattr__(self, "quorum_policy", quorum)
        object.__setattr__(self, "conflict_policy", conflict_policy)
        if not isinstance(self.sealed, bool):
            _fail("MIXER_INPUT_INVALID", "sealed must be boolean")
        if self.lease_generation is not None:
            if isinstance(self.lease_generation, bool) or not isinstance(self.lease_generation, int) or self.lease_generation < 0:
                _fail("MIXER_INPUT_INVALID", "lease_generation must be a non-negative integer")
        if self.fencing_token is not None:
            object.__setattr__(self, "fencing_token", _text("fencing_token", self.fencing_token, max_bytes=4096))
        reviewer_inputs = _sequence("reviewer_inputs", self.reviewer_inputs)
        if any(not isinstance(item, MixerReviewerInput) for item in reviewer_inputs):
            _fail("MIXER_REVIEWER_INPUT_INVALID", "reviewer_inputs contain invalid values")
        reviewer_ids = tuple(item.reviewer_id for item in reviewer_inputs)
        if len(set(reviewer_ids)) != len(reviewer_ids):
            _fail("MIXER_REVIEWER_DUPLICATE", "one reviewer has multiple Mixer inputs")
        unknown_reviewers = sorted(set(reviewer_ids) - set(required))
        if unknown_reviewers:
            _fail("MIXER_REVIEWER_UNKNOWN", ", ".join(unknown_reviewers))
        receipt_digests = tuple(item.receipt_digest for item in reviewer_inputs)
        if len(set(receipt_digests)) != len(receipt_digests):
            _fail("MIXER_RECEIPT_DUPLICATE", "receipt digest is reused by multiple reviewers")
        object.__setattr__(
            self,
            "reviewer_inputs",
            tuple(sorted(reviewer_inputs, key=lambda item: item.reviewer_id)),
        )
        conflicts = _sequence("conflicts", self.conflicts)
        if any(not isinstance(item, MixerConflict) for item in conflicts):
            _fail("MIXER_CONFLICT_INVALID", "conflicts contain invalid values")
        conflict_ids = tuple(item.conflict_id for item in conflicts)
        if len(set(conflict_ids)) != len(conflict_ids):
            _fail("MIXER_CONFLICT_DUPLICATE", "conflict IDs must be unique")
        object.__setattr__(self, "conflicts", tuple(sorted(conflicts, key=lambda item: item.conflict_id)))
        self._validate_findings_and_conflicts()
        if self.sealed and not self.ready_for_mixer:
            _fail("MIXER_QUORUM_INCOMPLETE", "sealed manifest must satisfy ALL_REQUIRED quorum")

    @classmethod
    def from_receipt_ledger(
        cls,
        ledger: InitialFindingReceiptLedger,
        outcomes: Iterable[ReviewerOutcome],
        *,
        raw_output_digests: Mapping[str, str] | None = None,
        conflicts: Iterable[MixerConflict] = (),
        parent_attempt_id: str | None = None,
        lease_generation: int | None = None,
        fencing_token: str | None = None,
    ) -> "MixerInputManifest":
        if not isinstance(ledger, InitialFindingReceiptLedger):
            _fail("MIXER_LEDGER_INVALID", "ledger must be an InitialFindingReceiptLedger")
        requirements = tuple(ledger.required_sessions)
        if not requirements:
            _fail("MIXER_LEDGER_INVALID", "ledger must declare required reviewers")
        identity_fields = (
            "run_id",
            "node_id",
            "attempt_id",
            "source_digest",
            "standards_profile_digest",
            "standards_context_digest",
        )
        first = requirements[0]
        for requirement in requirements[1:]:
            if any(getattr(requirement, field) != getattr(first, field) for field in identity_fields):
                _fail("MIXER_LEDGER_BINDING_MISMATCH", "required reviewers do not share one bound identity")
        outcome_values = _sequence("outcomes", outcomes)
        if any(not isinstance(item, ReviewerOutcome) for item in outcome_values):
            _fail("MIXER_OUTCOME_INVALID", "outcomes must contain ReviewerOutcome values")
        outcome_map: dict[str, ReviewerOutcome] = {}
        for outcome in outcome_values:
            if outcome.reviewer in outcome_map:
                _fail("MIXER_REVIEWER_DUPLICATE", f"duplicate outcome for {outcome.reviewer}")
            outcome_map[outcome.reviewer] = outcome
        required_ids = tuple(requirement.reviewer_id for requirement in requirements)
        unknown = sorted(set(outcome_map) - set(required_ids))
        if unknown:
            _fail("MIXER_REVIEWER_UNKNOWN", ", ".join(unknown))
        raw_map: dict[str, str] = {}
        if raw_output_digests is not None:
            if not isinstance(raw_output_digests, Mapping):
                _fail("MIXER_RAW_EVIDENCE_INVALID", "raw_output_digests must be a mapping")
            for reviewer, digest in raw_output_digests.items():
                if reviewer not in set(required_ids):
                    _fail("MIXER_REVIEWER_UNKNOWN", str(reviewer))
                raw_map[reviewer] = _digest(f"raw_output_digests.{reviewer}", digest)
        inputs: list[MixerReviewerInput] = []
        for receipt in ledger.receipts:
            outcome = outcome_map.get(receipt.reviewer_id)
            if outcome is None:
                _fail("MIXER_OUTCOME_MISSING", f"no normalized outcome for {receipt.reviewer_id}")
            inputs.append(
                MixerReviewerInput.from_receipt_and_outcome(
                    receipt,
                    outcome,
                    raw_output_digest=raw_map.get(receipt.reviewer_id),
                )
            )
        if parent_attempt_id is not None and parent_attempt_id != getattr(first, "attempt_id"):
            _fail("MIXER_LEDGER_BINDING_MISMATCH", "parent_attempt_id differs from reviewer session identity")
        return cls(
            run_id=first.run_id,
            node_id=first.node_id,
            attempt_id=first.attempt_id,
            source_digest=first.source_digest,
            standards_profile_digest=first.standards_profile_digest,
            standards_context_digest=first.standards_context_digest,
            required_reviewer_ids=required_ids,
            reviewer_inputs=tuple(inputs),
            conflicts=tuple(conflicts),
            lease_generation=lease_generation,
            fencing_token=fencing_token,
        )

    def _validate_findings_and_conflicts(self) -> None:
        findings = [finding for item in self.reviewer_inputs for finding in item.findings]
        finding_ids = [finding.finding_id for finding in findings]
        if len(set(finding_ids)) != len(finding_ids):
            _fail("MIXER_FINDING_ID_CONFLICT", "finding IDs must be globally unique in the input manifest")
        known_findings = set(finding_ids)
        retained_refs = {item.reference for item in self.retained_evidence_refs}
        for conflict in self.conflicts:
            if not set(conflict.finding_ids).issubset(known_findings):
                _fail("MIXER_CONFLICT_BINDING_MISMATCH", f"{conflict.conflict_id} references an unknown finding")
            if not set(conflict.evidence_refs).issubset(retained_refs):
                _fail("MIXER_CONFLICT_EVIDENCE_MISSING", f"{conflict.conflict_id} references dropped evidence")
            if not set(conflict.resolution_evidence_refs).issubset(retained_refs):
                _fail("MIXER_CONFLICT_EVIDENCE_MISSING", f"{conflict.conflict_id} resolution evidence is not retained")

    @property
    def reviewer_ids(self) -> tuple[str, ...]:
        return tuple(item.reviewer_id for item in self.reviewer_inputs)

    @property
    def received_reviewer_ids(self) -> tuple[str, ...]:
        return self.reviewer_ids

    @property
    def missing_reviewer_ids(self) -> tuple[str, ...]:
        received = set(self.received_reviewer_ids)
        return tuple(item for item in self.required_reviewer_ids if item not in received)

    @property
    def ready_for_mixer(self) -> bool:
        return not self.missing_reviewer_ids

    @property
    def received_receipt_digests(self) -> tuple[str, ...]:
        return tuple(sorted(item.receipt_digest for item in self.reviewer_inputs))

    @property
    def finding_ids(self) -> tuple[str, ...]:
        return tuple(sorted(finding.finding_id for item in self.reviewer_inputs for finding in item.findings))

    @property
    def all_findings(self) -> tuple[NormalizedFinding, ...]:
        return tuple(
            finding
            for item in self.reviewer_inputs
            for finding in sorted(item.findings, key=lambda value: value.finding_id)
        )

    @property
    def retained_evidence_refs(self) -> tuple[RetainedEvidenceRef, ...]:
        evidence = [item for reviewer in self.reviewer_inputs for item in reviewer.retained_evidence]
        return tuple(sorted(evidence, key=MixerReviewerInput._evidence_key))

    @property
    def raw_evidence_refs(self) -> tuple[RetainedEvidenceRef, ...]:
        return self.retained_evidence_refs

    @property
    def raw_output_digests(self) -> tuple[str, ...]:
        return tuple(sorted(item.raw_output_digest for item in self.reviewer_inputs if item.raw_output_digest))

    @property
    def material_conflict_ids(self) -> tuple[str, ...]:
        return tuple(sorted(item.conflict_id for item in self.conflicts if item.material))

    @property
    def unresolved_material_conflict_ids(self) -> tuple[str, ...]:
        return tuple(sorted(item.conflict_id for item in self.conflicts if item.unresolved_material))

    @property
    def severity_inventory(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.all_findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def high_severity_finding_ids(self) -> tuple[str, ...]:
        return tuple(sorted(finding.finding_id for finding in self.all_findings if finding.severity in _HIGH_SEVERITIES))

    @property
    def high_severity_evidence_refs(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    reference
                    for finding in self.all_findings
                    if finding.severity in _HIGH_SEVERITIES
                    for reference in finding.evidence_refs
                }
            )
        )

    def require_mixer_ready(self) -> "MixerInputManifest":
        if not self.ready_for_mixer:
            _fail("MIXER_QUORUM_INCOMPLETE", f"missing reviewers: {', '.join(self.missing_reviewer_ids)}")
        return self

    def require_clean_synthesis_ready(self) -> "MixerInputManifest":
        self.require_mixer_ready()
        if self.unresolved_material_conflict_ids:
            _fail(
                "MATERIAL_CONFLICT_UNRESOLVED",
                f"unresolved material conflicts: {', '.join(self.unresolved_material_conflict_ids)}",
            )
        return self

    def seal(self) -> "MixerInputManifest":
        self.require_mixer_ready()
        if self.sealed:
            return self
        return replace(self, sealed=True)

    def _canonical_payload(self) -> dict[str, Any]:
        payload = {
            "protocol": self.protocol,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt_id": self.attempt_id,
            "source_digest": self.source_digest,
            "standards_profile_digest": self.standards_profile_digest,
            "standards_context_digest": self.standards_context_digest,
            "quorum": {
                "policy": self.quorum_policy.value,
                "required_reviewer_ids": list(self.required_reviewer_ids),
                "received_reviewer_ids": list(self.received_reviewer_ids),
                "missing_reviewer_ids": list(self.missing_reviewer_ids),
                "satisfied": self.ready_for_mixer,
            },
            "conflict_policy": self.conflict_policy.value,
            "reviewer_inputs": [item.to_dict() for item in self.reviewer_inputs],
            "conflicts": [item.to_dict() for item in self.conflicts],
            "severity": {
                "inventory": self.severity_inventory,
                "high_severity_finding_ids": list(self.high_severity_finding_ids),
                "high_severity_evidence_refs": list(self.high_severity_evidence_refs),
            },
            "retained_evidence_refs": [item.to_dict() for item in self.retained_evidence_refs],
            "sealed": self.sealed,
        }
        if self.lease_generation is not None:
            payload["lease_generation"] = self.lease_generation
        if self.fencing_token is not None:
            payload["fencing_token"] = self.fencing_token
        return payload

    @property
    def manifest_digest(self) -> str:
        return _digest_payload(self._canonical_payload())

    def to_dict(self) -> dict[str, Any]:
        payload = copy.deepcopy(self._canonical_payload())
        payload["manifest_digest"] = self.manifest_digest
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MixerInputManifest":
        if not isinstance(value, Mapping):
            _fail("MIXER_INPUT_INVALID", "manifest must be an object")
        required = {
            "protocol",
            "run_id",
            "node_id",
            "attempt_id",
            "source_digest",
            "standards_profile_digest",
            "standards_context_digest",
            "quorum",
            "conflict_policy",
            "reviewer_inputs",
            "conflicts",
            "severity",
            "retained_evidence_refs",
            "sealed",
            "manifest_digest",
        }
        optional = {"lease_generation", "fencing_token"}
        if not set(value).issubset(required | optional) or not required.issubset(set(value)):
            _fail("MIXER_INPUT_INVALID", "manifest fields are exact")
        quorum = value["quorum"]
        if not isinstance(quorum, Mapping):
            _fail("MIXER_INPUT_INVALID", "quorum must be an object")
        quorum_required = {"policy", "required_reviewer_ids", "received_reviewer_ids", "missing_reviewer_ids", "satisfied"}
        if set(quorum) != quorum_required:
            _fail("MIXER_INPUT_INVALID", "quorum fields are exact")
        manifest = cls(
            protocol=value["protocol"],
            run_id=value["run_id"],
            node_id=value["node_id"],
            attempt_id=value["attempt_id"],
            source_digest=value["source_digest"],
            standards_profile_digest=value["standards_profile_digest"],
            standards_context_digest=value["standards_context_digest"],
            required_reviewer_ids=tuple(quorum["required_reviewer_ids"]),
            reviewer_inputs=tuple(MixerReviewerInput.from_dict(item) for item in value["reviewer_inputs"]),
            conflicts=tuple(MixerConflict.from_dict(item) for item in value["conflicts"]),
            quorum_policy=quorum["policy"],
            conflict_policy=value["conflict_policy"],
            sealed=value["sealed"],
            lease_generation=value.get("lease_generation"),
            fencing_token=value.get("fencing_token"),
        )
        if value["manifest_digest"] != manifest.manifest_digest:
            _fail("MIXER_MANIFEST_DIGEST_MISMATCH", "manifest_digest does not match canonical input")
        if tuple(quorum["received_reviewer_ids"]) != manifest.received_reviewer_ids:
            _fail("MIXER_MANIFEST_DIGEST_MISMATCH", "received reviewer projection is inconsistent")
        if tuple(quorum["missing_reviewer_ids"]) != manifest.missing_reviewer_ids:
            _fail("MIXER_MANIFEST_DIGEST_MISMATCH", "missing reviewer projection is inconsistent")
        if quorum["satisfied"] is not manifest.ready_for_mixer:
            _fail("MIXER_MANIFEST_DIGEST_MISMATCH", "quorum projection is inconsistent")
        return manifest

    def generation_identity(self) -> dict[str, Any]:
        """Return the v2 Mixer parent fence; legacy manifests remain v1-compatible."""
        if self.lease_generation is None or self.fencing_token is None:
            _fail(
                "MIXER_GENERATION_REQUIRED",
                "current-generation Mixer write requires lease_generation and fencing_token",
            )
        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt_id": self.attempt_id,
            "lease_generation": self.lease_generation,
            "fencing_token": self.fencing_token,
        }

    def generation_decision(self, current: Mapping[str, Any]) -> GenerationFenceDecision:
        try:
            return evaluate_generation_fence(self.generation_identity(), current)
        except GenerationFenceError as exc:
            raise MixerInputManifestError(exc.code, str(exc)) from exc


__all__ = [
    "MIXER_INPUT_MANIFEST_PROTOCOL",
    "ConflictPolicy",
    "EvidenceKind",
    "MixerConflict",
    "MixerInputManifest",
    "MixerInputManifestError",
    "MixerReviewerInput",
    "QuorumPolicy",
    "RetainedEvidenceRef",
]
