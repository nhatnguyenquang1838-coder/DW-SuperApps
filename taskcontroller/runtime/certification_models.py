"""Immutable domain records for the Runtime Proving Lab.

The campaign aggregate may evolve in the harness, but terminal TestRun evidence
must be detached, recursively immutable, and reproducible from exact source
identities.  This module deliberately contains no Slack/Notion integration.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


_SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_DIGEST_ONLY = re.compile(r"^[0-9a-fA-F]{64}$")


def _require_sha256_digest(value: str, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_DIGEST.fullmatch(value) is None:
        raise CertificationModelError(f"{field_name} must be sha256:<64-hex>")
    return value.lower()


class CertificationModelError(ValueError):
    """Raised when a certification record violates its domain contract."""


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CertificationModelError(f"{field_name} is required")
    return value


def _require_sha(value: str, field_name: str) -> str:
    if not isinstance(value, str) or _SHA40.fullmatch(value) is None:
        raise CertificationModelError(f"{field_name} must be an exact 40-hex SHA")
    return value.lower()


def _deep_freeze(value: Any) -> Any:
    """Copy and recursively freeze JSON-shaped values."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    """Return detached JSON-compatible data from a frozen value."""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_plain(item) for item in value]
    return value


def _freeze_refs(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if not normalized or any(not isinstance(value, str) or not value.strip() for value in normalized):
        raise CertificationModelError(f"{field_name} is required")
    return normalized


def _freeze_tuple(values: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(_deep_freeze(item) for item in values)


@dataclass(frozen=True)
class SourceRevision:
    repository: str
    branch: str
    start_sha: str
    end_sha: str

    def __post_init__(self) -> None:
        _require_text(self.repository, "repository")
        _require_text(self.branch, "branch")
        object.__setattr__(self, "start_sha", _require_sha(self.start_sha, "start_sha"))
        object.__setattr__(self, "end_sha", _require_sha(self.end_sha, "end_sha"))

    def to_dict(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "branch": self.branch,
            "start_sha": self.start_sha,
            "end_sha": self.end_sha,
        }


@dataclass(frozen=True)
class TestCase:
    case_id: str
    revision: str
    scenario: str
    acceptance: str
    declared_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.case_id, "case_id")
        _require_text(self.revision, "revision")
        _require_text(self.scenario, "scenario")
        _require_text(self.acceptance, "acceptance")
        object.__setattr__(self, "declared_paths", _freeze_refs(self.declared_paths, "declared_paths"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "revision": self.revision,
            "scenario": self.scenario,
            "acceptance": self.acceptance,
            "declared_paths": list(self.declared_paths),
        }


@dataclass(frozen=True)
class CertificationCampaign:
    campaign_id: str
    mode: str
    runtime_branch: str
    proving_branch: str
    test_case_id: str
    test_case_revision: str
    baseline_runtime_sha: str
    baseline_subject_sha: str
    gwc_sha: str
    status: str

    def __post_init__(self) -> None:
        for field_name in (
            "campaign_id",
            "mode",
            "runtime_branch",
            "proving_branch",
            "test_case_id",
            "test_case_revision",
            "status",
        ):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(self, "baseline_runtime_sha", _require_sha(self.baseline_runtime_sha, "baseline_runtime_sha"))
        object.__setattr__(self, "baseline_subject_sha", _require_sha(self.baseline_subject_sha, "baseline_subject_sha"))
        object.__setattr__(self, "gwc_sha", _require_sha(self.gwc_sha, "gwc_sha"))

    def to_dict(self) -> dict[str, str]:
        return {
            "campaign_id": self.campaign_id,
            "mode": self.mode,
            "runtime_branch": self.runtime_branch,
            "proving_branch": self.proving_branch,
            "test_case_id": self.test_case_id,
            "test_case_revision": self.test_case_revision,
            "baseline_runtime_sha": self.baseline_runtime_sha,
            "baseline_subject_sha": self.baseline_subject_sha,
            "gwc_sha": self.gwc_sha,
            "status": self.status,
        }


@dataclass(frozen=True)
class ExecutionReceipt:
    """Deeply immutable evidence that one independent execution occurred.

    SourceIdentity MAY repeat across TestRuns; ExecutionIdentity (execution_id
    and execution_receipt_digest) MUST be unique per TestRun. When
    ``harness_is_runtime`` is true, the exact harness/revision that executed
    and scored the run must equal the recorded runtime revision.
    """

    execution_id: str
    started_at: str
    completed_at: str
    controller_seq_start: int
    controller_seq_end: int
    executor_seq_start: int
    executor_seq_end: int
    cursor_before: str
    cursor_after: str
    step_receipt_digests: tuple[str, ...]
    local_validation_receipts: tuple[str, ...]
    ci_run_refs: tuple[tuple[str, str, str, str, str], ...]
    authority_refs: tuple[str, ...]
    harness_sha: str
    harness_is_runtime: bool
    execution_receipt_digest: str

    def __post_init__(self) -> None:
        for field_name in (
            "execution_id",
            "started_at",
            "completed_at",
            "cursor_before",
            "cursor_after",
        ):
            _require_text(getattr(self, field_name), field_name)
        for field_name in (
            "controller_seq_start",
            "controller_seq_end",
            "executor_seq_start",
            "executor_seq_end",
        ):
            if not isinstance(getattr(self, field_name), int) or getattr(self, field_name) < 0:
                raise CertificationModelError(f"{field_name} must be a non-negative integer")
        object.__setattr__(self, "step_receipt_digests", _freeze_tuple(self.step_receipt_digests))
        object.__setattr__(self, "local_validation_receipts", _freeze_tuple(self.local_validation_receipts))
        object.__setattr__(self, "authority_refs", _freeze_tuple(self.authority_refs))
        object.__setattr__(self, "harness_sha", _require_sha(self.harness_sha, "harness_sha"))
        object.__setattr__(
            self,
            "execution_receipt_digest",
            _require_sha256_digest(self.execution_receipt_digest, "execution_receipt_digest"),
        )
        if not isinstance(self.harness_is_runtime, bool):
            raise CertificationModelError("harness_is_runtime must be a boolean")
        normalized_ci = tuple(
            (str(run_id), str(attempt), str(head_sha), str(conclusion), str(workflow))
            for run_id, attempt, head_sha, conclusion, workflow in self.ci_run_refs
        )
        object.__setattr__(self, "ci_run_refs", normalized_ci)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "controller_seq_start": self.controller_seq_start,
            "controller_seq_end": self.controller_seq_end,
            "executor_seq_start": self.executor_seq_start,
            "executor_seq_end": self.executor_seq_end,
            "cursor_before": self.cursor_before,
            "cursor_after": self.cursor_after,
            "step_receipt_digests": list(self.step_receipt_digests),
            "local_validation_receipts": list(self.local_validation_receipts),
            "ci_run_refs": [list(item) for item in self.ci_run_refs],
            "authority_refs": list(self.authority_refs),
            "harness_sha": self.harness_sha,
            "harness_is_runtime": self.harness_is_runtime,
            "execution_receipt_digest": self.execution_receipt_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionReceipt":
        return cls(
            execution_id=str(payload["execution_id"]),
            started_at=str(payload["started_at"]),
            completed_at=str(payload["completed_at"]),
            controller_seq_start=int(payload["controller_seq_start"]),
            controller_seq_end=int(payload["controller_seq_end"]),
            executor_seq_start=int(payload["executor_seq_start"]),
            executor_seq_end=int(payload["executor_seq_end"]),
            cursor_before=str(payload["cursor_before"]),
            cursor_after=str(payload["cursor_after"]),
            step_receipt_digests=tuple(payload["step_receipt_digests"]),
            local_validation_receipts=tuple(payload["local_validation_receipts"]),
            ci_run_refs=tuple(tuple(item) for item in payload.get("ci_run_refs", [])),
            authority_refs=tuple(payload["authority_refs"]),
            harness_sha=str(payload["harness_sha"]),
            harness_is_runtime=bool(payload["harness_is_runtime"]),
            execution_receipt_digest=str(payload["execution_receipt_digest"]),
        )


@dataclass(frozen=True)
class TestRun:
    run_id: str
    campaign_id: str
    case_id: str
    case_revision: str
    runtime: SourceRevision
    subject: SourceRevision
    gwc_sha: str
    runtime_plan_ref: str
    runtime_plan_revision: str
    runtime_plan_digest: str
    executor: str
    model: str
    verdict: str
    evidence: Mapping[str, object] = field(default_factory=dict)
    execution: ExecutionReceipt | None = None
    legacy: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "campaign_id",
            "case_id",
            "case_revision",
            "runtime_plan_ref",
            "runtime_plan_revision",
            "executor",
            "model",
            "verdict",
        ):
            _require_text(getattr(self, field_name), field_name)
        if not isinstance(self.runtime, SourceRevision) or not isinstance(self.subject, SourceRevision):
            raise CertificationModelError("runtime and subject SourceRevision records are required")
        object.__setattr__(self, "gwc_sha", _require_sha(self.gwc_sha, "gwc_sha"))
        if _SHA256_DIGEST.fullmatch(self.runtime_plan_digest) is None:
            raise CertificationModelError("runtime_plan_digest must be sha256:<64-hex>")
        if self.verdict not in {"PENDING", "PASS", "FAIL"}:
            raise CertificationModelError(f"invalid verdict {self.verdict!r}")
        if not isinstance(self.evidence, Mapping):
            raise CertificationModelError("evidence must be a mapping")
        object.__setattr__(self, "evidence", _deep_freeze(dict(self.evidence)))
        if self.execution is None:
            if not self.legacy:
                raise CertificationModelError("execution identity (ExecutionReceipt) is required")
            object.__setattr__(
                self,
                "execution",
                ExecutionReceipt(
                    execution_id=f"legacy-{self.run_id}",
                    started_at="legacy",
                    completed_at="legacy",
                    controller_seq_start=0,
                    controller_seq_end=0,
                    executor_seq_start=0,
                    executor_seq_end=0,
                    cursor_before="legacy",
                    cursor_after="legacy",
                    step_receipt_digests=("legacy://" + self.run_id,),
                    local_validation_receipts=(),
                    ci_run_refs=(),
                    authority_refs=(),
                    harness_sha=self.runtime.end_sha,
                    harness_is_runtime=False,
                    execution_receipt_digest=_require_sha256_digest(
                        "sha256:" + hashlib.sha256(f"legacy:{self.run_id}".encode()).hexdigest(),
                        "execution_receipt_digest",
                    ),
                ),
            )
        if not isinstance(self.execution, ExecutionReceipt):
            raise CertificationModelError("execution must be an ExecutionReceipt")
        if self.execution.harness_is_runtime and self.execution.harness_sha != self.runtime.end_sha:
            raise CertificationModelError(
                "runtime/harness self-hosting mismatch: harness_sha "
                f"{self.execution.harness_sha} != recorded runtime {self.runtime.end_sha}"
            )

    @property
    def digest(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "campaign_id": self.campaign_id,
            "case_id": self.case_id,
            "case_revision": self.case_revision,
            "runtime": self.runtime.to_dict(),
            "subject": self.subject.to_dict(),
            "gwc_sha": self.gwc_sha,
            "runtime_plan_ref": self.runtime_plan_ref,
            "runtime_plan_revision": self.runtime_plan_revision,
            "runtime_plan_digest": self.runtime_plan_digest,
            "executor": self.executor,
            "model": self.model,
            "verdict": self.verdict,
            "legacy": self.legacy,
            "execution": self.execution.to_dict() if self.execution is not None else None,
            "evidence": _plain(self.evidence),
        }


@dataclass(frozen=True)
class RuntimeFinding:
    finding_id: str
    campaign_id: str
    discovered_by_run_id: str
    invariant_id: str
    severity: str
    expected: str
    actual: str
    reproduction_refs: tuple[str, ...]
    status: str
    correction_id: str = ""
    correction_sha: str = ""
    regression_evidence: tuple[str, ...] = ()
    successor_run_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "finding_id",
            "campaign_id",
            "discovered_by_run_id",
            "invariant_id",
            "severity",
            "expected",
            "actual",
            "status",
        ):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(self, "reproduction_refs", _freeze_refs(self.reproduction_refs, "reproduction_refs"))
        object.__setattr__(self, "regression_evidence", tuple(self.regression_evidence))
        object.__setattr__(self, "successor_run_ids", tuple(self.successor_run_ids))
        if self.status.upper() == "RESOLVED":
            if not self.correction_id or not self.correction_sha or not self.regression_evidence or not self.successor_run_ids:
                raise CertificationModelError("resolved finding requires RuntimeCorrection evidence")
            _require_sha(self.correction_sha, "correction_sha")

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "campaign_id": self.campaign_id,
            "discovered_by_run_id": self.discovered_by_run_id,
            "invariant_id": self.invariant_id,
            "severity": self.severity,
            "expected": self.expected,
            "actual": self.actual,
            "reproduction_refs": list(self.reproduction_refs),
            "status": self.status,
            "correction_id": self.correction_id,
            "correction_sha": self.correction_sha,
            "regression_evidence": list(self.regression_evidence),
            "successor_run_ids": list(self.successor_run_ids),
        }


@dataclass(frozen=True)
class RuntimeCorrection:
    correction_id: str
    finding_ids: tuple[str, ...]
    runtime_sha: str
    regression_evidence: tuple[str, ...]
    successor_run_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.correction_id, "correction_id")
        object.__setattr__(self, "finding_ids", _freeze_refs(self.finding_ids, "finding_ids"))
        object.__setattr__(self, "runtime_sha", _require_sha(self.runtime_sha, "runtime_sha"))
        object.__setattr__(self, "regression_evidence", _freeze_refs(self.regression_evidence, "regression_evidence"))
        object.__setattr__(self, "successor_run_ids", _freeze_refs(self.successor_run_ids, "successor_run_ids"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "correction_id": self.correction_id,
            "finding_ids": list(self.finding_ids),
            "runtime_sha": self.runtime_sha,
            "regression_evidence": list(self.regression_evidence),
            "successor_run_ids": list(self.successor_run_ids),
        }


__all__ = [
    "CertificationCampaign",
    "CertificationModelError",
    "RuntimeCorrection",
    "RuntimeFinding",
    "SourceRevision",
    "TestCase",
    "TestRun",
]
