"""TC-MBX-705: map normalized Controller decisions without mutating state.

The mapping is a pure boundary between a validated terminal result and the
Controller's richer decision vocabulary.  It carries canonical evidence
references forward and never grants external approval/merge/deploy authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

from taskcontroller.controlplane.semantic_acceptance import SemanticAcceptance
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.execution.terminal_result import TerminalParentResult


DECISION_CONTINUE = "CONTINUE"
DECISION_RETRY = "RETRY"
DECISION_REPLAN = "REPLAN"
DECISION_WAIT = "WAIT"
DECISION_ESCALATE = "ESCALATE"
DECISION_COMPLETE = "COMPLETE"
DECISION_CANCEL = "CANCEL"
DECISIONS = (
    DECISION_CONTINUE,
    DECISION_RETRY,
    DECISION_REPLAN,
    DECISION_WAIT,
    DECISION_ESCALATE,
    DECISION_COMPLETE,
)
_REQUESTED_DECISIONS = frozenset((*DECISIONS, DECISION_CANCEL))


class DecisionMappingError(TaskControllerValidationError):
    """Stable fail-closed error for an invalid decision/result binding."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> NoReturn:
    raise DecisionMappingError(code, message)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("DECISION_INVALID", f"{field} must be a non-empty string")
    normalized = value.strip().upper() if field.endswith("decision_type") else value.strip()
    if "\x00" in normalized:
        _fail("DECISION_INVALID", f"{field} must not contain NUL")
    return normalized


def _refs(value: Any, field: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        _fail("DECISION_EVIDENCE_INVALID", f"{field} must be a non-empty array")
    refs = tuple(sorted({
        _text(item, f"{field}[]")
        for item in value
    }))
    if not refs:
        _fail("DECISION_EVIDENCE_INVALID", f"{field} must not be empty")
    return refs


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("DECISION_INVALID", f"{field} must be an object")
    return value


def _truth_signal(value: Any, field: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        _fail("DECISION_INVALID", f"{field} must be boolean")
    return value


@dataclass(frozen=True, slots=True)
class DecisionMapping:
    """Immutable Controller decision projection with evidence binding."""

    decision: str
    requested_decision: str
    decision_id: str
    rationale: str
    result_digest: str
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]
    completion_blocked: bool = False
    human_approval_required: bool = False
    authority_granted: bool = False

    @property
    def can_close(self) -> bool:
        """Only an accepted COMPLETE without human-boundary escalation can close."""

        return (
            self.decision == DECISION_COMPLETE
            and not self.completion_blocked
            and not self.human_approval_required
            and self.authority_granted is False
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "requested_decision": self.requested_decision,
            "decision_id": self.decision_id,
            "rationale": self.rationale,
            "result_digest": self.result_digest,
            "evidence_refs": list(self.evidence_refs),
            "reason_codes": list(self.reason_codes),
            "completion_blocked": self.completion_blocked,
            "human_approval_required": self.human_approval_required,
            "authority_granted": self.authority_granted,
            "can_close": self.can_close,
        }


def map_terminal_decision(
    terminal: TerminalParentResult,
    acceptance: SemanticAcceptance,
) -> DecisionMapping:
    """Map one terminal result into a bounded Controller decision.

    ``COMPLETE`` is emitted only when semantic acceptance is true.  ``CANCEL``
    and explicit authority signals are represented as ``ESCALATE`` so this
    adapter cannot turn a result into an approval, merge, deploy, or mutation.
    """

    if not isinstance(terminal, TerminalParentResult):
        _fail("DECISION_RESULT_INVALID", "terminal must be a TerminalParentResult")
    if not isinstance(acceptance, SemanticAcceptance):
        _fail("DECISION_ACCEPTANCE_INVALID", "acceptance must be a SemanticAcceptance")
    if acceptance.result_digest != terminal.result_digest:
        _fail("DECISION_RESULT_DIGEST_MISMATCH", "acceptance is not bound to terminal result_digest")

    normalized = terminal.normalized_result
    decision = _mapping(normalized.get("controller_decision"), "controller_decision")
    requested = _text(decision.get("decision_type"), "controller_decision.decision_type")
    if requested not in _REQUESTED_DECISIONS:
        _fail("DECISION_INVALID", f"unsupported decision_type: {requested!r}")
    decision_id = _text(decision.get("decision_id"), "controller_decision.decision_id")
    rationale = _text(decision.get("rationale"), "controller_decision.rationale")
    direct_refs = _refs(decision.get("evidence_refs"), "controller_decision.evidence_refs")
    evidence_refs = acceptance.evidence_refs
    if not evidence_refs:
        _fail("DECISION_EVIDENCE_INVALID", "semantic acceptance has no evidence references")
    if not set(direct_refs).issubset(set(evidence_refs)):
        _fail("DECISION_EVIDENCE_INVALID", "decision evidence is absent from the accepted result evidence")

    human_signal = any(
        _truth_signal(normalized.get(field), f"normalized_parent_result.{field}")
        for field in ("human_approval_required", "authority_required")
    ) or any(
        _truth_signal(decision.get(field), f"controller_decision.{field}")
        for field in ("human_approval_required", "authority_required")
    )

    mapped = requested
    reasons: list[str] = []
    completion_blocked = False
    human_approval_required = human_signal

    if requested == DECISION_CANCEL:
        mapped = DECISION_ESCALATE
        human_approval_required = True
        reasons.append("HUMAN_AUTHORITY_REQUIRED")
    elif requested == DECISION_COMPLETE and not acceptance.accepted:
        mapped = DECISION_WAIT
        completion_blocked = True
        reasons.append("COMPLETION_NOT_ACCEPTED")

    if human_signal and requested != DECISION_CANCEL:
        mapped = DECISION_ESCALATE
        human_approval_required = True
        reasons.append("HUMAN_AUTHORITY_REQUIRED")

    if not reasons:
        reasons.append("MAPPED")

    return DecisionMapping(
        decision=mapped,
        requested_decision=requested,
        decision_id=decision_id,
        rationale=rationale,
        result_digest=terminal.result_digest,
        evidence_refs=tuple(sorted(evidence_refs)),
        reason_codes=tuple(dict.fromkeys(reasons)),
        completion_blocked=completion_blocked,
        human_approval_required=human_approval_required,
        authority_granted=False,
    )


def map_normalized_result(
    terminal: TerminalParentResult,
    acceptance: SemanticAcceptance,
) -> DecisionMapping:
    """Compatibility-oriented descriptive alias for the Controller adapter."""

    return map_terminal_decision(terminal, acceptance)


__all__ = [
    "DECISION_CANCEL",
    "DECISION_COMPLETE",
    "DECISION_CONTINUE",
    "DECISION_ESCALATE",
    "DECISION_REPLAN",
    "DECISION_RETRY",
    "DECISION_WAIT",
    "DECISIONS",
    "DecisionMapping",
    "DecisionMappingError",
    "map_normalized_result",
    "map_terminal_decision",
]
