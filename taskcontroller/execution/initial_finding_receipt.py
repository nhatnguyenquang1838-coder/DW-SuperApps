"""TC-MBX-602: immutable initial-finding receipts and cross-review gate.

The module is a provider-neutral evidence boundary.  It materializes one
canonical receipt per already-bound ReviewerSession and an append-only immutable
ledger snapshot.  It does not write a mailbox, invoke a provider, or activate
cross-review runtime behavior.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
import re
from typing import Any, cast

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.standards.reviewer_session import (
    INITIAL_FIRST_PASS,
    REVIEWER_SESSION_PROTOCOL,
    ReviewerSession,
)


INITIAL_FINDING_RECEIPT_PROTOCOL = "dw.taskcontroller.initial-finding-receipt/v1"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_MAX_IDENTIFIER_LENGTH = 128


class InitialFindingReceiptError(TaskControllerValidationError):
    """Stable fail-closed error for receipt or ledger validation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


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
        raise InitialFindingReceiptError(
            "RECEIPT_NOT_SERIALIZABLE",
            f"receipt payload is not canonical JSON: {type(exc).__name__}",
        ) from exc


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identifier(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_IDENTIFIER_LENGTH
        or not _IDENTIFIER_RE.fullmatch(value)
    ):
        raise InitialFindingReceiptError(
            "RECEIPT_INVALID",
            f"{field} must be a stable identifier of at most {_MAX_IDENTIFIER_LENGTH} characters",
        )
    return value


def _digest_field(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise InitialFindingReceiptError(
            "RECEIPT_INVALID",
            f"{field} must be sha256:<64 lowercase hex>",
        )
    return value


def _recorded_at(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InitialFindingReceiptError(
            "RECEIPT_TIMESTAMP_INVALID",
            "recorded_at must be an ISO-8601 timestamp with timezone",
        )
    normalized = value.strip()
    candidate = normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise InitialFindingReceiptError(
            "RECEIPT_TIMESTAMP_INVALID",
            "recorded_at must be a valid ISO-8601 timestamp",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InitialFindingReceiptError(
            "RECEIPT_TIMESTAMP_INVALID",
            "recorded_at must include an explicit timezone",
        )
    return normalized


def _finding_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        candidate = dict(value)
    elif hasattr(value, "to_dict"):
        candidate = value.to_dict()
        if not isinstance(candidate, Mapping):
            raise InitialFindingReceiptError(
                "RECEIPT_FINDINGS_INVALID",
                "finding.to_dict() must return an object",
            )
        candidate = dict(candidate)
    else:
        raise InitialFindingReceiptError(
            "RECEIPT_FINDINGS_INVALID",
            "findings must contain mappings or objects with to_dict()",
        )
    try:
        return copy.deepcopy(candidate)
    except (TypeError, ValueError) as exc:
        raise InitialFindingReceiptError(
            "RECEIPT_FINDINGS_INVALID",
            "finding cannot be copied safely",
        ) from exc


def _normalize_findings(values: Any) -> tuple[dict[str, Any], ...]:
    if values is None:
        sequence: tuple[Any, ...] = ()
    elif isinstance(values, Mapping) or hasattr(values, "to_dict"):
        sequence = (values,)
    elif isinstance(values, (str, bytes, bytearray)):
        raise InitialFindingReceiptError(
            "RECEIPT_FINDINGS_INVALID",
            "findings must be a sequence of finding objects",
        )
    else:
        try:
            sequence = tuple(values)
        except TypeError as exc:
            raise InitialFindingReceiptError(
                "RECEIPT_FINDINGS_INVALID",
                "findings must be iterable",
            ) from exc

    normalized = tuple(_finding_mapping(value) for value in sequence)
    try:
        return tuple(
            sorted(
                normalized,
                key=lambda item: (
                    str(item.get("finding_id", "")),
                    _canonical_bytes(item),
                ),
            )
        )
    except (TypeError, ValueError) as exc:
        raise InitialFindingReceiptError(
            "RECEIPT_FINDINGS_INVALID",
            "findings must be canonical JSON objects",
        ) from exc


def digest_findings(findings: Any) -> str:
    """Return the deterministic digest of a normalized finding set."""

    normalized = _normalize_findings(findings)
    return _digest({"findings": list(normalized)})


@dataclass(frozen=True, slots=True)
class InitialFindingReceipt:
    """Immutable receipt proving one reviewer's initial findings were sealed."""

    run_id: str
    node_id: str
    attempt_id: str
    reviewer_id: str
    session_id: str
    context_id: str
    source_digest: str
    standards_profile_digest: str
    standards_context_digest: str
    finding_digest: str
    recorded_at: str
    receipt_digest: str | None = None
    protocol: str = INITIAL_FINDING_RECEIPT_PROTOCOL
    phase: str = INITIAL_FIRST_PASS

    def __post_init__(self) -> None:
        if self.protocol != INITIAL_FINDING_RECEIPT_PROTOCOL:
            raise InitialFindingReceiptError(
                "RECEIPT_INVALID", "unsupported initial-finding receipt protocol"
            )
        if self.phase != INITIAL_FIRST_PASS:
            raise InitialFindingReceiptError(
                "RECEIPT_INVALID", "receipt phase must be INITIAL_FIRST_PASS"
            )
        for field in (
            "run_id",
            "node_id",
            "attempt_id",
            "reviewer_id",
            "session_id",
            "context_id",
        ):
            object.__setattr__(self, field, _identifier(getattr(self, field), field))
        for field in (
            "source_digest",
            "standards_profile_digest",
            "standards_context_digest",
            "finding_digest",
        ):
            object.__setattr__(self, field, _digest_field(getattr(self, field), field))
        object.__setattr__(self, "recorded_at", _recorded_at(self.recorded_at))
        expected = _digest(self._payload_without_digest())
        if self.receipt_digest is not None:
            _digest_field(self.receipt_digest, "receipt_digest")
            if self.receipt_digest != expected:
                raise InitialFindingReceiptError(
                    "RECEIPT_DIGEST_MISMATCH",
                    "receipt_digest does not match the canonical receipt payload",
                )
        object.__setattr__(self, "receipt_digest", expected)

    @classmethod
    def from_session(
        cls,
        session: ReviewerSession,
        *,
        findings: Any,
        recorded_at: str,
    ) -> "InitialFindingReceipt":
        if not isinstance(session, ReviewerSession):
            raise InitialFindingReceiptError(
                "RECEIPT_SESSION_INVALID",
                "session must be a ReviewerSession",
            )
        return cls(
            run_id=session.run_id,
            node_id=session.node_id,
            attempt_id=session.attempt_id,
            reviewer_id=session.reviewer_id,
            session_id=session.session_id,
            context_id=session.context_id,
            source_digest=session.source_pack_digest,
            standards_profile_digest=session.standards_profile_digest,
            standards_context_digest=session.standards_context_digest,
            finding_digest=digest_findings(findings),
            recorded_at=recorded_at,
        )

    def _payload_without_digest(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "phase": self.phase,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt_id": self.attempt_id,
            "reviewer_id": self.reviewer_id,
            "session_id": self.session_id,
            "context_id": self.context_id,
            "source_digest": self.source_digest,
            "standards_profile_digest": self.standards_profile_digest,
            "standards_context_digest": self.standards_context_digest,
            "finding_digest": self.finding_digest,
            "recorded_at": self.recorded_at,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload_without_digest()
        payload["receipt_digest"] = self.receipt_digest
        return copy.deepcopy(payload)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InitialFindingReceipt":
        if not isinstance(value, Mapping):
            raise InitialFindingReceiptError("RECEIPT_INVALID", "receipt must be an object")
        required = {
            "run_id",
            "node_id",
            "attempt_id",
            "reviewer_id",
            "session_id",
            "context_id",
            "source_digest",
            "standards_profile_digest",
            "standards_context_digest",
            "finding_digest",
            "recorded_at",
        }
        optional = {"protocol", "phase", "receipt_digest"}
        unknown = sorted(set(value) - required - optional)
        missing = sorted(required - set(value))
        if unknown or missing:
            raise InitialFindingReceiptError(
                "RECEIPT_INVALID",
                f"unknown={unknown}, missing={missing}",
            )
        return cls(
            run_id=value["run_id"],
            node_id=value["node_id"],
            attempt_id=value["attempt_id"],
            reviewer_id=value["reviewer_id"],
            session_id=value["session_id"],
            context_id=value["context_id"],
            source_digest=value["source_digest"],
            standards_profile_digest=value["standards_profile_digest"],
            standards_context_digest=value["standards_context_digest"],
            finding_digest=value["finding_digest"],
            recorded_at=value["recorded_at"],
            receipt_digest=value.get("receipt_digest"),
            protocol=value.get("protocol", INITIAL_FINDING_RECEIPT_PROTOCOL),
            phase=value.get("phase", INITIAL_FIRST_PASS),
        )


@dataclass(frozen=True, slots=True)
class ReviewerReceiptRequirement:
    """Digest-only identity/binding required before a receipt can be accepted."""

    run_id: str
    node_id: str
    attempt_id: str
    reviewer_id: str
    session_id: str
    context_id: str
    source_digest: str
    standards_profile_digest: str
    standards_context_digest: str

    @classmethod
    def from_session(cls, session: ReviewerSession) -> "ReviewerReceiptRequirement":
        if not isinstance(session, ReviewerSession):
            raise InitialFindingReceiptError(
                "RECEIPT_SESSION_INVALID", "required reviewer must be a ReviewerSession"
            )
        return cls(
            run_id=session.run_id,
            node_id=session.node_id,
            attempt_id=session.attempt_id,
            reviewer_id=session.reviewer_id,
            session_id=session.session_id,
            context_id=session.context_id,
            source_digest=session.source_pack_digest,
            standards_profile_digest=session.standards_profile_digest,
            standards_context_digest=session.standards_context_digest,
        )

    def __post_init__(self) -> None:
        for field in (
            "run_id",
            "node_id",
            "attempt_id",
            "reviewer_id",
            "session_id",
            "context_id",
        ):
            object.__setattr__(self, field, _identifier(getattr(self, field), field))
        for field in (
            "source_digest",
            "standards_profile_digest",
            "standards_context_digest",
        ):
            object.__setattr__(self, field, _digest_field(getattr(self, field), field))

    def to_dict(self) -> dict[str, str]:
        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt_id": self.attempt_id,
            "reviewer_id": self.reviewer_id,
            "session_id": self.session_id,
            "context_id": self.context_id,
            "source_digest": self.source_digest,
            "standards_profile_digest": self.standards_profile_digest,
            "standards_context_digest": self.standards_context_digest,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReviewerReceiptRequirement":
        if not isinstance(value, Mapping):
            raise InitialFindingReceiptError(
                "RECEIPT_REQUIREMENT_INVALID", "required reviewer must be an object"
            )
        fields = {
            "run_id",
            "node_id",
            "attempt_id",
            "reviewer_id",
            "session_id",
            "context_id",
            "source_digest",
            "standards_profile_digest",
            "standards_context_digest",
        }
        if set(value) != fields:
            raise InitialFindingReceiptError(
                "RECEIPT_REQUIREMENT_INVALID", "required reviewer binding fields are exact"
            )
        return cls(**{field: value[field] for field in fields})


RequirementInput = ReviewerSession | ReviewerReceiptRequirement | Mapping[str, Any]


def _requirement(value: RequirementInput) -> ReviewerReceiptRequirement:
    if isinstance(value, ReviewerReceiptRequirement):
        return value
    if isinstance(value, ReviewerSession):
        return ReviewerReceiptRequirement.from_session(value)
    return ReviewerReceiptRequirement.from_dict(value)


@dataclass(frozen=True, slots=True)
class InitialFindingReceiptLedger:
    """Immutable append-only receipt snapshot and all-required cross-review gate."""

    required_sessions: tuple[RequirementInput, ...]
    receipts: tuple[InitialFindingReceipt, ...] = ()
    sealed: bool = False

    def __post_init__(self) -> None:
        try:
            requirements = tuple(_requirement(value) for value in self.required_sessions)
        except TypeError as exc:
            raise InitialFindingReceiptError(
                "RECEIPT_REQUIREMENT_INVALID", "required_sessions must be iterable"
            ) from exc
        if not requirements:
            raise InitialFindingReceiptError(
                "RECEIPT_REQUIREMENT_INVALID", "at least one required reviewer is needed"
            )
        reviewer_ids = [item.reviewer_id for item in requirements]
        if len(set(reviewer_ids)) != len(reviewer_ids):
            raise InitialFindingReceiptError(
                "RECEIPT_REQUIREMENT_INVALID", "required reviewer identities must be unique"
            )
        requirements = tuple(sorted(requirements, key=lambda item: item.reviewer_id))
        try:
            receipts = tuple(self.receipts)
        except TypeError as exc:
            raise InitialFindingReceiptError(
                "RECEIPT_INVALID", "receipts must be iterable"
            ) from exc
        if any(not isinstance(receipt, InitialFindingReceipt) for receipt in receipts):
            raise InitialFindingReceiptError(
                "RECEIPT_INVALID", "receipts must contain InitialFindingReceipt values"
            )
        receipt_map: dict[str, InitialFindingReceipt] = {}
        requirement_map = {item.reviewer_id: item for item in requirements}
        for receipt in receipts:
            if receipt.reviewer_id in receipt_map:
                raise InitialFindingReceiptError(
                    "RECEIPT_DUPLICATE_CONFLICT",
                    f"multiple receipts for {receipt.reviewer_id}",
                )
            self._validate_binding(receipt, requirement_map)
            receipt_map[receipt.reviewer_id] = receipt
        if self.sealed and set(receipt_map) != set(requirement_map):
            raise InitialFindingReceiptError(
                "INITIAL_RECEIPTS_INCOMPLETE",
                "a sealed ledger must contain every required receipt",
            )
        object.__setattr__(self, "required_sessions", requirements)
        object.__setattr__(
            self,
            "receipts",
            tuple(receipt_map[key] for key in sorted(receipt_map)),
        )

    @classmethod
    def from_sessions(cls, sessions: Sequence[ReviewerSession]) -> "InitialFindingReceiptLedger":
        return cls(required_sessions=tuple(sessions))

    def _requirements(self) -> tuple[ReviewerReceiptRequirement, ...]:
        return cast(tuple[ReviewerReceiptRequirement, ...], self.required_sessions)

    @property
    def required_reviewer_ids(self) -> tuple[str, ...]:
        return tuple(item.reviewer_id for item in self._requirements())

    @property
    def received_reviewer_ids(self) -> tuple[str, ...]:
        return tuple(receipt.reviewer_id for receipt in self.receipts)

    @property
    def missing_reviewer_ids(self) -> tuple[str, ...]:
        received = set(self.received_reviewer_ids)
        return tuple(item for item in self.required_reviewer_ids if item not in received)

    @property
    def ready_for_cross_review(self) -> bool:
        return not self.missing_reviewer_ids

    @staticmethod
    def _validate_binding(
        receipt: InitialFindingReceipt,
        requirement_map: Mapping[str, ReviewerReceiptRequirement],
    ) -> None:
        expected = requirement_map.get(receipt.reviewer_id)
        if expected is None:
            raise InitialFindingReceiptError(
                "RECEIPT_BINDING_MISMATCH",
                f"receipt reviewer {receipt.reviewer_id} is not required",
            )
        for field in (
            "run_id",
            "node_id",
            "attempt_id",
            "reviewer_id",
            "session_id",
            "context_id",
            "source_digest",
            "standards_profile_digest",
            "standards_context_digest",
        ):
            if getattr(receipt, field) != getattr(expected, field):
                raise InitialFindingReceiptError(
                    "RECEIPT_BINDING_MISMATCH",
                    f"receipt {field} does not match required reviewer binding",
                )

    def append(self, receipt: InitialFindingReceipt) -> "InitialFindingReceiptLedger":
        """Append one receipt, returning a new immutable ledger snapshot."""

        if self.sealed:
            raise InitialFindingReceiptError(
                "RECEIPT_LEDGER_SEALED", "sealed ledger cannot accept another receipt"
            )
        if not isinstance(receipt, InitialFindingReceipt):
            raise InitialFindingReceiptError(
                "RECEIPT_INVALID", "append requires an InitialFindingReceipt"
            )
        requirement_map = {item.reviewer_id: item for item in self._requirements()}
        self._validate_binding(receipt, requirement_map)
        existing = next(
            (item for item in self.receipts if item.reviewer_id == receipt.reviewer_id),
            None,
        )
        if existing is not None:
            if existing.receipt_digest == receipt.receipt_digest:
                return self
            raise InitialFindingReceiptError(
                "RECEIPT_DUPLICATE_CONFLICT",
                f"conflicting receipt for {receipt.reviewer_id}",
            )
        return replace(self, receipts=(*self.receipts, receipt))

    record = append
    register = append

    def require_cross_review_ready(self) -> "InitialFindingReceiptLedger":
        """Fail closed until every required reviewer receipt is present."""

        if not self.ready_for_cross_review:
            missing = ", ".join(self.missing_reviewer_ids)
            raise InitialFindingReceiptError(
                "INITIAL_RECEIPTS_INCOMPLETE",
                f"cross-review must wait for receipts: {missing}",
            )
        return self

    def seal(self) -> "InitialFindingReceiptLedger":
        """Seal a complete snapshot; later appends are rejected."""

        self.require_cross_review_ready()
        if self.sealed:
            return self
        return replace(self, sealed=True)

    def _manifest_payload(self) -> dict[str, Any]:
        return {
            "protocol": INITIAL_FINDING_RECEIPT_PROTOCOL,
            "required_sessions": [item.to_dict() for item in self._requirements()],
            "receipts": [receipt.to_dict() for receipt in self.receipts],
            "missing_reviewer_ids": list(self.missing_reviewer_ids),
            "ready_for_cross_review": self.ready_for_cross_review,
            "sealed": self.sealed,
        }

    @property
    def manifest_digest(self) -> str:
        return _digest(self._manifest_payload())

    def to_dict(self) -> dict[str, Any]:
        payload = self._manifest_payload()
        payload["manifest_digest"] = self.manifest_digest
        return copy.deepcopy(payload)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InitialFindingReceiptLedger":
        if not isinstance(value, Mapping):
            raise InitialFindingReceiptError("RECEIPT_INVALID", "ledger must be an object")
        required = {"protocol", "required_sessions", "receipts", "sealed"}
        optional = {"manifest_digest", "missing_reviewer_ids", "ready_for_cross_review"}
        unknown = sorted(set(value) - required - optional)
        missing = sorted(required - set(value))
        if unknown or missing:
            raise InitialFindingReceiptError(
                "RECEIPT_INVALID", f"unknown={unknown}, missing={missing}"
            )
        if value["protocol"] != INITIAL_FINDING_RECEIPT_PROTOCOL:
            raise InitialFindingReceiptError("RECEIPT_INVALID", "unsupported ledger protocol")
        ledger = cls(
            required_sessions=tuple(
                ReviewerReceiptRequirement.from_dict(item)
                for item in value["required_sessions"]
            ),
            receipts=tuple(InitialFindingReceipt.from_dict(item) for item in value["receipts"]),
            sealed=value["sealed"],
        )
        if "manifest_digest" in value and value["manifest_digest"] != ledger.manifest_digest:
            raise InitialFindingReceiptError(
                "RECEIPT_DIGEST_MISMATCH", "manifest_digest does not match canonical ledger"
            )
        if "missing_reviewer_ids" in value and tuple(value["missing_reviewer_ids"]) != ledger.missing_reviewer_ids:
            raise InitialFindingReceiptError(
                "RECEIPT_DIGEST_MISMATCH", "missing reviewer projection does not match ledger"
            )
        if "ready_for_cross_review" in value and value["ready_for_cross_review"] != ledger.ready_for_cross_review:
            raise InitialFindingReceiptError(
                "RECEIPT_DIGEST_MISMATCH", "cross-review readiness projection does not match ledger"
            )
        return ledger


def create_initial_finding_receipt(
    *,
    session: ReviewerSession,
    findings: Any,
    recorded_at: str,
) -> InitialFindingReceipt:
    """Create a digest-only receipt from one exact reviewer session."""

    return InitialFindingReceipt.from_session(
        session,
        findings=findings,
        recorded_at=recorded_at,
    )


__all__ = [
    "INITIAL_FINDING_RECEIPT_PROTOCOL",
    "InitialFindingReceipt",
    "InitialFindingReceiptError",
    "InitialFindingReceiptLedger",
    "ReviewerReceiptRequirement",
    "create_initial_finding_receipt",
    "digest_findings",
    "REVIEWER_SESSION_PROTOCOL",
]
