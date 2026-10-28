"""Versioned, namespace-safe contracts for DWO LangGraph qualification.

These records are certification metadata, not DWO event history or runtime
authority. Their canonical JSON form is stable so receipt identities can be
replayed and compared across executions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable


SUBJECT_SCHEMA_VERSION = "dwo.qualification-subject/1"
EXECUTION_SCHEMA_VERSION = "dwo.qualification-execution/1"
RECEIPT_SCHEMA_VERSION = "dwo.qualification-receipt/1"
_SHA256_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _nonempty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{name} must not contain surrounding whitespace")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DwoRunId:
    """Identity in the DWO run namespace."""

    value: str

    def __post_init__(self) -> None:
        _nonempty(self.value, "dwo_run_id")


@dataclass(frozen=True)
class TaskRef:
    """Optional identity in the task/work-item namespace."""

    value: str

    def __post_init__(self) -> None:
        _nonempty(self.value, "task_ref")


@dataclass(frozen=True)
class QualificationId:
    """Identity in the qualification namespace; never a DWO run id."""

    value: str

    def __post_init__(self) -> None:
        _nonempty(self.value, "qualification_id")
        if not self.value.startswith("qualification:"):
            raise ValueError("qualification_id must use the 'qualification:' namespace")


@dataclass(frozen=True)
class LangGraphThreadId:
    """Identity in the LangGraph operational checkpoint namespace."""

    value: str

    def __post_init__(self) -> None:
        _nonempty(self.value, "langgraph_thread_id")
        if not self.value.startswith("langgraph:"):
            raise ValueError("langgraph_thread_id must use the 'langgraph:' namespace")


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    INTERRUPTED = "INTERRUPTED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    DRIFTED = "DRIFTED"
    UNKNOWN = "UNKNOWN"


class QualificationStatus(str, Enum):
    QUALIFIED = "QUALIFIED"
    FAILED = "FAILED"
    DRIFTED = "DRIFTED"
    UNKNOWN = "UNKNOWN"


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    DRIFTED = "DRIFTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class QualificationSubject:
    """Immutable versioned identity of the exact history being qualified."""

    dwo_run_id: DwoRunId
    task_ref: TaskRef | None
    source_repository: str
    source_sha: str
    lifecycle_profile: str
    projection_contract_version: str
    reducer_version: str
    durable_position: str
    schema_version: str = SUBJECT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SUBJECT_SCHEMA_VERSION:
            raise ValueError(f"unsupported QualificationSubject schema: {self.schema_version!r}")
        if not isinstance(self.dwo_run_id, DwoRunId):
            raise TypeError("dwo_run_id must be a DwoRunId, not another identifier namespace")
        if self.task_ref is not None and not isinstance(self.task_ref, TaskRef):
            raise TypeError("task_ref must be TaskRef or None")
        repository = _nonempty(self.source_repository, "source_repository")
        if repository.count("/") != 1 or any(not part for part in repository.split("/")):
            raise ValueError("source_repository must be owner/repository")
        if not isinstance(self.source_sha, str) or not _SHA256_RE.fullmatch(self.source_sha):
            raise ValueError("source_sha must be exactly 40 lowercase hexadecimal characters")
        _nonempty(self.lifecycle_profile, "lifecycle_profile")
        _nonempty(self.projection_contract_version, "projection_contract_version")
        _nonempty(self.reducer_version, "reducer_version")
        _nonempty(self.durable_position, "durable_position")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dwo_run_id": self.dwo_run_id.value,
            "task_ref": self.task_ref.value if self.task_ref is not None else None,
            "source_repository": self.source_repository,
            "source_sha": self.source_sha,
            "lifecycle_profile": self.lifecycle_profile,
            "projection_contract_version": self.projection_contract_version,
            "reducer_version": self.reducer_version,
            "durable_position": self.durable_position,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualificationSubject":
        expected = {
            "schema_version", "dwo_run_id", "task_ref", "source_repository",
            "source_sha", "lifecycle_profile", "projection_contract_version",
            "reducer_version", "durable_position",
        }
        if set(data) != expected:
            raise ValueError(f"QualificationSubject fields mismatch: {sorted(set(data) ^ expected)}")
        task = data["task_ref"]
        return cls(
            schema_version=data["schema_version"],
            dwo_run_id=DwoRunId(data["dwo_run_id"]),
            task_ref=TaskRef(task) if task is not None else None,
            source_repository=data["source_repository"],
            source_sha=data["source_sha"],
            lifecycle_profile=data["lifecycle_profile"],
            projection_contract_version=data["projection_contract_version"],
            reducer_version=data["reducer_version"],
            durable_position=data["durable_position"],
        )


def subject_digest(subject: QualificationSubject) -> str:
    """Canonical digest over every subject binding, including durable position."""
    return _digest(subject.to_dict())


def _qualification_id_for_digest(digest: str, graph_version: str) -> QualificationId:
    if not _DIGEST_RE.fullmatch(digest):
        raise ValueError("subject_digest must be sha256:<64 lowercase hexadecimal characters>")
    _nonempty(graph_version, "graph_version")
    derived = _digest({"subject_digest": digest, "graph_version": graph_version})
    return QualificationId(f"qualification:{derived.removeprefix('sha256:')}")


@dataclass(frozen=True)
class QualificationExecution:
    """Operational execution identity/status; not the certification receipt."""

    qualification_id: QualificationId
    subject_digest: str
    langgraph_thread_id: LangGraphThreadId
    graph_version: str
    status: ExecutionStatus
    evidence_refs: tuple[str, ...] = ()
    receipt_ref: str | None = None
    schema_version: str = EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXECUTION_SCHEMA_VERSION:
            raise ValueError(f"unsupported QualificationExecution schema: {self.schema_version!r}")
        if not isinstance(self.qualification_id, QualificationId):
            raise TypeError("qualification_id must be a QualificationId")
        if not isinstance(self.langgraph_thread_id, LangGraphThreadId):
            raise TypeError("langgraph_thread_id must be a LangGraphThreadId")
        if not _DIGEST_RE.fullmatch(self.subject_digest):
            raise ValueError("subject_digest must be sha256:<64 lowercase hexadecimal characters>")
        _nonempty(self.graph_version, "graph_version")
        if self.qualification_id != _qualification_id_for_digest(self.subject_digest, self.graph_version):
            raise ValueError("qualification_id is not bound to subject_digest and graph_version")
        if not isinstance(self.status, ExecutionStatus):
            object.__setattr__(self, "status", ExecutionStatus(self.status))
        refs = tuple(sorted({_nonempty(ref, "evidence_ref") for ref in self.evidence_refs}))
        object.__setattr__(self, "evidence_refs", refs)
        if self.receipt_ref is not None:
            _nonempty(self.receipt_ref, "receipt_ref")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "qualification_id": self.qualification_id.value,
            "subject_digest": self.subject_digest,
            "langgraph_thread_id": self.langgraph_thread_id.value,
            "graph_version": self.graph_version,
            "status": self.status.value,
            "evidence_refs": list(self.evidence_refs),
            "receipt_ref": self.receipt_ref,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualificationExecution":
        expected = {
            "schema_version", "qualification_id", "subject_digest", "langgraph_thread_id",
            "graph_version", "status", "evidence_refs", "receipt_ref",
        }
        if set(data) != expected:
            raise ValueError(f"QualificationExecution fields mismatch: {sorted(set(data) ^ expected)}")
        return cls(
            schema_version=data["schema_version"],
            qualification_id=QualificationId(data["qualification_id"]),
            subject_digest=data["subject_digest"],
            langgraph_thread_id=LangGraphThreadId(data["langgraph_thread_id"]),
            graph_version=data["graph_version"],
            status=ExecutionStatus(data["status"]),
            evidence_refs=tuple(data["evidence_refs"]),
            receipt_ref=data["receipt_ref"],
        )


@dataclass(frozen=True)
class QualificationCheck:
    check_id: str
    status: CheckStatus
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.check_id, "check_id")
        if not isinstance(self.status, CheckStatus):
            object.__setattr__(self, "status", CheckStatus(self.status))
        refs = tuple(sorted({_nonempty(ref, "evidence_ref") for ref in self.evidence_refs}))
        object.__setattr__(self, "evidence_refs", refs)
        if self.status is CheckStatus.PASS and not refs:
            raise ValueError("a passing qualification check requires evidence_refs")

    def to_dict(self) -> dict[str, Any]:
        return {"check_id": self.check_id, "status": self.status.value, "evidence_refs": list(self.evidence_refs)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualificationCheck":
        if set(data) != {"check_id", "status", "evidence_refs"}:
            raise ValueError("QualificationCheck fields mismatch")
        return cls(data["check_id"], CheckStatus(data["status"]), tuple(data["evidence_refs"]))


@dataclass(frozen=True)
class QualificationReceipt:
    """Immutable derived certification; never an authority or event-store write."""

    receipt_id: str
    qualification_id: QualificationId
    subject: QualificationSubject
    subject_digest: str
    graph_version: str
    status: QualificationStatus
    checks: tuple[QualificationCheck, ...]
    evidence_refs: tuple[str, ...]
    authority_granted: bool = False
    projection_events_mutated: bool = False
    schema_version: str = RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"unsupported QualificationReceipt schema: {self.schema_version!r}")
        _nonempty(self.receipt_id, "receipt_id")
        if not isinstance(self.qualification_id, QualificationId):
            raise TypeError("qualification_id must be a QualificationId")
        if not isinstance(self.subject, QualificationSubject):
            raise TypeError("subject must be QualificationSubject")
        if self.subject_digest != subject_digest(self.subject):
            raise ValueError("receipt subject_digest does not match the immutable subject")
        _nonempty(self.graph_version, "graph_version")
        if self.qualification_id != _qualification_id_for_digest(self.subject_digest, self.graph_version):
            raise ValueError("qualification_id is not bound to receipt subject_digest and graph_version")
        if not isinstance(self.status, QualificationStatus):
            object.__setattr__(self, "status", QualificationStatus(self.status))
        if self.authority_granted is not False:
            raise ValueError("qualification receipts cannot grant authority")
        if self.projection_events_mutated is not False:
            raise ValueError("qualification receipts cannot mutate projection_events")
        checks = tuple(sorted(self.checks, key=lambda check: check.check_id))
        object.__setattr__(self, "checks", checks)
        refs = tuple(sorted({_nonempty(ref, "evidence_ref") for ref in self.evidence_refs}))
        object.__setattr__(self, "evidence_refs", refs)
        if self.status is QualificationStatus.QUALIFIED:
            if not checks or any(check.status is not CheckStatus.PASS for check in checks):
                raise ValueError("QUALIFIED requires a non-empty all-PASS check set")
            if not refs:
                raise ValueError("QUALIFIED requires evidence_refs")
        expected_receipt_id = f"receipt:{self.receipt_digest.removeprefix('sha256:')}"
        if self.receipt_id != expected_receipt_id:
            raise ValueError("receipt_id is not bound to canonical receipt content")

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "qualification_id": self.qualification_id.value,
            "subject": self.subject.to_dict(),
            "subject_digest": self.subject_digest,
            "graph_version": self.graph_version,
            "status": self.status.value,
            "checks": [check.to_dict() for check in self.checks],
            "evidence_refs": list(self.evidence_refs),
            "authority_granted": False,
            "projection_events_mutated": False,
        }

    @property
    def receipt_digest(self) -> str:
        return _digest(self._content_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._content_dict(),
            "receipt_id": self.receipt_id,
            "receipt_digest": self.receipt_digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualificationReceipt":
        expected = {
            "schema_version", "receipt_id", "qualification_id", "subject", "subject_digest",
            "graph_version", "status", "checks", "evidence_refs", "authority_granted",
            "projection_events_mutated", "receipt_digest",
        }
        if set(data) != expected:
            raise ValueError(f"QualificationReceipt fields mismatch: {sorted(set(data) ^ expected)}")
        receipt = cls(
            schema_version=data["schema_version"],
            receipt_id=data["receipt_id"],
            qualification_id=QualificationId(data["qualification_id"]),
            subject=QualificationSubject.from_dict(data["subject"]),
            subject_digest=data["subject_digest"],
            graph_version=data["graph_version"],
            status=QualificationStatus(data["status"]),
            checks=tuple(QualificationCheck.from_dict(check) for check in data["checks"]),
            evidence_refs=tuple(data["evidence_refs"]),
            authority_granted=data["authority_granted"],
            projection_events_mutated=data["projection_events_mutated"],
        )
        if data["receipt_digest"] != receipt.receipt_digest:
            raise ValueError("receipt_digest does not match canonical receipt content")
        if data["receipt_id"] != f"receipt:{receipt.receipt_digest.removeprefix('sha256:')}" :
            raise ValueError("receipt_id does not match canonical receipt content")
        return receipt


def create_qualification_id(subject: QualificationSubject, graph_version: str) -> QualificationId:
    return _qualification_id_for_digest(subject_digest(subject), graph_version)


def create_qualification_receipt(
    subject: QualificationSubject,
    graph_version: str,
    status: QualificationStatus,
    checks: Iterable[QualificationCheck],
) -> QualificationReceipt:
    ordered_checks = tuple(sorted(checks, key=lambda check: check.check_id))
    evidence_refs = tuple(sorted({ref for check in ordered_checks for ref in check.evidence_refs}))
    qualification_id = create_qualification_id(subject, graph_version)
    normalized_status = QualificationStatus(status)
    subject_hash = subject_digest(subject)
    content = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "qualification_id": qualification_id.value,
        "subject": subject.to_dict(),
        "subject_digest": subject_hash,
        "graph_version": graph_version,
        "status": normalized_status.value,
        "checks": [check.to_dict() for check in ordered_checks],
        "evidence_refs": list(evidence_refs),
        "authority_granted": False,
        "projection_events_mutated": False,
    }
    receipt_digest = _digest(content)
    return QualificationReceipt(
        receipt_id=f"receipt:{receipt_digest.removeprefix('sha256:')}",
        qualification_id=qualification_id,
        subject=subject,
        subject_digest=subject_hash,
        graph_version=graph_version,
        status=normalized_status,
        checks=ordered_checks,
        evidence_refs=evidence_refs,
    )
