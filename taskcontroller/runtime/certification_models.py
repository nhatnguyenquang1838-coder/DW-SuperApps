"""Immutable domain records for the Runtime Proving Lab.

The campaign aggregate may evolve in the harness, but terminal TestRun evidence
must be detached, recursively immutable, and reproducible from exact source and
execution identities. This module deliberately contains no Slack/Notion
integration.
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


def _require_digest(value: str, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_DIGEST.fullmatch(value) is None:
        raise CertificationModelError(f"{field_name} must be sha256:<64-hex>")
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


def _freeze_optional_refs(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in normalized):
        raise CertificationModelError(f"{field_name} must contain non-empty strings")
    return normalized


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        _plain(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    """Immutable proof that one TestRun represents one physical execution.

    SourceIdentity is intentionally allowed to repeat for stability replay, but
    ExecutionIdentity must be unique. The digest covers the complete execution
    receipt so copying the same receipt under another run ID is detectable.
    """

    execution_id: str
    started_at: str
    ended_at: str
    controller_seq_start: int
    controller_seq_end: int
    executor_seq_start: int
    executor_seq_end: int
    cursor_before: str
    cursor_after: str
    semantic_step_receipt_digests: tuple[str, ...]
    local_validation_receipts: tuple[str, ...] = ()
    github_workflow_receipts: tuple[Mapping[str, object], ...] = ()
    authority_receipt_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("execution_id", "started_at", "ended_at", "cursor_before", "cursor_after"):
            _require_text(getattr(self, field_name), field_name)
        for start_name, end_name in (
            ("controller_seq_start", "controller_seq_end"),
            ("executor_seq_start", "executor_seq_end"),
        ):
            start = getattr(self, start_name)
            end = getattr(self, end_name)
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or start < 0
                or not isinstance(end, int)
                or isinstance(end, bool)
                or end < start
            ):
                raise CertificationModelError(f"{start_name}/{end_name} must be monotonic non-negative integers")
        step_digests = _freeze_refs(
            self.semantic_step_receipt_digests, "semantic_step_receipt_digests"
        )
        for digest in step_digests:
            _require_digest(digest, "semantic_step_receipt_digest")
        object.__setattr__(self, "semantic_step_receipt_digests", step_digests)
        object.__setattr__(
            self,
            "local_validation_receipts",
            _freeze_optional_refs(self.local_validation_receipts, "local_validation_receipts"),
        )
        object.__setattr__(
            self,
            "authority_receipt_refs",
            _freeze_optional_refs(self.authority_receipt_refs, "authority_receipt_refs"),
        )
        workflows: list[Mapping[str, object]] = []
        for workflow in self.github_workflow_receipts:
            if not isinstance(workflow, Mapping):
                raise CertificationModelError("github_workflow_receipts must contain mappings")
            if "run_id" not in workflow or "run_attempt" not in workflow or "head_sha" not in workflow:
                raise CertificationModelError(
                    "github_workflow_receipt requires run_id, run_attempt and head_sha"
                )
            run_id = workflow["run_id"]
            run_attempt = workflow["run_attempt"]
            if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
                raise CertificationModelError("github workflow run_id must be a positive integer")
            if not isinstance(run_attempt, int) or isinstance(run_attempt, bool) or run_attempt < 1:
                raise CertificationModelError("github workflow run_attempt must be a positive integer")
            _require_sha(str(workflow["head_sha"]), "github workflow head_sha")
            workflows.append(_deep_freeze(dict(workflow)))
        object.__setattr__(self, "github_workflow_receipts", tuple(workflows))

    @property
    def execution_receipt_digest(self) -> str:
        return _canonical_digest(self._content_dict())

    def _content_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "controller_seq_start": self.controller_seq_start,
            "controller_seq_end": self.controller_seq_end,
            "executor_seq_start": self.executor_seq_start,
            "executor_seq_end": self.executor_seq_end,
            "cursor_before": self.cursor_before,
            "cursor_after": self.cursor_after,
            "semantic_step_receipt_digests": list(self.semantic_step_receipt_digests),
            "local_validation_receipts": list(self.local_validation_receipts),
            "github_workflow_receipts": [_plain(item) for item in self.github_workflow_receipts],
            "authority_receipt_refs": list(self.authority_receipt_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._content_dict()
        payload["execution_receipt_digest"] = self.execution_receipt_digest
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionReceipt":
        if not isinstance(payload, Mapping):
            raise CertificationModelError("execution_receipt must be a mapping")
        receipt = cls(
            execution_id=payload["execution_id"],
            started_at=payload["started_at"],
            ended_at=payload["ended_at"],
            controller_seq_start=payload["controller_seq_start"],
            controller_seq_end=payload["controller_seq_end"],
            executor_seq_start=payload["executor_seq_start"],
            executor_seq_end=payload["executor_seq_end"],
            cursor_before=payload["cursor_before"],
            cursor_after=payload["cursor_after"],
            semantic_step_receipt_digests=tuple(payload["semantic_step_receipt_digests"]),
            local_validation_receipts=tuple(payload.get("local_validation_receipts", ())),
            github_workflow_receipts=tuple(payload.get("github_workflow_receipts", ())),
            authority_receipt_refs=tuple(payload.get("authority_receipt_refs", ())),
        )
        supplied = payload.get("execution_receipt_digest")
        if supplied is not None and supplied != receipt.execution_receipt_digest:
            raise CertificationModelError("execution_receipt_digest does not match receipt content")
        return receipt


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
    legacy: bool = False
    blueprint_ref: str = ""
    blueprint_digest: str = ""
    harness_sha: str = ""
    execution_receipt: ExecutionReceipt | None = None

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
        object.__setattr__(self, "runtime_plan_digest", _require_digest(self.runtime_plan_digest, "runtime_plan_digest"))
        if self.blueprint_digest:
            object.__setattr__(self, "blueprint_digest", _require_digest(self.blueprint_digest, "blueprint_digest"))
        if self.blueprint_ref:
            _require_text(self.blueprint_ref, "blueprint_ref")
        if bool(self.blueprint_ref) != bool(self.blueprint_digest):
            raise CertificationModelError("blueprint_ref and blueprint_digest must be supplied together")
        object.__setattr__(self, "harness_sha", _require_sha(self.harness_sha or self.runtime.end_sha, "harness_sha"))
        if self.execution_receipt is not None and not isinstance(self.execution_receipt, ExecutionReceipt):
            raise CertificationModelError("execution_receipt must be an ExecutionReceipt")
        if self.verdict not in {"PENDING", "PASS", "FAIL"}:
            raise CertificationModelError(f"invalid verdict {self.verdict!r}")
        if not isinstance(self.evidence, Mapping):
            raise CertificationModelError("evidence must be a mapping")
        object.__setattr__(self, "evidence", _deep_freeze(dict(self.evidence)))

    @property
    def digest(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = {
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
            "blueprint_ref": self.blueprint_ref,
            "blueprint_digest": self.blueprint_digest,
            "harness_sha": self.harness_sha,
            "evidence": _plain(self.evidence),
        }
        if self.execution_receipt is not None:
            payload["execution_receipt"] = self.execution_receipt.to_dict()
        return payload


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
    "ExecutionReceipt",
    "RuntimeCorrection",
    "RuntimeFinding",
    "SourceRevision",
    "TestCase",
    "TestRun",
]
