"""Controller-side pointer-only wakeup emission boundary.

This module composes already-verified mailbox dispatch evidence with the v1
pointer signal and a bounded human projection.  It deliberately does not
perform Slack or any other transport I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn

from taskcontroller.controlplane.mailbox_dispatch import MailboxDispatchOutcome
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.human_projection import HumanEvent, HumanEventKind
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
)
from taskcontroller.interaction.wakeup import WakeupSignal
from taskcontroller.interaction.wakeup_gate import (
    WAKEUP_DUPLICATE,
    WAKEUP_EMITTED,
    WakeupDecision,
    WakeupGate,
)


def _fail(code: str, message: str) -> NoReturn:
    raise MailboxV2ValidationError(code, message)


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, f"{name} must be non-empty")
    return value


def _expected_agent_instance(envelope: V2MailboxEnvelope) -> str:
    recipient = envelope.to_dict().get("recipient")
    if not isinstance(recipient, dict):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "v2 envelope recipient must be an object")
    return _required_text(recipient.get("agent_instance"), "recipient.agent_instance")


def _human_projection(
    envelope: V2MailboxEnvelope,
    decision: WakeupDecision,
) -> HumanEvent:
    signal = decision.signal
    if not isinstance(signal, WakeupSignal):
        raise TaskControllerValidationError("human projection requires an emitted WakeupSignal")
    return HumanEvent(
        kind=HumanEventKind.SUBTASK_STARTED.value,
        title=f"Started {envelope.node_id}",
        status="DISPATCHED",
        detail=(
            f"Controller sent a pointer-only wake-up to {signal.recipient}; "
            f"canonical mailbox sequence {decision.mailbox_seq} is available."
        ),
        evidence_refs=(decision.mailbox_ref,),
    )


def _human_event_to_dict(event: HumanEvent) -> dict[str, Any]:
    return {
        "kind": event.kind,
        "title": event.title,
        "status": event.status,
        "detail": event.detail,
        "evidence_refs": list(event.evidence_refs),
    }


@dataclass(frozen=True)
class PointerWakeupEmission:
    """Pointer signal plus optional human projection, never executable payload."""

    decision: WakeupDecision
    human_projection: HumanEvent | None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WakeupDecision):
            raise TaskControllerValidationError("pointer wakeup requires WakeupDecision")
        if self.decision.status == WAKEUP_EMITTED:
            if not isinstance(self.decision.signal, WakeupSignal):
                raise TaskControllerValidationError("EMITTED wakeup requires WakeupSignal")
            if not isinstance(self.human_projection, HumanEvent):
                raise TaskControllerValidationError(
                    "EMITTED wakeup requires a human projection"
                )
        elif self.decision.status == WAKEUP_DUPLICATE:
            if self.decision.signal is not None or self.human_projection is not None:
                raise TaskControllerValidationError(
                    "DUPLICATE wakeup cannot carry a second notification"
                )

    def to_notification_dict(self) -> dict[str, Any] | None:
        """Serialize only the Slack-safe pointer and bounded human projection."""

        if self.decision.status != WAKEUP_EMITTED or self.decision.signal is None:
            return None
        assert self.human_projection is not None
        payload = self.decision.signal.to_dict()
        payload["human_projection"] = _human_event_to_dict(self.human_projection)
        return payload


def emit_pointer_only_wakeup(
    outcome: MailboxDispatchOutcome,
    envelope: V2MailboxEnvelope,
    *,
    sender: str,
    recipient: str,
    updated_at: str,
    gate: WakeupGate | None = None,
) -> PointerWakeupEmission:
    """Emit one pointer-only wakeup from exact mailbox dispatch evidence.

    The adapter accepts no raw request body and performs no transport I/O.  A
    caller receives a notification payload only after the supplied outcome has
    passed the mailbox dispatch/cursor boundary and the recipient binding has
    been checked.
    """

    if not isinstance(outcome, MailboxDispatchOutcome):
        raise TaskControllerValidationError(
            "pointer wakeup requires MailboxDispatchOutcome exact-readback evidence"
        )
    if not isinstance(envelope, V2MailboxEnvelope):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "pointer wakeup requires a v2 envelope")

    sender = _required_text(sender, "sender")
    recipient = _required_text(recipient, "recipient")
    updated_at = _required_text(updated_at, "updated_at")
    committed = outcome.committed
    payload = envelope.to_dict()

    if committed.run_id != envelope.run_id or committed.node_id != envelope.node_id:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "wakeup envelope run/node differs from commit")
    if committed.envelope_digest != envelope.digest():
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "wakeup envelope digest differs from commit")
    if committed.message_id != payload.get("message_id"):
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "wakeup message ID differs from commit")
    if outcome.cursor.actor_namespace != envelope.producer_namespace:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "wakeup cursor actor differs from producer")
    if sender != envelope.producer_namespace:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "wakeup sender differs from producer")
    if recipient != _expected_agent_instance(envelope):
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "wakeup recipient differs from envelope")

    wakeup_gate = gate if gate is not None else WakeupGate()
    decision = wakeup_gate.issue(
        committed,
        sender=sender,
        recipient=recipient,
        updated_at=updated_at,
    )
    projection = _human_projection(envelope, decision) if decision.status == WAKEUP_EMITTED else None
    return PointerWakeupEmission(decision=decision, human_projection=projection)


__all__ = ["PointerWakeupEmission", "emit_pointer_only_wakeup"]
