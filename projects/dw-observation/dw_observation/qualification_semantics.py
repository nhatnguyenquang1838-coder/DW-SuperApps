"""Semantic evidence candidate binding with fail-closed qualification.

This module validates candidate content integrity and source bindings, not
semantic truth or source authenticity. An independent source-artifact reader
is not yet available, so even a well-formed candidate remains UNKNOWN. Neither
caller-supplied PASS statuses nor self-computed digests establish qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .qualification_models import CheckStatus, QualificationCheck, QualificationSubject, subject_digest as _subject_digest

SEMANTIC_EVIDENCE_SCHEMA = "dwo.semantic-evidence/1"
SEMANTIC_CONTRACT_VERSION = "dwo.semantic-invariants/1"
REQUIRED_SEMANTIC_CHECKS = ("hierarchy", "lifecycle", "dependency-blocking", "authority-orthogonality")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class SemanticEvidence:
    schema_version: str
    source_repository: str
    source_sha: str
    projection_contract_version: str
    reducer_version: str
    subject_digest: str
    history_digest: str
    facts: dict[str, Any]
    evidence_content_digest: str
    contract_version: str = SEMANTIC_CONTRACT_VERSION

    def _content(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "contract_version": self.contract_version,
                "source_repository": self.source_repository, "source_sha": self.source_sha,
                "projection_contract_version": self.projection_contract_version,
                "reducer_version": self.reducer_version, "subject_digest": self.subject_digest,
                "history_digest": self.history_digest,
                "facts": self.facts}

    @classmethod
    def create(cls, *, source_repository: str, source_sha: str, projection_contract_version: str,
               reducer_version: str, subject_digest: str, history_digest: str, facts: dict[str, Any],
               contract_version: str = SEMANTIC_CONTRACT_VERSION) -> "SemanticEvidence":
        safe_facts = json.loads(_canonical(facts))
        evidence = cls(SEMANTIC_EVIDENCE_SCHEMA, source_repository, source_sha,
                       projection_contract_version, reducer_version, subject_digest,
                       history_digest, safe_facts, "", contract_version)
        return cls(**{**evidence.__dict__, "evidence_content_digest": _digest(evidence._content())})

    def to_dict(self) -> dict[str, Any]:
        return {**self._content(), "evidence_content_digest": self.evidence_content_digest}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticEvidence":
        expected = {"schema_version", "contract_version", "source_repository", "source_sha",
                    "projection_contract_version", "reducer_version", "subject_digest", "history_digest", "facts",
                    "evidence_content_digest"}
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError("semantic evidence fields mismatch")
        if data["schema_version"] != SEMANTIC_EVIDENCE_SCHEMA:
            raise ValueError("unsupported semantic evidence schema")
        return cls(**data)


def _check(check_id: str, status: CheckStatus, reason: str) -> QualificationCheck:
    return QualificationCheck(check_id, status, (f"evidence://semantic/{check_id}/{_digest(reason)}",))


def verify_semantic_evidence(evidence: SemanticEvidence | dict[str, Any] | None,
                             subject: QualificationSubject, prefix: Any) -> tuple[QualificationCheck, ...]:
    """Return UNKNOWN absent an independent source-artifact semantic reader.

    Content digests and caller assertions bind bytes; they do not authenticate
    the facts' origin or establish their relation to the run subject. This
    repository has no trusted producer/reader for those source artifacts yet.
    """
    reason = "SEMANTIC_SOURCE_VERIFIER_UNAVAILABLE"
    unknown = tuple(_check(name, CheckStatus.UNKNOWN, reason) for name in REQUIRED_SEMANTIC_CHECKS)
    if evidence is None:
        return unknown
    try:
        if isinstance(evidence, dict):
            evidence = SemanticEvidence.from_dict(evidence)
        if not isinstance(evidence, SemanticEvidence):
            return unknown
        if evidence.schema_version != SEMANTIC_EVIDENCE_SCHEMA or evidence.contract_version != SEMANTIC_CONTRACT_VERSION:
            return unknown
        if evidence.evidence_content_digest != _digest(evidence._content()):
            return unknown
        expected = (subject.source_repository, subject.source_sha, subject.projection_contract_version,
                    subject.reducer_version, _subject_digest(subject), prefix.history_digest)
        observed = (evidence.source_repository, evidence.source_sha, evidence.projection_contract_version,
                    evidence.reducer_version, evidence.subject_digest, evidence.history_digest)
        if observed != expected:
            return tuple(_check(name, CheckStatus.DRIFTED, "semantic evidence provenance mismatch") for name in REQUIRED_SEMANTIC_CHECKS)
        return unknown
    except (TypeError, ValueError, KeyError, AttributeError):
        return unknown
