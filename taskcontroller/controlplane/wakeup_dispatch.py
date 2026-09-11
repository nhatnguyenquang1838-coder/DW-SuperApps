"""Controller-side pointer-only wakeup emission boundary.

This module composes already-verified mailbox dispatch evidence with the v1
pointer signal and a bounded human projection.  It deliberately does not
perform Slack or any other transport I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, NoReturn

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


WAKEUP_PROJECTION_PROTOCOL = "dw.taskcontroller.wakeup-projection/v1"
WAKEUP_PROJECTION_PENDING = "PENDING"
WAKEUP_PROJECTION_RETRYING = "RETRYING"
WAKEUP_PROJECTION_DELIVERED = "DELIVERED"
WAKEUP_PROJECTION_BLOCKED = "BLOCKED"
WAKEUP_EXECUTOR_NOT_TRIGGERED = "NOT_TRIGGERED"
WAKEUP_EXECUTOR_RETRYING = "WAKEUP_RETRYING"
WAKEUP_EXECUTOR_DELIVERED_CLAIM_UNCONFIRMED = "WAKEUP_DELIVERED_CLAIM_UNCONFIRMED"
WAKEUP_EXECUTOR_BLOCKED = "WAKEUP_BLOCKED"


@dataclass(frozen=True)
class WakeupDeliveryProjection:
    """Read-only human projection of the separate WakeupDelivery state domain.

    A projection is deliberately not a run-state record.  Its identity points
    back to the already persisted GitHub mailbox event and its outbox intent;
    it contains no request payload and cannot advance either canonical source.
    """

    intent_id: str
    run_id: str
    node_id: str
    mailbox_ref: str
    mailbox_seq: int
    event_id: str
    event_digest: str
    envelope_digest: str
    idempotency_key: str
    recipient: str
    delivery_status: str
    executor_status: str
    attempt_count: int
    next_attempt_at: str | None
    detail: str
    canonical_source: str = "github-mailbox"
    canonical_request_persisted: bool = True
    projection_only: bool = True
    protocol: str = WAKEUP_PROJECTION_PROTOCOL

    def __post_init__(self) -> None:
        if self.protocol != WAKEUP_PROJECTION_PROTOCOL:
            raise TaskControllerValidationError(
                "unsupported WakeupDeliveryProjection protocol"
            )
        for name in (
            "intent_id",
            "run_id",
            "node_id",
            "mailbox_ref",
            "event_id",
            "event_digest",
            "envelope_digest",
            "idempotency_key",
            "recipient",
            "detail",
        ):
            _required_text(getattr(self, name), f"wakeup_projection.{name}")
        if self.delivery_status not in {
            WAKEUP_PROJECTION_PENDING,
            WAKEUP_PROJECTION_RETRYING,
            WAKEUP_PROJECTION_DELIVERED,
            WAKEUP_PROJECTION_BLOCKED,
        }:
            raise TaskControllerValidationError(
                f"unsupported wakeup projection delivery status: {self.delivery_status!r}"
            )
        if self.executor_status not in {
            WAKEUP_EXECUTOR_NOT_TRIGGERED,
            WAKEUP_EXECUTOR_RETRYING,
            WAKEUP_EXECUTOR_DELIVERED_CLAIM_UNCONFIRMED,
            WAKEUP_EXECUTOR_BLOCKED,
        }:
            raise TaskControllerValidationError(
                f"unsupported wakeup projection executor status: {self.executor_status!r}"
            )
        if isinstance(self.mailbox_seq, bool) or not isinstance(self.mailbox_seq, int) or self.mailbox_seq < 0:
            raise TaskControllerValidationError(
                "wakeup_projection.mailbox_seq must be int >= 0"
            )
        if isinstance(self.attempt_count, bool) or not isinstance(self.attempt_count, int) or self.attempt_count < 0:
            raise TaskControllerValidationError(
                "wakeup_projection.attempt_count must be int >= 0"
            )
        if self.next_attempt_at is not None:
            _required_text(self.next_attempt_at, "wakeup_projection.next_attempt_at")
        if self.canonical_source != "github-mailbox":
            raise TaskControllerValidationError(
                "wakeup projection canonical source must be github-mailbox"
            )
        if self.canonical_request_persisted is not True or self.projection_only is not True:
            raise TaskControllerValidationError(
                "wakeup projection must remain a persisted-request-only projection"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize operator data without mailbox request or run-state payloads."""

        return {
            "protocol": self.protocol,
            "record_type": "WakeupDeliveryProjection",
            "intent_id": self.intent_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "mailbox_ref": self.mailbox_ref,
            "mailbox_seq": self.mailbox_seq,
            "event_id": self.event_id,
            "event_digest": self.event_digest,
            "envelope_digest": self.envelope_digest,
            "idempotency_key": self.idempotency_key,
            "recipient": self.recipient,
            "delivery_status": self.delivery_status,
            "executor_status": self.executor_status,
            "attempt_count": self.attempt_count,
            "next_attempt_at": self.next_attempt_at,
            "detail": self.detail,
            "canonical_source": self.canonical_source,
            "canonical_request_persisted": self.canonical_request_persisted,
            "projection_only": self.projection_only,
        }

    def to_human_event(self) -> HumanEvent:
        """Adapt the delivery projection to the existing human-plane event."""

        kind = (
            HumanEventKind.BLOCKED.value
            if self.delivery_status == WAKEUP_PROJECTION_BLOCKED
            else HumanEventKind.SUBTASK_STARTED.value
        )
        return HumanEvent(
            kind=kind,
            title=f"Wake-up {self.delivery_status.lower()} for {self.node_id}",
            status=f"WAKEUP_{self.delivery_status}",
            detail=self.detail,
            evidence_refs=(self.mailbox_ref, self.event_id, self.intent_id),
        )


def project_wakeup_delivery(
    intent: Any,
    attempts: Iterable[Any] = (),
) -> WakeupDeliveryProjection:
    """Project durable outbox evidence for operators without changing authority.

    ``WakeupIntent`` is only created from a readback-verified mailbox commit.
    The full append-only attempt list is required when attempts exist so a
    projection cannot hide delivery history or accidentally become canonical
    run state.  The local import preserves the outbox → pointer-emission import
    boundary.
    """

    from taskcontroller.controlplane.wakeup_outbox import (
        WAKEUP_ATTEMPT_BLOCKED,
        WAKEUP_ATTEMPT_DELIVERED,
        WAKEUP_ATTEMPT_FAILED,
        WAKEUP_ATTEMPT_STARTED,
        WAKEUP_INTENT_BLOCKED,
        WAKEUP_INTENT_DELIVERED,
        WAKEUP_INTENT_FAILED,
        WAKEUP_INTENT_IN_FLIGHT,
        WAKEUP_INTENT_PENDING,
        WakeupDeliveryAttempt,
        WakeupIntent,
    )

    if not isinstance(intent, WakeupIntent):
        raise TaskControllerValidationError(
            "wakeup projection requires WakeupIntent evidence"
        )
    try:
        observed_attempts = tuple(attempts)
    except TypeError as exc:
        raise TaskControllerValidationError(
            "wakeup projection attempts must be iterable"
        ) from exc
    for expected_number, attempt in enumerate(observed_attempts, start=1):
        if not isinstance(attempt, WakeupDeliveryAttempt):
            raise TaskControllerValidationError(
                "wakeup projection requires WakeupDeliveryAttempt evidence"
            )
        if attempt.intent_id != intent.intent_id:
            raise TaskControllerValidationError(
                "wakeup projection attempt is not bound to the intent"
            )
        if attempt.attempt_number != expected_number:
            raise TaskControllerValidationError(
                "wakeup projection attempts must be contiguous"
            )
    if intent.attempt_count != len(observed_attempts):
        raise TaskControllerValidationError(
            "wakeup projection attempt count differs from the intent"
        )

    last_attempt = observed_attempts[-1] if observed_attempts else None
    if intent.state == WAKEUP_INTENT_PENDING and last_attempt is None:
        delivery_status = WAKEUP_PROJECTION_PENDING
        executor_status = WAKEUP_EXECUTOR_NOT_TRIGGERED
        detail = (
            "canonical request persisted in GitHub mailbox; "
            "Executor not yet triggered; wake-up delivery is pending."
        )
    elif intent.state == WAKEUP_INTENT_DELIVERED:
        if last_attempt is None or last_attempt.state != WAKEUP_ATTEMPT_DELIVERED:
            raise TaskControllerValidationError(
                "delivered wakeup projection lacks a delivered attempt"
            )
        delivery_status = WAKEUP_PROJECTION_DELIVERED
        executor_status = WAKEUP_EXECUTOR_DELIVERED_CLAIM_UNCONFIRMED
        detail = (
            "canonical request persisted in GitHub mailbox; pointer wake-up "
            "delivered; Executor claim is not observed by this projection."
        )
    elif intent.state == WAKEUP_INTENT_BLOCKED:
        if last_attempt is None or last_attempt.state != WAKEUP_ATTEMPT_BLOCKED:
            raise TaskControllerValidationError(
                "blocked wakeup projection lacks a blocked attempt"
            )
        delivery_status = WAKEUP_PROJECTION_BLOCKED
        executor_status = WAKEUP_EXECUTOR_BLOCKED
        detail = (
            "canonical request persisted in GitHub mailbox; wake-up delivery "
            "is blocked with WAKEUP_DELIVERY_BLOCKED; Executor trigger is not confirmed."
        )
    elif intent.state in {
        WAKEUP_INTENT_PENDING,
        WAKEUP_INTENT_IN_FLIGHT,
        WAKEUP_INTENT_FAILED,
    } and last_attempt is not None and last_attempt.state in {
        WAKEUP_ATTEMPT_STARTED,
        WAKEUP_ATTEMPT_FAILED,
    }:
        delivery_status = WAKEUP_PROJECTION_RETRYING
        executor_status = WAKEUP_EXECUTOR_RETRYING
        detail = (
            "canonical request persisted in GitHub mailbox; Executor wake-up "
            "delivery is retrying; Executor claim is not observed."
        )
    else:
        raise TaskControllerValidationError(
            "wakeup projection state and attempt evidence are inconsistent"
        )

    return WakeupDeliveryProjection(
        intent_id=intent.intent_id,
        run_id=intent.run_id,
        node_id=intent.node_id,
        mailbox_ref=intent.mailbox_ref,
        mailbox_seq=intent.mailbox_seq,
        event_id=intent.event_id,
        event_digest=intent.event_digest,
        envelope_digest=intent.envelope_digest,
        idempotency_key=intent.idempotency_key,
        recipient=intent.recipient,
        delivery_status=delivery_status,
        executor_status=executor_status,
        attempt_count=intent.attempt_count,
        next_attempt_at=intent.next_attempt_at,
        detail=detail,
    )


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


__all__ = [
    "PointerWakeupEmission",
    "WAKEUP_EXECUTOR_BLOCKED",
    "WAKEUP_EXECUTOR_DELIVERED_CLAIM_UNCONFIRMED",
    "WAKEUP_EXECUTOR_NOT_TRIGGERED",
    "WAKEUP_EXECUTOR_RETRYING",
    "WAKEUP_PROJECTION_BLOCKED",
    "WAKEUP_PROJECTION_DELIVERED",
    "WAKEUP_PROJECTION_PENDING",
    "WAKEUP_PROJECTION_PROTOCOL",
    "WAKEUP_PROJECTION_RETRYING",
    "WakeupDeliveryProjection",
    "emit_pointer_only_wakeup",
    "project_wakeup_delivery",
]
