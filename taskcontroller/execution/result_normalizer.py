"""TC-MBX-506 provider-neutral child-result normalization.

This module is a pre-Mixer evidence seam. It converts bounded free-form or
structured child output into immutable artifact/finding records, or returns an
explicit failed/retryable result. It never invokes providers, persists raw
output, dispatches children, or changes mailbox/runtime state.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, NoReturn

from taskcontroller.errors import TaskControllerValidationError


RESULT_NORMALIZER_PROTOCOL = "dw.taskcontroller.child-result-normalizer/v1"
MAX_CHILD_ID_LENGTH = 128
MAX_REVIEWER_LENGTH = 128
MAX_LENS_LENGTH = 128
MAX_CATEGORY_LENGTH = 128
MAX_ARTIFACTS = 64
MAX_FINDINGS = 64
MAX_EVIDENCE_REFS = 256
MAX_MEDIA_TYPE_LENGTH = 128
MAX_CONTENT_REF_LENGTH = 2048
MAX_DIGEST_LENGTH = 80
MAX_CLAIM_LENGTH = 2048
MAX_RECOMMENDATION_LENGTH = 2048
MAX_FAILURE_MESSAGE_LENGTH = 512
MAX_RAW_OUTPUT_BYTES = 256 * 1024

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SEVERITIES = frozenset({"critical", "major", "minor", "info"})
_DISPOSITIONS = frozenset({"OPEN", "ACCEPTED", "REJECTED", "DEFERRED", "ESCALATED"})
_OUTPUT_STATUSES = frozenset({"SUCCEEDED", "FAILED", "NEEDS_RETRY"})
_MISSING = object()


class NormalizationStatus(str, Enum):
    """Local pre-Mixer disposition of one child output."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    NEEDS_RETRY = "NEEDS_RETRY"


class ChildResultNormalizationError(TaskControllerValidationError):
    """Stable, fail-closed validation error used inside the normalizer."""

    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str, *, retryable: bool = True) -> NoReturn:
    raise ChildResultNormalizationError(code, message, retryable=retryable)


def _text(name: str, value: Any, limit: int) -> str:
    if not isinstance(value, str):
        _fail("CHILD_OUTPUT_INVALID", f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        _fail("CHILD_OUTPUT_INVALID", f"{name} must be non-empty")
    if "\x00" in normalized:
        _fail("CHILD_OUTPUT_INVALID", f"{name} must not contain NUL characters")
    if len(normalized.encode("utf-8")) > limit:
        _fail("CHILD_OUTPUT_LIMIT_EXCEEDED", f"{name} exceeds its byte limit")
    return normalized


def _identifier(name: str, value: Any, limit: int) -> str:
    normalized = _text(name, value, limit)
    if not _ID_RE.fullmatch(normalized):
        _fail("CHILD_OUTPUT_INVALID", f"{name} must be a stable identifier")
    return normalized


def _digest(name: str, value: Any) -> str:
    normalized = _text(name, value, MAX_DIGEST_LENGTH)
    if not _DIGEST_RE.fullmatch(normalized):
        _fail("CHILD_OUTPUT_INVALID", f"{name} must be sha256:<64 lowercase hex>")
    return normalized


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("CHILD_OUTPUT_NOT_SERIALIZABLE", f"output is not canonical JSON: {type(exc).__name__}")
    if len(encoded) > MAX_RAW_OUTPUT_BYTES:
        _fail("CHILD_OUTPUT_LIMIT_EXCEEDED", "raw output exceeds the bounded byte limit")
    return encoded


def _raw_digest(value: Any) -> str | None:
    try:
        if isinstance(value, str):
            encoded = value.encode("utf-8")
            if len(encoded) > MAX_RAW_OUTPUT_BYTES:
                return None
            return _sha256_bytes(encoded)
        return _sha256_bytes(_canonical_bytes(value))
    except ChildResultNormalizationError:
        return None


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("CHILD_OUTPUT_INVALID", f"{name} must be an object")
    result = dict(value)
    if any(not isinstance(key, str) for key in result):
        _fail("CHILD_OUTPUT_INVALID", f"{name} keys must be strings")
    return result


def _sequence(value: Any, name: str, limit: int) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        _fail("CHILD_OUTPUT_INVALID", f"{name} must be an array")
    if len(value) > limit:
        _fail("CHILD_OUTPUT_LIMIT_EXCEEDED", f"{name} exceeds its item limit")
    return tuple(value)


def _derived_id(prefix: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_bytes(dict(payload))).hexdigest()
    return f"{prefix}-{digest[:32]}"


def _alias(candidate: dict[str, Any], canonical: str, aliases: Sequence[str]) -> None:
    present = [key for key in (canonical, *aliases) if key in candidate]
    if not present:
        return
    values = [candidate[key] for key in present]
    if any(value != values[0] for value in values[1:]):
        _fail("CHILD_OUTPUT_INVALID", f"conflicting aliases for {canonical}")
    candidate[canonical] = values[0]


@dataclass(frozen=True, slots=True)
class NormalizationFailure:
    """Bounded machine-readable failure evidence; never contains raw output."""

    code: str
    message: str
    retryable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _identifier("failure.code", self.code, 128))
        object.__setattr__(
            self,
            "message",
            _text("failure.message", self.message, MAX_FAILURE_MESSAGE_LENGTH),
        )
        if not isinstance(self.retryable, bool):
            _fail("CHILD_OUTPUT_INVALID", "failure.retryable must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(frozen=True, slots=True)
class NormalizedArtifact:
    """Digest/reference-only artifact emitted from a child output."""

    artifact_id: str
    content_ref: str
    media_type: str
    digest: str
    provenance: Mapping[str, str]
    schema_ref: str | None = None
    schema_version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _identifier("artifact_id", self.artifact_id, MAX_CHILD_ID_LENGTH),
        )
        object.__setattr__(
            self,
            "content_ref",
            _text("content_ref", self.content_ref, MAX_CONTENT_REF_LENGTH),
        )
        object.__setattr__(
            self,
            "media_type",
            _text("media_type", self.media_type, MAX_MEDIA_TYPE_LENGTH),
        )
        object.__setattr__(self, "digest", _digest("artifact.digest", self.digest))
        if not isinstance(self.provenance, Mapping):
            _fail("CHILD_OUTPUT_INVALID", "artifact.provenance must be an object")
        normalized: dict[str, str] = {}
        for key, value in self.provenance.items():
            normalized[_identifier("provenance key", key, 128)] = _text(
                f"provenance.{key}", value, MAX_CONTENT_REF_LENGTH
            )
        object.__setattr__(self, "provenance", dict(sorted(normalized.items())))
        if self.schema_ref is not None:
            object.__setattr__(self, "schema_ref", _text("schema_ref", self.schema_ref, MAX_CONTENT_REF_LENGTH))
        if self.schema_version is not None:
            object.__setattr__(
                self,
                "schema_version",
                _text("schema_version", self.schema_version, MAX_CONTENT_REF_LENGTH),
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "content_ref": self.content_ref,
            "media_type": self.media_type,
            "digest": self.digest,
            "provenance": dict(self.provenance),
        }
        if self.schema_ref is not None:
            result["schema_ref"] = self.schema_ref
        if self.schema_version is not None:
            result["schema_version"] = self.schema_version
        return result


@dataclass(frozen=True, slots=True)
class NormalizedFinding:
    """Finding shape aligned with the normative mailbox/v2 finding fields."""

    finding_id: str
    severity: str
    category: str
    lens: str
    claim: str
    evidence_refs: tuple[str, ...]
    recommendation: str
    reviewer: str
    disposition: str = "OPEN"
    confidence: float | None = None
    conflict_group: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "finding_id",
            _identifier("finding_id", self.finding_id, MAX_CHILD_ID_LENGTH),
        )
        severity = _text("severity", self.severity, 32).lower()
        if severity not in _SEVERITIES:
            _fail("CHILD_OUTPUT_INVALID", "severity is not a supported finding severity")
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "category", _text("category", self.category, MAX_CATEGORY_LENGTH))
        object.__setattr__(self, "lens", _text("lens", self.lens, MAX_LENS_LENGTH))
        object.__setattr__(self, "claim", _text("claim", self.claim, MAX_CLAIM_LENGTH))
        refs = _sequence(self.evidence_refs, "evidence_refs", MAX_EVIDENCE_REFS)
        if not refs:
            _fail("CHILD_OUTPUT_INVALID", "evidence_refs must contain at least one reference")
        normalized_refs = tuple(sorted({_text("evidence_ref", ref, MAX_CONTENT_REF_LENGTH) for ref in refs}))
        if len(normalized_refs) != len(refs):
            _fail("CHILD_OUTPUT_INVALID", "evidence_refs must not contain duplicates")
        object.__setattr__(self, "evidence_refs", normalized_refs)
        object.__setattr__(
            self,
            "recommendation",
            _text("recommendation", self.recommendation, MAX_RECOMMENDATION_LENGTH),
        )
        object.__setattr__(
            self,
            "reviewer",
            _identifier("reviewer", self.reviewer, MAX_REVIEWER_LENGTH),
        )
        disposition = _text("disposition", self.disposition, 32).upper()
        if disposition not in _DISPOSITIONS:
            _fail("CHILD_OUTPUT_INVALID", "disposition is not a supported finding disposition")
        object.__setattr__(self, "disposition", disposition)
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
                _fail("CHILD_OUTPUT_INVALID", "confidence must be numeric")
            if not 0 <= self.confidence <= 1:
                _fail("CHILD_OUTPUT_INVALID", "confidence must be between 0 and 1")
            object.__setattr__(self, "confidence", float(self.confidence))
        if self.conflict_group is not None:
            object.__setattr__(
                self,
                "conflict_group",
                _text("conflict_group", self.conflict_group, MAX_CHILD_ID_LENGTH),
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "category": self.category,
            "lens": self.lens,
            "claim": self.claim,
            "evidence_refs": list(self.evidence_refs),
            "recommendation": self.recommendation,
            "reviewer": self.reviewer,
            "disposition": self.disposition,
        }
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.conflict_group is not None:
            result["conflict_group"] = self.conflict_group
        return result


@dataclass(frozen=True, slots=True)
class NormalizedChildResult:
    """Immutable, bounded output handed to a future Mixer adapter."""

    child_id: str
    status: NormalizationStatus
    raw_output_digest: str | None
    artifacts: tuple[NormalizedArtifact, ...] = ()
    findings: tuple[NormalizedFinding, ...] = ()
    failure: NormalizationFailure | None = None
    child_contract_digest: str | None = None
    source_digest: str | None = None
    lens: str | None = None
    reviewer: str | None = None
    protocol: str = RESULT_NORMALIZER_PROTOCOL

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "child_id",
            _identifier("child_id", self.child_id, MAX_CHILD_ID_LENGTH),
        )
        if not isinstance(self.status, NormalizationStatus):
            try:
                object.__setattr__(self, "status", NormalizationStatus(self.status))
            except (TypeError, ValueError):
                _fail("CHILD_OUTPUT_INVALID", "status is not a supported normalization status")
        if self.raw_output_digest is not None:
            object.__setattr__(self, "raw_output_digest", _digest("raw_output_digest", self.raw_output_digest))
        artifacts = tuple(self.artifacts)
        findings = tuple(self.findings)
        if len(artifacts) > MAX_ARTIFACTS or len(findings) > MAX_FINDINGS:
            _fail("CHILD_OUTPUT_LIMIT_EXCEEDED", "normalized result exceeds its item limit")
        artifact_ids = [item.artifact_id for item in artifacts]
        finding_ids = [item.finding_id for item in findings]
        if len(set(artifact_ids)) != len(artifact_ids) or len(set(finding_ids)) != len(finding_ids):
            _fail("CHILD_OUTPUT_INVALID", "normalized result contains duplicate IDs")
        object.__setattr__(self, "artifacts", tuple(sorted(artifacts, key=lambda item: item.artifact_id)))
        object.__setattr__(self, "findings", tuple(sorted(findings, key=lambda item: item.finding_id)))
        if self.failure is not None and not isinstance(self.failure, NormalizationFailure):
            _fail("CHILD_OUTPUT_INVALID", "failure must be a NormalizationFailure")
        if self.status is NormalizationStatus.SUCCEEDED and self.failure is not None:
            _fail("CHILD_OUTPUT_INVALID", "successful result must not carry failure")
        if self.status is not NormalizationStatus.SUCCEEDED and self.failure is None:
            _fail("CHILD_OUTPUT_INVALID", "failed result must carry failure")
        if self.child_contract_digest is not None:
            object.__setattr__(
                self,
                "child_contract_digest",
                _digest("child_contract_digest", self.child_contract_digest),
            )
        if self.source_digest is not None:
            object.__setattr__(self, "source_digest", _digest("source_digest", self.source_digest))
        if self.lens is not None:
            object.__setattr__(self, "lens", _text("lens", self.lens, MAX_LENS_LENGTH))
        if self.reviewer is not None:
            object.__setattr__(self, "reviewer", _identifier("reviewer", self.reviewer, MAX_REVIEWER_LENGTH))
        object.__setattr__(self, "protocol", _text("protocol", self.protocol, 128))

    def _canonical_payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "protocol": self.protocol,
            "child_id": self.child_id,
            "status": self.status.value,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "findings": [item.to_dict() for item in self.findings],
        }
        for key in ("child_contract_digest", "source_digest", "lens", "reviewer"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        if self.failure is not None:
            result["failure"] = self.failure.to_dict()
        return result

    @property
    def normalization_digest(self) -> str:
        return _sha256_bytes(_canonical_bytes(self._canonical_payload()))

    def to_dict(self) -> dict[str, Any]:
        result = self._canonical_payload()
        result["raw_output_digest"] = self.raw_output_digest
        result["normalization_digest"] = self.normalization_digest
        return result


class ChildResultNormalizer:
    """Normalize one child output without invoking or persisting provider data."""

    def __init__(
        self,
        *,
        child_id: str = "child",
        child_contract_digest: str | None = None,
        source_digest: str | None = None,
        lens: str | None = None,
        reviewer: str | None = None,
    ) -> None:
        self._child_id = child_id
        self._child_contract_digest = child_contract_digest
        self._source_digest = source_digest
        self._lens = lens
        self._reviewer = reviewer

    def normalize(
        self,
        raw_output_or_child_id: Any,
        raw_output: Any = _MISSING,
        *,
        child_id: str | None = None,
        child_contract_digest: str | None | object = _MISSING,
        source_digest: str | None | object = _MISSING,
        lens: str | None | object = _MISSING,
        reviewer: str | None | object = _MISSING,
    ) -> NormalizedChildResult:
        """Return a success or explicit failure result for one child output.

        The one-argument form uses constructor bindings.  A two-positional form
        ``normalize(child_id, raw_output)`` is also accepted for adapter callers.
        """

        if raw_output is _MISSING:
            effective_child_id = child_id if child_id is not None else self._child_id
            value = raw_output_or_child_id
        else:
            effective_child_id = raw_output_or_child_id
            value = raw_output
        bindings: dict[str, Any] = {
            "child_contract_digest": self._child_contract_digest if child_contract_digest is _MISSING else child_contract_digest,
            "source_digest": self._source_digest if source_digest is _MISSING else source_digest,
            "lens": self._lens if lens is _MISSING else lens,
            "reviewer": self._reviewer if reviewer is _MISSING else reviewer,
        }
        raw_digest = _raw_digest(value)
        try:
            normalized_child_id = _identifier("child_id", effective_child_id, MAX_CHILD_ID_LENGTH)
            normalized_bindings = self._normalize_bindings(bindings)
            if isinstance(value, str) and len(value.encode("utf-8")) > MAX_RAW_OUTPUT_BYTES:
                _fail("CHILD_OUTPUT_LIMIT_EXCEEDED", "raw output exceeds the bounded byte limit")
            if raw_digest is None and not isinstance(value, str):
                _fail("CHILD_OUTPUT_NOT_SERIALIZABLE", "raw output cannot be represented as bounded JSON")
            if isinstance(value, str):
                if not value.strip():
                    _fail("CHILD_OUTPUT_EMPTY", "text output is empty")
                artifact = self._inline_artifact(value, normalized_child_id, normalized_bindings)
                return NormalizedChildResult(
                    child_id=normalized_child_id,
                    status=NormalizationStatus.SUCCEEDED,
                    raw_output_digest=raw_digest,
                    artifacts=(artifact,),
                    child_contract_digest=normalized_bindings["child_contract_digest"],
                    source_digest=normalized_bindings["source_digest"],
                    lens=normalized_bindings["lens"],
                    reviewer=normalized_bindings["reviewer"],
                )
            candidate = _mapping(value, "child output")
            return self._normalize_mapping(candidate, normalized_child_id, raw_digest, normalized_bindings)
        except ChildResultNormalizationError as exc:
            safe_child_id = self._safe_child_id(effective_child_id)
            safe_bindings = self._safe_bindings(bindings)
            return self._failure_result(
                safe_child_id,
                raw_digest,
                exc.code,
                exc.message.split(": ", 1)[-1],
                exc.retryable,
                safe_bindings,
            )

    def _normalize_bindings(self, bindings: Mapping[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in ("child_contract_digest", "source_digest"):
            value = bindings[name]
            if value is None:
                result[name] = None
                continue
            try:
                result[name] = _digest(name, value)
            except ChildResultNormalizationError:
                _fail("CHILD_BINDING_INVALID", f"{name} binding is invalid")
        for name, limit in (("lens", MAX_LENS_LENGTH), ("reviewer", MAX_REVIEWER_LENGTH)):
            value = bindings[name]
            if value is None:
                result[name] = None
                continue
            try:
                result[name] = _text(name, value, limit)
            except ChildResultNormalizationError:
                _fail("CHILD_BINDING_INVALID", f"{name} binding is invalid")
        return result

    def _normalize_mapping(
        self,
        candidate: dict[str, Any],
        child_id: str,
        raw_digest: str | None,
        bindings: Mapping[str, Any],
    ) -> NormalizedChildResult:
        allowed = {
            "status",
            "artifacts",
            "findings",
            "output",
            "text",
            "message",
            "summary",
            "failure_code",
        }
        unknown = sorted(set(candidate) - allowed)
        if unknown:
            _fail("CHILD_OUTPUT_INVALID", "unsupported child output fields")
        status = candidate.get("status")
        if status is not None:
            status = _text("status", status, 32).upper()
            if status not in _OUTPUT_STATUSES:
                _fail("CHILD_OUTPUT_INVALID", "status is not supported")
        if status in {NormalizationStatus.FAILED.value, NormalizationStatus.NEEDS_RETRY.value}:
            if candidate.get("artifacts") not in (None, [], ()) or candidate.get("findings") not in (None, [], ()):
                _fail("CHILD_OUTPUT_INVALID", "non-success output must not carry result payloads")
            return self._failure_result(
                child_id,
                raw_digest,
                "CHILD_REPORTED_FAILURE",
                "child reported a non-success status",
                True,
                bindings,
                status=NormalizationStatus(status),
            )

        artifacts_value = candidate.get("artifacts", [])
        findings_value = candidate.get("findings", [])
        artifact_values = _sequence(artifacts_value, "artifacts", MAX_ARTIFACTS)
        finding_values = _sequence(findings_value, "findings", MAX_FINDINGS)
        free_text = self._free_text(candidate)
        if not artifact_values and not finding_values and free_text is None:
            _fail("CHILD_OUTPUT_EMPTY", "child output contains no artifact, finding or text")

        artifacts = [
            self._artifact_from_mapping(item, child_id, bindings)
            for item in artifact_values
        ]
        if free_text is not None:
            artifacts.append(self._inline_artifact(free_text, child_id, bindings))
        findings = [
            self._finding_from_mapping(item, child_id, bindings)
            for item in finding_values
        ]
        return NormalizedChildResult(
            child_id=child_id,
            status=NormalizationStatus.SUCCEEDED,
            raw_output_digest=raw_digest,
            artifacts=tuple(artifacts),
            findings=tuple(findings),
            child_contract_digest=bindings["child_contract_digest"],
            source_digest=bindings["source_digest"],
            lens=bindings["lens"],
            reviewer=bindings["reviewer"],
        )

    def _free_text(self, candidate: Mapping[str, Any]) -> str | None:
        keys = [key for key in ("output", "text", "message", "summary") if key in candidate]
        if not keys:
            return None
        values = [_text(key, candidate[key], MAX_CLAIM_LENGTH) for key in keys]
        if any(value != values[0] for value in values[1:]):
            _fail("CHILD_OUTPUT_INVALID", "conflicting free-form output fields")
        return values[0]

    def _artifact_from_mapping(
        self,
        value: Any,
        child_id: str,
        bindings: Mapping[str, Any],
    ) -> NormalizedArtifact:
        candidate = _mapping(value, "artifact")
        allowed = {
            "artifact_id",
            "content_ref",
            "media_type",
            "digest",
            "content",
            "schema_ref",
            "schema_version",
        }
        if sorted(set(candidate) - allowed):
            _fail("CHILD_OUTPUT_INVALID", "unsupported artifact fields")
        content = candidate.get("content")
        supplied_digest = candidate.get("digest")
        if content is not None:
            if not isinstance(content, str):
                _fail("CHILD_OUTPUT_INVALID", "artifact.content must be a string")
            content_bytes = content.encode("utf-8")
            if len(content_bytes) > MAX_RAW_OUTPUT_BYTES:
                _fail("CHILD_OUTPUT_LIMIT_EXCEEDED", "artifact content exceeds the bounded byte limit")
            computed_digest = _sha256_bytes(content_bytes)
            if supplied_digest is not None and _digest("artifact.digest", supplied_digest) != computed_digest:
                _fail("DIGEST_MISMATCH", "artifact content digest does not match content")
            digest = computed_digest
            content_ref = candidate.get("content_ref", f"inline:{computed_digest}")
        else:
            if supplied_digest is None:
                _fail("CHILD_OUTPUT_INVALID", "artifact requires content or digest")
            digest = _digest("artifact.digest", supplied_digest)
            content_ref = candidate.get("content_ref")
            if content_ref is None:
                _fail("CHILD_OUTPUT_INVALID", "artifact with digest requires content_ref")
        artifact_id = candidate.get("artifact_id")
        if artifact_id is None:
            artifact_id = _derived_id("artifact", {"child_id": child_id, "digest": digest, "content_ref": content_ref})
        provenance = self._provenance(child_id, bindings)
        return NormalizedArtifact(
            artifact_id=artifact_id,
            content_ref=content_ref,
            media_type=candidate.get("media_type", "application/octet-stream"),
            digest=digest,
            provenance=provenance,
            schema_ref=candidate.get("schema_ref"),
            schema_version=candidate.get("schema_version"),
        )

    def _inline_artifact(
        self,
        content: str,
        child_id: str,
        bindings: Mapping[str, Any],
    ) -> NormalizedArtifact:
        digest = _sha256_bytes(content.encode("utf-8"))
        return NormalizedArtifact(
            artifact_id=_derived_id("artifact", {"child_id": child_id, "digest": digest}),
            content_ref=f"inline:{digest}",
            media_type="text/plain",
            digest=digest,
            provenance=self._provenance(child_id, bindings),
        )

    def _finding_from_mapping(
        self,
        value: Any,
        child_id: str,
        bindings: Mapping[str, Any],
    ) -> NormalizedFinding:
        candidate = _mapping(value, "finding")
        allowed = {
            "finding_id",
            "id",
            "severity",
            "category",
            "type",
            "lens",
            "claim",
            "message",
            "description",
            "evidence_refs",
            "evidence",
            "recommendation",
            "recommended_action",
            "reviewer",
            "confidence",
            "disposition",
            "conflict_group",
        }
        if sorted(set(candidate) - allowed):
            _fail("CHILD_OUTPUT_INVALID", "unsupported finding fields")
        _alias(candidate, "finding_id", ("id",))
        _alias(candidate, "category", ("type",))
        _alias(candidate, "claim", ("message", "description"))
        _alias(candidate, "evidence_refs", ("evidence",))
        _alias(candidate, "recommendation", ("recommended_action",))
        finding_id = candidate.get("finding_id")
        if finding_id is None:
            finding_id = _derived_id("finding", {key: candidate.get(key) for key in sorted(candidate) if key != "finding_id"})
        lens = candidate.get("lens") or bindings.get("lens")
        reviewer = candidate.get("reviewer") or bindings.get("reviewer") or child_id
        if lens is None or reviewer is None:
            _fail("CHILD_OUTPUT_INVALID", "finding requires lens and reviewer binding")
        return NormalizedFinding(
            finding_id=finding_id,
            severity=candidate.get("severity"),
            category=candidate.get("category"),
            lens=lens,
            claim=candidate.get("claim"),
            evidence_refs=candidate.get("evidence_refs"),
            recommendation=candidate.get("recommendation"),
            reviewer=reviewer,
            disposition=candidate.get("disposition", "OPEN"),
            confidence=candidate.get("confidence"),
            conflict_group=candidate.get("conflict_group"),
        )

    def _provenance(self, child_id: str, bindings: Mapping[str, Any]) -> dict[str, str]:
        result = {"child_id": child_id}
        for key in ("child_contract_digest", "source_digest", "lens", "reviewer"):
            value = bindings.get(key)
            if value is not None:
                result[key] = value
        return result

    def _safe_child_id(self, value: Any) -> str:
        try:
            return _identifier("child_id", value, MAX_CHILD_ID_LENGTH)
        except ChildResultNormalizationError:
            return "unknown-child"

    def _safe_bindings(self, bindings: Mapping[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"child_contract_digest": None, "source_digest": None, "lens": None, "reviewer": None}
        for name in result:
            value = bindings.get(name)
            if value is None:
                continue
            try:
                if name.endswith("digest"):
                    result[name] = _digest(name, value)
                elif name == "lens":
                    result[name] = _text(name, value, MAX_LENS_LENGTH)
                else:
                    result[name] = _text(name, value, MAX_REVIEWER_LENGTH)
            except ChildResultNormalizationError:
                pass
        return result

    def _failure_result(
        self,
        child_id: str,
        raw_digest: str | None,
        code: str,
        message: str,
        retryable: bool,
        bindings: Mapping[str, Any],
        *,
        status: NormalizationStatus = NormalizationStatus.NEEDS_RETRY,
    ) -> NormalizedChildResult:
        return NormalizedChildResult(
            child_id=child_id,
            status=status,
            raw_output_digest=raw_digest,
            failure=NormalizationFailure(code=code, message=message, retryable=retryable),
            child_contract_digest=bindings.get("child_contract_digest"),
            source_digest=bindings.get("source_digest"),
            lens=bindings.get("lens"),
            reviewer=bindings.get("reviewer"),
        )


__all__ = [
    "RESULT_NORMALIZER_PROTOCOL",
    "MAX_ARTIFACTS",
    "MAX_FINDINGS",
    "NormalizationStatus",
    "ChildResultNormalizationError",
    "NormalizationFailure",
    "NormalizedArtifact",
    "NormalizedFinding",
    "NormalizedChildResult",
    "ChildResultNormalizer",
]
