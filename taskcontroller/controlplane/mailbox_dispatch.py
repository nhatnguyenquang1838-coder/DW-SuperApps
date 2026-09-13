"""Controller mailbox/v2 write, exact-readback, and cursor boundary.

The lower-level dispatch protocol owns the durable prepare/CAS/readback/commit
ordering.  This composition boundary consumes only its readback-backed commit,
records the exact mailbox sequence/digests, and acknowledges the bound producer
cursor.  It deliberately has no notification or transport parameter: callers
can reach a later pointer-only wakeup boundary only after this function returns
an outcome containing verified evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_repository import (
    MailboxActorCursor,
    MailboxEvent,
    MailboxRepository,
    MailboxSnapshot,
    WriteReceipt,
)
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
)
from taskcontroller.runtime.dispatch_ledger import (
    DispatchCommitted,
    DispatchPrepared,
    DispatchProtocol,
)


def _fail(code: str, message: str) -> NoReturn:
    raise MailboxV2ValidationError(code, message)


@dataclass(frozen=True)
class MailboxDispatchOutcome:
    """Verified dispatch evidence returned before any pointer notification."""

    committed: DispatchCommitted
    cursor: MailboxActorCursor

    def __post_init__(self) -> None:
        if not isinstance(self.committed, DispatchCommitted):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "dispatch outcome commit is invalid")
        if self.committed.readback_verified is not True:
            _fail(
                MailboxV2ErrorCode.DIGEST_MISMATCH,
                "dispatch outcome requires exact-readback-verified commit",
            )
        if not isinstance(self.cursor, MailboxActorCursor):
            _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "dispatch outcome cursor is invalid")
        if self.cursor.mailbox_ref != self.committed.mailbox_ref:
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "outcome cursor mailbox differs from commit")
        if self.cursor.last_event_seq != self.committed.mailbox_seq:
            _fail(MailboxV2ErrorCode.INVALID_SEQUENCE, "outcome cursor sequence differs from commit")
        if self.cursor.last_event_id != self.committed.event_id:
            _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "outcome cursor event differs from commit")
        if self.cursor.last_event_digest != self.committed.event_digest:
            _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "outcome cursor digest differs from commit")

    def to_dict(self) -> dict[str, Any]:
        """Return only machine evidence needed by the next dispatch boundary."""

        return {
            "committed": self.committed.to_dict(),
            "cursor": self.cursor.to_dict(),
        }


def _write_receipt(committed: DispatchCommitted) -> WriteReceipt:
    """Adapt committed evidence to the repository exact-readback contract."""

    return WriteReceipt(
        mailbox_ref=committed.mailbox_ref,
        event_id=committed.event_id,
        event_seq=committed.mailbox_seq,
        message_id=committed.message_id,
        envelope_digest=committed.envelope_digest,
        event_digest=committed.event_digest,
        idempotent=True,
    )


def _verified_event(
    snapshot: MailboxSnapshot,
    committed: DispatchCommitted,
    envelope: V2MailboxEnvelope,
) -> MailboxEvent:
    """Return the exact event named by the committed seq/digest evidence."""

    if not isinstance(snapshot, MailboxSnapshot):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "mailbox exact readback is not a snapshot")
    if snapshot.mailbox_ref != committed.mailbox_ref:
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "mailbox readback reference differs from commit")
    event = next(
        (candidate for candidate in snapshot.events if candidate.event_id == committed.event_id),
        None,
    )
    if event is None:
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "exact readback omitted the committed event")
    if not isinstance(event, MailboxEvent):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "exact readback committed event is invalid")
    if (
        event.mailbox_ref != committed.mailbox_ref
        or event.event_seq != committed.mailbox_seq
        or event.envelope_digest != committed.envelope_digest
        or event.event_digest != committed.event_digest
        or event.envelope != envelope
        or event.logical_seq != envelope.seq
        or event.producer_namespace != envelope.producer_namespace
        or event.idempotency_key != envelope.idempotency_key
    ):
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "exact readback event binding differs from commit")
    return event


def _acknowledge_event_cursor(
    repository: MailboxRepository,
    event: MailboxEvent,
) -> MailboxActorCursor:
    """Advance and exact-check the durable producer cursor for one event."""

    envelope = event.envelope
    current = repository.read_cursor(
        event.mailbox_ref,
        envelope.run_id,
        envelope.node_id,
        event.producer_namespace,
    )
    if not isinstance(current, MailboxActorCursor):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "repository returned an invalid actor cursor")

    # A retry may observe a cursor that already consumed this event together
    # with a later event from the same producer.  Never move such a cursor back.
    if (
        current.last_event_seq > event.event_seq
        and current.last_logical_seq > event.logical_seq
    ):
        candidate = current
    else:
        candidate = current.observe(event)

    acknowledged = repository.acknowledge_cursor(candidate)
    if not isinstance(acknowledged, MailboxActorCursor):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "repository returned an invalid acknowledged cursor")
    if acknowledged != candidate:
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "durable cursor readback differs from candidate")
    return acknowledged


def dispatch_v2_with_cursor(
    protocol: DispatchProtocol,
    prepared: DispatchPrepared,
    envelope: V2MailboxEnvelope,
    *,
    committed_at: str,
) -> MailboxDispatchOutcome:
    """Commit one v2 request and acknowledge its durable Controller cursor.

    ``DispatchProtocol.dispatch`` is the first stateful operation and enforces
    repository CAS → exact readback → ``DispatchCommitted``.  This function then
    exact-reads the returned receipt again at the WP2 boundary, validates the
    returned sequence/digests against the envelope, and only then updates the
    durable producer cursor.  No notification callback is accepted or invoked.
    """

    if not isinstance(protocol, DispatchProtocol):
        raise TaskControllerValidationError("dispatch requires DispatchProtocol")
    if not isinstance(prepared, DispatchPrepared):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "dispatch requires DispatchPrepared")
    if not isinstance(envelope, V2MailboxEnvelope):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "dispatch requires a v2 envelope")

    committed = protocol.dispatch(prepared, envelope, committed_at=committed_at)
    if not isinstance(committed, DispatchCommitted):
        _fail(MailboxV2ErrorCode.SCHEMA_INVALID, "dispatch protocol returned an invalid commit")
    if committed.readback_verified is not True:
        _fail(
            MailboxV2ErrorCode.DIGEST_MISMATCH,
            "dispatch protocol returned an unverified commit",
        )
    if committed.envelope_digest != envelope.digest():
        _fail(MailboxV2ErrorCode.DIGEST_MISMATCH, "commit envelope digest differs from request")
    if committed.message_id != envelope.to_dict().get("message_id"):
        _fail(MailboxV2ErrorCode.CONTRACT_MISMATCH, "commit message ID differs from request")

    repository = protocol.repository
    receipt = _write_receipt(committed)
    snapshot = repository.exact_readback(receipt)
    event = _verified_event(snapshot, committed, envelope)
    cursor = _acknowledge_event_cursor(repository, event)
    return MailboxDispatchOutcome(committed=committed, cursor=cursor)


__all__ = ["MailboxDispatchOutcome", "dispatch_v2_with_cursor"]
