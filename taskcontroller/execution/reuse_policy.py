"""Deterministic reusable-child evidence policy for takeover recovery.

This module is intentionally provider-neutral and side-effect free.  It decides
whether a terminal child result may be rebound to a newer lease generation;
it does not mutate a manifest, dispatch work, or advance controller state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class ReusePolicy(str, Enum):
    """Policy recorded by both the source evidence and takeover target."""

    REUSE_IF_COMPATIBLE = "REUSE_IF_COMPATIBLE"
    RERUN_REQUIRED = "RERUN_REQUIRED"


class ReuseDisposition(str, Enum):
    """The only two outcomes of the reusable-evidence decision."""

    REUSE = "REUSE"
    RERUN = "RERUN"


_ALLOWED_STATUSES = frozenset(
    {
        "PLANNED",
        "CREATED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "TIMED_OUT",
        "CANCELLED",
        "STALE",
    }
)


def _policy_value(value: ReusePolicy | str) -> ReusePolicy:
    try:
        return value if isinstance(value, ReusePolicy) else ReusePolicy(value)
    except ValueError as exc:
        raise ValueError(f"unknown child evidence reuse policy: {value!r}") from exc


def _status_value(value: Any) -> str:
    candidate = getattr(value, "value", value)
    if not isinstance(candidate, str) or candidate not in _ALLOWED_STATUSES:
        raise ValueError(f"unknown child evidence status: {value!r}")
    return candidate


def _required_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class ChildEvidenceRecord:
    """Immutable evidence identity used as source or takeover target context."""

    child_id: str
    child_contract_digest: str
    parent_contract_id: str
    parent_contract_digest: str
    plan_version: str
    source_digest: str
    standards_digest: str
    parent_attempt_id: str
    lease_generation: int
    status: str
    result_ref: str | None
    result_digest: str | None
    reuse_policy: ReusePolicy | str

    def __post_init__(self) -> None:
        for name in (
            "child_id",
            "child_contract_digest",
            "parent_contract_id",
            "parent_contract_digest",
            "plan_version",
            "source_digest",
            "standards_digest",
            "parent_attempt_id",
        ):
            _required_text(name, getattr(self, name))

        if isinstance(self.lease_generation, bool) or not isinstance(
            self.lease_generation, int
        ):
            raise ValueError("lease_generation must be an integer")
        if self.lease_generation < 0:
            raise ValueError("lease_generation must be non-negative")

        if self.result_ref is not None:
            _required_text("result_ref", self.result_ref)
        if self.result_digest is not None:
            _required_text("result_digest", self.result_digest)

        object.__setattr__(self, "status", _status_value(self.status))
        object.__setattr__(self, "reuse_policy", _policy_value(self.reuse_policy))

    def to_dict(self) -> dict[str, Any]:
        """Return a stable, JSON-compatible representation."""

        return {
            "child_id": self.child_id,
            "child_contract_digest": self.child_contract_digest,
            "parent_contract_id": self.parent_contract_id,
            "parent_contract_digest": self.parent_contract_digest,
            "plan_version": self.plan_version,
            "source_digest": self.source_digest,
            "standards_digest": self.standards_digest,
            "parent_attempt_id": self.parent_attempt_id,
            "lease_generation": self.lease_generation,
            "status": self.status,
            "result_ref": self.result_ref,
            "result_digest": self.result_digest,
            "reuse_policy": ReusePolicy(self.reuse_policy).value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChildEvidenceRecord":
        """Decode a complete record; missing policy never defaults to reuse."""

        if not isinstance(payload, Mapping):
            raise TypeError("child evidence record must be a mapping")
        return cls(
            child_id=payload["child_id"],
            child_contract_digest=payload["child_contract_digest"],
            parent_contract_id=payload["parent_contract_id"],
            parent_contract_digest=payload["parent_contract_digest"],
            plan_version=payload["plan_version"],
            source_digest=payload["source_digest"],
            standards_digest=payload["standards_digest"],
            parent_attempt_id=payload["parent_attempt_id"],
            lease_generation=payload["lease_generation"],
            status=payload["status"],
            result_ref=payload["result_ref"],
            result_digest=payload["result_digest"],
            reuse_policy=payload["reuse_policy"],
        )


@dataclass(frozen=True, slots=True)
class ChildEvidenceReuseDecision:
    """Deterministic decision and evidence refs for a takeover candidate."""

    child_id: str
    disposition: ReuseDisposition
    failed_checks: tuple[str, ...]
    reused_result_ref: str | None = None
    reused_result_digest: str | None = None

    def __post_init__(self) -> None:
        _required_text("child_id", self.child_id)
        disposition = (
            self.disposition
            if isinstance(self.disposition, ReuseDisposition)
            else ReuseDisposition(self.disposition)
        )
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(self, "failed_checks", tuple(self.failed_checks))

        if disposition is ReuseDisposition.REUSE:
            if self.failed_checks:
                raise ValueError("REUSE cannot contain failed checks")
            _required_text("reused_result_ref", self.reused_result_ref)
            _required_text("reused_result_digest", self.reused_result_digest)
        elif self.reused_result_ref is not None or self.reused_result_digest is not None:
            raise ValueError("RERUN cannot carry reusable result evidence")
        if disposition is ReuseDisposition.RERUN and not self.failed_checks:
            raise ValueError("RERUN must identify at least one failed check")

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "disposition": self.disposition.value,
            "failed_checks": list(self.failed_checks),
            "reused_result_ref": self.reused_result_ref,
            "reused_result_digest": self.reused_result_digest,
        }


def evaluate_child_evidence_reuse(
    prior: ChildEvidenceRecord,
    target: ChildEvidenceRecord,
) -> ChildEvidenceReuseDecision:
    """Decide whether ``prior`` may be reused by ``target`` after takeover.

    The target must represent the same logical parent attempt at a strictly
    newer lease generation.  All semantic bindings are compared explicitly;
    any mismatch produces ``RERUN`` and never returns prior result evidence.
    """

    failed_checks: list[str] = []

    if prior.child_id != target.child_id:
        failed_checks.append("child_id")
    if prior.child_contract_digest != target.child_contract_digest:
        failed_checks.append("child_contract_digest")
    if prior.parent_contract_id != target.parent_contract_id:
        failed_checks.append("parent_contract_id")
    if prior.parent_contract_digest != target.parent_contract_digest:
        failed_checks.append("parent_contract_digest")
    if prior.plan_version != target.plan_version:
        failed_checks.append("plan_version")
    if prior.source_digest != target.source_digest:
        failed_checks.append("source_digest")
    if prior.standards_digest != target.standards_digest:
        failed_checks.append("standards_digest")
    if prior.reuse_policy is not target.reuse_policy or (
        prior.reuse_policy is not ReusePolicy.REUSE_IF_COMPATIBLE
    ):
        failed_checks.append("reuse_policy")
    if prior.parent_attempt_id != target.parent_attempt_id:
        failed_checks.append("parent_attempt_id")
    if target.lease_generation <= prior.lease_generation:
        failed_checks.append("lease_generation")
    if prior.status != "SUCCEEDED":
        failed_checks.append("status")
    if prior.result_ref is None:
        failed_checks.append("result_ref")
    if prior.result_digest is None:
        failed_checks.append("result_digest")

    if failed_checks:
        return ChildEvidenceReuseDecision(
            child_id=target.child_id,
            disposition=ReuseDisposition.RERUN,
            failed_checks=tuple(failed_checks),
        )

    return ChildEvidenceReuseDecision(
        child_id=target.child_id,
        disposition=ReuseDisposition.REUSE,
        failed_checks=(),
        reused_result_ref=prior.result_ref,
        reused_result_digest=prior.result_digest,
    )


__all__ = [
    "ChildEvidenceRecord",
    "ChildEvidenceReuseDecision",
    "ReuseDisposition",
    "ReusePolicy",
    "evaluate_child_evidence_reuse",
]
