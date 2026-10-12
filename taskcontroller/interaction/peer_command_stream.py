"""Lightweight v1 A2A conversation sequence, separate from protected mailbox/v2.

Pure state transition: host retains responsibility for a single serialized writer,
durable append, exact readback, notification and authenticated actor identity.
No v2 approval, execution lease or fence is created by a communication command.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2AEnvelope, EnvelopeKind


@dataclass(frozen=True)
class PeerCommandReceipt:
    run_id: str
    seq: int
    sender: str
    recipient: str
    kind: str
    # Only the remote adapter can attach a real durable comment id.
    comment_id: str | None = None


def verify_peer_history(history: Sequence[A2AEnvelope], *, run_id: str) -> int:
    """Validate a single globally increasing per-run v1 command stream.

    One exchange = one A2AEnvelope; COMMAND, REPORT and CORRECTION all advance
    the same shared conversation sequence. The host must order comments by
    authenticated immutable remote order and reject concurrent/forked writes.
    """
    previous = 0
    seen = set()
    for envelope in history:
        if not isinstance(envelope, A2AEnvelope):
            raise TaskControllerValidationError("peer history requires v1 A2A envelopes")
        if envelope.run_id != run_id:
            raise TaskControllerValidationError("peer history run identity drift")
        if envelope.seq != previous + 1:
            raise TaskControllerValidationError(
                f"peer command sequence gap/fork: expected {previous + 1}, got {envelope.seq}"
            )
        if envelope.kind not in (
            EnvelopeKind.COMMAND.value, EnvelopeKind.REPORT.value,
            EnvelopeKind.CORRECTION.value, EnvelopeKind.REVIEW_REQUEST.value,
            EnvelopeKind.TERMINAL.value, EnvelopeKind.HEALTH.value,
        ):
            raise TaskControllerValidationError("unsupported v1 peer command kind")
        if envelope.sender == envelope.recipient:
            raise TaskControllerValidationError("peer self-message is invalid")
        if (envelope.sender, envelope.seq) in seen:
            raise TaskControllerValidationError("duplicate peer command")
        seen.add((envelope.sender, envelope.seq))
        previous = envelope.seq
    return previous


def build_next_peer_command(
    *,
    history: Sequence[A2AEnvelope],
    run_id: str,
    node_id: str,
    sender: str,
    recipient: str,
    kind: str,
    request: str,
    updated_at: str,
    artifact_refs: Sequence[str] = (),
    state: dict | None = None,
) -> A2AEnvelope:
    """Create the next semantic v1 command, *without* issuing execution authority."""
    last_seq = verify_peer_history(history, run_id=run_id)
    if sender == recipient:
        raise TaskControllerValidationError("sender and recipient must differ")
    if kind not in {EnvelopeKind.COMMAND.value, EnvelopeKind.REPORT.value,
                    EnvelopeKind.CORRECTION.value, EnvelopeKind.REVIEW_REQUEST.value}:
        raise TaskControllerValidationError("unsupported conversation command kind")
    if not isinstance(request, str) or not request.strip():
        raise TaskControllerValidationError("peer command must contain an actionable request/report")
    return A2AEnvelope(
        run_id=run_id,
        node_id=node_id,
        sender=sender,
        recipient=recipient,
        seq=last_seq + 1,
        kind=kind,
        request=request,
        artifact_refs=tuple(artifact_refs),
        state=dict(state or {}),
        updated_at=updated_at,
    )


def unread_after(history: Sequence[A2AEnvelope], *, run_id: str, consumed_seq: int,
                 recipient: str) -> tuple[A2AEnvelope, ...]:
    """Read without acknowledging; observation never advances consumed_seq."""
    highest = verify_peer_history(history, run_id=run_id)
    if type(consumed_seq) is not int or consumed_seq < 0 or consumed_seq > highest:
        raise TaskControllerValidationError("consumed peer cursor invalid")
    return tuple(e for e in history if e.seq > consumed_seq and e.recipient == recipient)
