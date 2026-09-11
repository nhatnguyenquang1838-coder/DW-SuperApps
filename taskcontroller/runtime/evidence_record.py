"""Canonical EvidenceRecord schema (M0 integration wave, designer M1/M2).

One typed, immutable evidence shape for certification so W5/W6/W7 stop each
defining their own ad-hoc ``evidence`` dict. Machine-readable AND
human-readable: expected/actual outputs may be structured or prose, and the
record carries exact plan/readback digests plus authority revalidation truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class EvidenceRecordError(ValueError):
    """Raised when an EvidenceRecord violates the schema contract."""


@dataclass(frozen=True)
class EvidenceRecord:
    """Immutable, schema-typed certification evidence for one plan step."""

    expected_output: Any = None
    actual_output: Any = None
    verdict_reason: str = ""
    authority_revalidated: bool = False
    readback_digest: str = ""
    plan_digest_at_execution: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.verdict_reason, str):
            raise EvidenceRecordError("verdict_reason must be a string")
        if not isinstance(self.authority_revalidated, bool):
            raise EvidenceRecordError("authority_revalidated must be a bool")
        if not isinstance(self.readback_digest, str):
            raise EvidenceRecordError("readback_digest must be a string")
        if not isinstance(self.plan_digest_at_execution, str):
            raise EvidenceRecordError("plan_digest_at_execution must be a string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_output": self.expected_output,
            "actual_output": self.actual_output,
            "verdict_reason": self.verdict_reason,
            "authority_revalidated": self.authority_revalidated,
            "readback_digest": self.readback_digest,
            "plan_digest_at_execution": self.plan_digest_at_execution,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceRecord":
        if not isinstance(payload, Mapping):
            raise EvidenceRecordError("evidence record payload must be an object")
        return cls(
            expected_output=payload.get("expected_output"),
            actual_output=payload.get("actual_output"),
            verdict_reason=payload.get("verdict_reason", ""),
            authority_revalidated=bool(payload.get("authority_revalidated", False)),
            readback_digest=payload.get("readback_digest", ""),
            plan_digest_at_execution=payload.get("plan_digest_at_execution", ""),
        )


__all__ = ["EvidenceRecord", "EvidenceRecordError"]
