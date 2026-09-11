"""Mailbox-first Executor bootstrap for pointer-only wakeups.

The entrypoint is transport-neutral: a host supplies a mailbox reader, while the
canonical mailbox envelope supplies every executable field. A WakeupSignal is
only a pointer to that envelope; an optional human/Slack projection is accepted
for caller compatibility but is never inspected or copied into the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2AEnvelope, EnvelopeKind
from taskcontroller.interaction.github_mailbox import parse_mailbox_comment
from taskcontroller.interaction.wakeup import WakeupSignal


EXECUTOR_MAILBOX_PROTOCOL = "dw.taskcontroller.executor-mailbox-entrypoint/v1"
EXECUTOR_MAILBOX_BOOTSTRAPPED = "BOOTSTRAPPED"
_EXECUTABLE_KINDS = frozenset({EnvelopeKind.COMMAND.value, EnvelopeKind.CORRECTION.value})


@runtime_checkable
class MailboxReader(Protocol):
    """Minimal host port required to exact-read one canonical mailbox record."""

    def read_mailbox(self, mailbox_ref: str) -> str:
        """Return the complete mailbox body for ``mailbox_ref``."""
        ...


@dataclass(frozen=True)
class ExecutorMailboxRequest:
    """Canonical request loaded from the mailbox named by one wakeup pointer."""

    signal: WakeupSignal
    envelope: A2AEnvelope

    def __post_init__(self) -> None:
        if not isinstance(self.signal, WakeupSignal):
            raise TaskControllerValidationError(
                "executor_mailbox_request requires WakeupSignal"
            )
        if not isinstance(self.envelope, A2AEnvelope):
            raise TaskControllerValidationError(
                "executor_mailbox_request requires A2AEnvelope"
            )
        if self.envelope.run_id != self.signal.run_id:
            raise TaskControllerValidationError(
                "executor mailbox run_id mismatch with wakeup pointer"
            )
        if self.envelope.sender != self.signal.sender:
            raise TaskControllerValidationError(
                "executor mailbox sender mismatch with wakeup pointer"
            )
        if self.envelope.recipient != self.signal.recipient:
            raise TaskControllerValidationError(
                "executor mailbox recipient mismatch with wakeup pointer"
            )
        if self.envelope.seq != self.signal.seq:
            raise TaskControllerValidationError(
                "executor mailbox sequence mismatch with wakeup pointer"
            )
        if self.envelope.kind not in _EXECUTABLE_KINDS:
            raise TaskControllerValidationError(
                "executor mailbox envelope is not executable COMMAND or CORRECTION"
            )
        if self.envelope.request is None or not self.envelope.request.strip():
            raise TaskControllerValidationError(
                "executor mailbox executable request must be non-empty"
            )

    @property
    def mailbox_ref(self) -> str:
        return self.signal.mailbox_ref

    @property
    def mailbox_seq(self) -> int:
        return self.signal.seq

    def to_dict(self) -> dict[str, Any]:
        """Return bounded bootstrap evidence without any Slack projection fields."""

        return {
            "protocol": EXECUTOR_MAILBOX_PROTOCOL,
            "status": EXECUTOR_MAILBOX_BOOTSTRAPPED,
            "run_id": self.signal.run_id,
            "sender": self.signal.sender,
            "recipient": self.signal.recipient,
            "mailbox_ref": self.mailbox_ref,
            "mailbox_seq": self.mailbox_seq,
            "envelope": self.envelope.to_dict(),
        }


class MailboxFirstExecutorEntrypoint:
    """Load one canonical Executor request from a pointer-only wakeup."""

    def __init__(self, mailbox_reader: MailboxReader, *, executor_actor: str) -> None:
        if not isinstance(mailbox_reader, MailboxReader):
            raise TaskControllerValidationError(
                "mailbox-first entrypoint requires a MailboxReader"
            )
        if not isinstance(executor_actor, str) or not executor_actor.strip():
            raise TaskControllerValidationError(
                "mailbox-first entrypoint executor_actor must be non-empty"
            )
        self._mailbox_reader = mailbox_reader
        self._executor_actor = executor_actor

    def bootstrap(
        self,
        signal: WakeupSignal,
        *,
        projection: object | None = None,
    ) -> ExecutorMailboxRequest:
        """Exact-read and validate the mailbox request named by ``signal``.

        ``projection`` is intentionally unused. It represents an optional Slack
        or human-plane rendering and has no authority over the canonical request.
        """

        if not isinstance(signal, WakeupSignal):
            raise TaskControllerValidationError(
                "mailbox-first bootstrap requires WakeupSignal"
            )
        if signal.recipient != self._executor_actor:
            raise TaskControllerValidationError(
                "executor mailbox recipient does not match entrypoint actor"
            )

        # Keep the compatibility argument visibly non-authoritative. Do not
        # validate, serialize, merge, or otherwise inspect it.
        del projection

        try:
            body = self._mailbox_reader.read_mailbox(signal.mailbox_ref)
        except Exception as exc:
            raise TaskControllerValidationError(
                "TASKCONTROLLER_EXECUTOR_MAILBOX_REJECTED: canonical mailbox read failed"
            ) from exc
        if not isinstance(body, str) or not body:
            raise TaskControllerValidationError(
                "TASKCONTROLLER_EXECUTOR_MAILBOX_REJECTED: canonical mailbox body is empty"
            )

        try:
            envelope = parse_mailbox_comment(body)
            return ExecutorMailboxRequest(signal=signal, envelope=envelope)
        except TaskControllerValidationError as exc:
            raise TaskControllerValidationError(
                "TASKCONTROLLER_EXECUTOR_MAILBOX_REJECTED: canonical mailbox "
                f"does not match wakeup pointer ({exc})"
            ) from exc


__all__ = [
    "EXECUTOR_MAILBOX_BOOTSTRAPPED",
    "EXECUTOR_MAILBOX_PROTOCOL",
    "ExecutorMailboxRequest",
    "MailboxFirstExecutorEntrypoint",
    "MailboxReader",
]
