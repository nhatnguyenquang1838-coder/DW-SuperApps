"""Fail-closed orchestration policy for Controller-owned HITL and Executor outcomes.

This module closes the gap between an outcome-oriented EXECUTE contract and
mailbox/v2 runtime results. The Controller owns planning, human authority, and
next-gate decisions. The Executor reports progress/completion/blockers only to
the Controller and never creates a User-facing approval loop.

The policy is deliberately transport-neutral and grants no authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, NoReturn, Sequence

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope


BLOCKER_AUTHORITY_BOUNDARY = "AUTHORITY_BOUNDARY"
BLOCKER_SCOPE_EXPANSION = "SCOPE_EXPANSION"
BLOCKER_MATERIAL_PLAN_INVALIDATION = "MATERIAL_PLAN_INVALIDATION"
BLOCKER_EXTERNAL_DEPENDENCY = "EXTERNAL_DEPENDENCY_BLOCKED"

EXECUTOR_BLOCKER_CLASSES = frozenset(
    {
        BLOCKER_AUTHORITY_BOUNDARY,
        BLOCKER_SCOPE_EXPANSION,
        BLOCKER_MATERIAL_PLAN_INVALIDATION,
        BLOCKER_EXTERNAL_DEPENDENCY,
    }
)

HOLD_EFFECT = "EFFECT_HOLD"
HOLD_RUN = "RUN_HOLD"
HOLD_TYPES = frozenset({HOLD_EFFECT, HOLD_RUN})

_BLOCKING_PROGRESS_STATUSES = frozenset({"BLOCKED", "NEEDS_CLARIFICATION"})
_FORBIDDEN_USER_WAIT_PREFIXES = ("WAIT_USER", "WAIT_HUMAN")
_FORBIDDEN_EXECUTOR_HITL_KEYS = frozenset(
    {
        "approval_command",
        "approval_token",
        "human_approval_command",
        "user_approval",
        "wait_user",
    }
)


class OrchestrationPolicyError(TaskControllerValidationError):
    """Stable fail-closed error for anti-stuck orchestration invariants."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> NoReturn:
    raise OrchestrationPolicyError(code, message)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("ORCHESTRATION_POLICY_INVALID", f"{field} must be non-empty")
    return value.strip()


def _string_list(value: Any, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail("ORCHESTRATION_POLICY_INVALID", f"{field} must be an array")
    result = tuple(_text(item, f"{field}[]") for item in value)
    if not allow_empty and not result:
        _fail("ORCHESTRATION_POLICY_INVALID", f"{field} must not be empty")
    if len(set(result)) != len(result):
        _fail("ORCHESTRATION_POLICY_INVALID", f"{field} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class ExecutorProgressOutcome:
    """Validated Executor progress/completion/boundary report."""

    envelope: V2MailboxEnvelope
    status: str
    typed_next: str | None
    blocker_class: str | None
    blocker_detail: str | None
    report_type: str | None

    @property
    def requires_controller_action(self) -> bool:
        return self.blocker_class is not None or self.status in _BLOCKING_PROGRESS_STATUSES

    @property
    def completed(self) -> bool:
        return self.status == "SUCCEEDED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "typed_next": self.typed_next,
            "blocker_class": self.blocker_class,
            "blocker_detail": self.blocker_detail,
            "report_type": self.report_type,
            "requires_controller_action": self.requires_controller_action,
            "completed": self.completed,
        }


def validate_executor_progress(envelope: V2MailboxEnvelope) -> ExecutorProgressOutcome:
    """Validate one executor_to_controller execution_progress envelope.

    A blocker is always reported to the Controller. The Executor cannot emit
    a User/Human wait semantic or carry an approval command/token.
    """

    if not isinstance(envelope, V2MailboxEnvelope):
        _fail("EXECUTOR_PROGRESS_INVALID", "progress must be a V2MailboxEnvelope")
    raw = envelope.to_dict()
    if raw.get("message_type") != "execution_progress":
        _fail("EXECUTOR_PROGRESS_INVALID", "message_type must be execution_progress")
    if raw.get("direction") != "executor_to_controller":
        _fail("EXECUTOR_PROGRESS_DIRECTION_INVALID", "Executor progress must flow executor_to_controller")
    producer = raw.get("producer")
    if not isinstance(producer, Mapping) or producer.get("role") != "executor":
        _fail("EXECUTOR_PROGRESS_PRODUCER_INVALID", "execution_progress producer role must be executor")
    recipient = raw.get("recipient")
    if not isinstance(recipient, Mapping) or recipient.get("capability") != "taskcontroller.controller":
        _fail("EXECUTOR_PROGRESS_RECIPIENT_INVALID", "Executor progress must target taskcontroller.controller")

    payload = raw.get("payload")
    if not isinstance(payload, Mapping):
        _fail("EXECUTOR_PROGRESS_INVALID", "execution_progress payload must be an object")
    forbidden = _FORBIDDEN_EXECUTOR_HITL_KEYS.intersection(payload)
    if forbidden:
        _fail(
            "EXECUTOR_USER_HITL_FORBIDDEN",
            "Executor cannot materialize User/Human approval fields: " + ", ".join(sorted(forbidden)),
        )

    provenance = raw.get("provenance")
    provenance_status = provenance.get("status") if isinstance(provenance, Mapping) else None
    status = _text(payload.get("status", provenance_status), "payload.status").upper()

    typed_next_raw = payload.get("typed_next")
    typed_next = None if typed_next_raw is None else _text(typed_next_raw, "payload.typed_next")
    if typed_next is not None and typed_next.upper().startswith(_FORBIDDEN_USER_WAIT_PREFIXES):
        _fail(
            "EXECUTOR_USER_HITL_FORBIDDEN",
            "Executor must return a Controller boundary; it cannot wait for User/Human approval directly",
        )

    blocker_raw = payload.get("blocker_class")
    blocker_class = None if blocker_raw is None else _text(blocker_raw, "payload.blocker_class").upper()
    if blocker_class is not None and blocker_class not in EXECUTOR_BLOCKER_CLASSES:
        _fail(
            "EXECUTOR_BLOCKER_CLASS_INVALID",
            "blocker_class must be one of " + ", ".join(sorted(EXECUTOR_BLOCKER_CLASSES)),
        )
    if status in _BLOCKING_PROGRESS_STATUSES and blocker_class is None:
        _fail(
            "EXECUTOR_BLOCKER_CLASS_REQUIRED",
            "blocked/needs-clarification progress requires one canonical blocker_class",
        )

    detail_raw = payload.get("blocker_detail")
    blocker_detail = None if detail_raw is None else _text(detail_raw, "payload.blocker_detail")
    if blocker_class is not None and blocker_detail is None:
        _fail("EXECUTOR_BLOCKER_DETAIL_REQUIRED", "blocker_class requires blocker_detail")

    report_raw = payload.get("report_type")
    report_type = None if report_raw is None else _text(report_raw, "payload.report_type")

    return ExecutorProgressOutcome(
        envelope=envelope,
        status=status,
        typed_next=typed_next,
        blocker_class=blocker_class,
        blocker_detail=blocker_detail,
        report_type=report_type,
    )


@dataclass(frozen=True, slots=True)
class HoldSemantics:
    hold_type: str
    denied_effects: tuple[str, ...]
    control_loop_continues: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.hold_type,
            "denied_effects": list(self.denied_effects),
            "control_loop_continues": self.control_loop_continues,
        }


def validate_hold_semantics(payload: Mapping[str, Any]) -> HoldSemantics | None:
    """Validate explicit EFFECT_HOLD vs RUN_HOLD semantics on Controller payloads."""

    if not isinstance(payload, Mapping):
        _fail("ORCHESTRATION_POLICY_INVALID", "Controller payload must be an object")
    hold = payload.get("hold")
    disposition = payload.get("disposition")
    disposition_mentions_hold = isinstance(disposition, str) and "HOLD" in disposition.upper()
    if hold is None:
        if disposition_mentions_hold:
            _fail(
                "AMBIGUOUS_HOLD_FORBIDDEN",
                "HOLD disposition must declare typed hold semantics (EFFECT_HOLD or RUN_HOLD)",
            )
        return None
    if not isinstance(hold, Mapping):
        _fail("HOLD_POLICY_INVALID", "hold must be an object")

    hold_type = _text(hold.get("type"), "hold.type").upper()
    if hold_type not in HOLD_TYPES:
        _fail("HOLD_POLICY_INVALID", "hold.type must be EFFECT_HOLD or RUN_HOLD")
    denied_effects = _string_list(
        hold.get("denied_effects", ()),
        "hold.denied_effects",
        allow_empty=hold_type == HOLD_RUN,
    )
    continues = hold.get("control_loop_continues")
    if not isinstance(continues, bool):
        _fail("HOLD_POLICY_INVALID", "hold.control_loop_continues must be boolean")

    if hold_type == HOLD_EFFECT and not continues:
        _fail(
            "EFFECT_HOLD_MUST_CONTINUE_CONTROL_LOOP",
            "EFFECT_HOLD gates named effects only; Controller reasoning/planning must continue",
        )
    if hold_type == HOLD_RUN and continues:
        _fail("RUN_HOLD_MUST_STOP_CONTROL_LOOP", "RUN_HOLD must stop new run actions")

    return HoldSemantics(
        hold_type=hold_type,
        denied_effects=denied_effects,
        control_loop_continues=continues,
    )


__all__ = [
    "BLOCKER_AUTHORITY_BOUNDARY",
    "BLOCKER_EXTERNAL_DEPENDENCY",
    "BLOCKER_MATERIAL_PLAN_INVALIDATION",
    "BLOCKER_SCOPE_EXPANSION",
    "EXECUTOR_BLOCKER_CLASSES",
    "ExecutorProgressOutcome",
    "HOLD_EFFECT",
    "HOLD_RUN",
    "HOLD_TYPES",
    "HoldSemantics",
    "OrchestrationPolicyError",
    "validate_executor_progress",
    "validate_hold_semantics",
]
