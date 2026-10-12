"""Qualified, read-only observer for exact TaskController mailbox/v2 refs.

Observation is deliberately separate from canonical cursor acknowledgement and
Executor dispatch: a host may use the returned candidate event for fresh PRECHECK,
but this function never writes state or grants authority.
"""

from __future__ import annotations

from taskcontroller.controlplane.orchestration_policy import ExecutorLoopContinuity
from taskcontroller.interaction.continuation import (
    WAIT_EXECUTOR_EVENT_ACTION,
    ContinuationPhase,
    ContinuationStatus,
    ControllerContinuation,
)
from taskcontroller.interaction.mailbox_repository import (
    MailboxActorCursor,
    MailboxEvent,
    MailboxRepository,
    MailboxSnapshot,
)

MAX_OBSERVER_EVENTS = 64
_OBSERVER_ALLOWED = "ALLOW_READ_ONLY_MAILBOX_OBSERVATION"
_OBSERVER_HELD = "PAUSE_OBSERVER_DURING_HOLD"


def observe_controller_mailbox(
    *,
    repository: MailboxRepository,
    continuation: ControllerContinuation,
    observer_cursor: MailboxActorCursor,
    node_id: str,
    agent_instance: str,
    continuity_decision: ExecutorLoopContinuity,
    max_events: int,
) -> tuple[tuple[MailboxEvent, ...], MailboxActorCursor]:
    """Read at most ``max_events`` exact Controller events after a local cursor.

    The cursor returned here is an observer high-water mark only. It is never
    acknowledged through ``MailboxRepository`` and is not an execution grant.
    """
    if not isinstance(continuity_decision, ExecutorLoopContinuity):
        raise TypeError("qualified mailbox observer decision is required")
    if continuity_decision.scheduler_action == _OBSERVER_HELD:
        return (), observer_cursor
    if (
        continuity_decision.scheduler_action != _OBSERVER_ALLOWED
        or continuity_decision.effects_allowed
        or continuity_decision.auto_resume_allowed
    ):
        raise ValueError("mailbox observer is not qualified for read-only observation")
    if continuity_decision.next_owner != "AGENT":
        raise ValueError("mailbox observer decision has the wrong owner")
    if not isinstance(repository, MailboxRepository):
        raise TypeError("mailbox observer requires a canonical MailboxRepository")
    if not isinstance(continuation, ControllerContinuation):
        raise TypeError("mailbox observer requires a canonical continuation")
    if not isinstance(observer_cursor, MailboxActorCursor):
        raise TypeError("mailbox observer requires a typed observer cursor")
    if (
        not isinstance(node_id, str)
        or not node_id.strip()
        or not isinstance(agent_instance, str)
        or not agent_instance.strip()
    ):
        raise ValueError("mailbox observer binding requires node_id and agent_instance")
    if (
        isinstance(max_events, bool)
        or not isinstance(max_events, int)
        or not 1 <= max_events <= MAX_OBSERVER_EVENTS
    ):
        raise ValueError(f"max_events must be an integer in [1, {MAX_OBSERVER_EVENTS}]")
    if (
        continuation.status != ContinuationStatus.ACTIVE.value
        or continuation.phase != ContinuationPhase.WAIT_EXECUTOR.value
        or continuation.next_action != WAIT_EXECUTOR_EVENT_ACTION
    ):
        raise ValueError(
            "mailbox observer continuation is not awaiting an Executor event"
        )
    if (
        continuation.run_id != observer_cursor.run_id
        or continuation.controller_mailbox_ref != observer_cursor.mailbox_ref
        or node_id != observer_cursor.node_id
        or observer_cursor.actor_namespace != "controller"
    ):
        raise ValueError("mailbox observer continuation/cursor binding mismatch")

    snapshot = repository.read(observer_cursor.mailbox_ref)
    if (
        not isinstance(snapshot, MailboxSnapshot)
        or snapshot.mailbox_ref != observer_cursor.mailbox_ref
    ):
        raise ValueError("mailbox observer exact-readback binding mismatch")

    cursor = observer_cursor
    candidates: list[MailboxEvent] = []
    scanned = 0
    expected_event_seq = observer_cursor.last_event_seq + 1
    for event in snapshot.events:
        if not isinstance(event, MailboxEvent):
            raise TypeError("mailbox observer readback contains a non-event record")
        if event.event_seq <= observer_cursor.last_event_seq:
            continue
        if scanned >= max_events:
            break
        if event.event_seq != expected_event_seq:
            raise ValueError("mailbox observer event sequence has a gap")
        envelope = event.envelope.to_dict()
        recipient = envelope.get("recipient")
        attempt = envelope.get("attempt")
        if (
            event.mailbox_ref != observer_cursor.mailbox_ref
            or event.producer_namespace != "controller"
            or event.envelope.run_id != continuation.run_id
            or event.envelope.node_id != node_id
            or event.logical_seq != envelope.get("seq")
            or envelope.get("direction") != "controller_to_executor"
            or envelope.get("message_type") != "execution_request"
            or not isinstance(recipient, dict)
            or recipient.get("capability") != "taskcontroller.executor"
            or recipient.get("agent_instance") != agent_instance
            or not isinstance(attempt, dict)
            or attempt.get("agent_instance") != agent_instance
        ):
            raise ValueError("mailbox observer event binding mismatch")
        cursor = cursor.observe(event)
        scanned += 1
        expected_event_seq += 1
        if event.logical_seq > continuation.controller_seq:
            candidates.append(event)
    return tuple(candidates), cursor
