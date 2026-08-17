"""Pointer-only notification semantic for non-polling Agent mailboxes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import MailboxCursor

WAKEUP_PROTOCOL = "dw.taskcontroller.wakeup/v1"


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(f"wakeup_signal.{name} must be non-empty")
    return value


@dataclass(frozen=True)
class WakeupSignal:
    """Announce unseen mailbox work without carrying the command payload."""

    run_id: str
    sender: str
    recipient: str
    mailbox_ref: str
    seq: int
    updated_at: str

    def __post_init__(self) -> None:
        for name in ("run_id", "sender", "recipient", "mailbox_ref", "updated_at"):
            _required_text(getattr(self, name), name)
        if not isinstance(self.seq, int) or isinstance(self.seq, bool) or self.seq <= 0:
            raise TaskControllerValidationError("wakeup_signal.seq must be int > 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": WAKEUP_PROTOCOL,
            "run_id": self.run_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "mailbox_ref": self.mailbox_ref,
            "seq": self.seq,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WakeupSignal":
        if not isinstance(payload, dict):
            raise TaskControllerValidationError("wakeup_signal payload must be an object")
        if payload.get("protocol") != WAKEUP_PROTOCOL:
            raise TaskControllerValidationError(
                f"wakeup_signal.protocol must be {WAKEUP_PROTOCOL!r}"
            )
        allowed = {
            "protocol",
            "run_id",
            "sender",
            "recipient",
            "mailbox_ref",
            "seq",
            "updated_at",
        }
        unexpected = set(payload) - allowed
        if unexpected:
            raise TaskControllerValidationError(
                "wakeup_signal contains non-pointer fields: " + ", ".join(sorted(unexpected))
            )
        try:
            return cls(
                run_id=payload["run_id"],
                sender=payload["sender"],
                recipient=payload["recipient"],
                mailbox_ref=payload["mailbox_ref"],
                seq=payload["seq"],
                updated_at=payload["updated_at"],
            )
        except KeyError as exc:
            raise TaskControllerValidationError("malformed wakeup_signal payload") from exc

    def announces_new_work(self, cursor: MailboxCursor) -> bool:
        """Return whether this notice announces unseen state in the sender mailbox."""

        if not isinstance(cursor, MailboxCursor):
            raise TaskControllerValidationError(
                "wakeup_signal.announces_new_work requires MailboxCursor"
            )
        # A recipient consumes the sender's mailbox. MailboxCursor.actor therefore
        # tracks the mailbox owner / envelope sender, not the notification recipient.
        if cursor.actor != self.sender:
            raise TaskControllerValidationError(
                "wakeup_signal sender does not match mailbox cursor actor"
            )
        if cursor.mailbox_ref is not None and cursor.mailbox_ref != self.mailbox_ref:
            raise TaskControllerValidationError(
                "wakeup_signal mailbox_ref does not match mailbox cursor"
            )
        return self.seq > cursor.last_seen_seq
