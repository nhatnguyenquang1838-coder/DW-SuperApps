"""Committed-dispatch gate for pointer-only wakeups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.wakeup import WakeupSignal
from taskcontroller.runtime.dispatch_ledger import DispatchCommitted


WAKEUP_EMITTED = "EMITTED"
WAKEUP_DUPLICATE = "DUPLICATE"


@dataclass(frozen=True)
class WakeupDecision:
    """Projection result; the signal carries no executable task payload."""

    status: str
    dispatch_id: str
    mailbox_ref: str
    mailbox_seq: int
    envelope_digest: str
    event_digest: str
    signal: WakeupSignal | None

    def __post_init__(self) -> None:
        if self.status not in {WAKEUP_EMITTED, WAKEUP_DUPLICATE}:
            raise TaskControllerValidationError(f"unsupported wakeup decision: {self.status!r}")
        if not isinstance(self.dispatch_id, str) or not self.dispatch_id:
            raise TaskControllerValidationError("wakeup decision dispatch_id must be non-empty")
        if not isinstance(self.mailbox_ref, str) or not self.mailbox_ref:
            raise TaskControllerValidationError("wakeup decision mailbox_ref must be non-empty")
        if isinstance(self.mailbox_seq, bool) or not isinstance(self.mailbox_seq, int) or self.mailbox_seq < 0:
            raise TaskControllerValidationError("wakeup decision mailbox_seq must be int >= 0")
        if not isinstance(self.envelope_digest, str) or not self.envelope_digest:
            raise TaskControllerValidationError("wakeup decision envelope_digest must be non-empty")
        if not isinstance(self.event_digest, str) or not self.event_digest:
            raise TaskControllerValidationError("wakeup decision event_digest must be non-empty")
        if self.status == WAKEUP_EMITTED and not isinstance(self.signal, WakeupSignal):
            raise TaskControllerValidationError("EMITTED wakeup decision requires a signal")
        if self.status == WAKEUP_DUPLICATE and self.signal is not None:
            raise TaskControllerValidationError("DUPLICATE wakeup decision cannot emit a second signal")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status,
            "dispatch_id": self.dispatch_id,
            "mailbox_ref": self.mailbox_ref,
            "mailbox_seq": self.mailbox_seq,
            "envelope_digest": self.envelope_digest,
            "event_digest": self.event_digest,
        }
        if self.signal is not None:
            result["signal"] = self.signal.to_dict()
        return result


class WakeupGate:
    """Allow one pointer-only wakeup per committed logical dispatch."""

    def __init__(self) -> None:
        self._issued_dispatches: set[str] = set()

    def issue(
        self,
        committed: DispatchCommitted,
        *,
        sender: str,
        recipient: str,
        updated_at: str,
    ) -> WakeupDecision:
        """Issue a v1 pointer only after exact-readback-backed commit evidence."""

        if not isinstance(committed, DispatchCommitted):
            raise TaskControllerValidationError(
                "wakeup requires DispatchCommitted exact-readback evidence"
            )
        dispatch_id = committed.committed_id
        if dispatch_id in self._issued_dispatches:
            return WakeupDecision(
                status=WAKEUP_DUPLICATE,
                dispatch_id=dispatch_id,
                mailbox_ref=committed.mailbox_ref,
                mailbox_seq=committed.mailbox_seq,
                envelope_digest=committed.envelope_digest,
                event_digest=committed.event_digest,
                signal=None,
            )

        signal = WakeupSignal(
            run_id=committed.run_id,
            sender=sender,
            recipient=recipient,
            mailbox_ref=committed.mailbox_ref,
            # The v2 repository's event sequence is zero-based; the existing
            # v1 pointer contract is one-based (seq must be > 0).  Keep the
            # exact v2 sequence in WakeupDecision and apply only this adapter
            # projection at the compatibility boundary.
            seq=committed.mailbox_seq + 1,
            updated_at=updated_at,
        )
        self._issued_dispatches.add(dispatch_id)
        return WakeupDecision(
            status=WAKEUP_EMITTED,
            dispatch_id=dispatch_id,
            mailbox_ref=committed.mailbox_ref,
            mailbox_seq=committed.mailbox_seq,
            envelope_digest=committed.envelope_digest,
            event_digest=committed.event_digest,
            signal=signal,
        )


__all__ = [
    "WAKEUP_DUPLICATE",
    "WAKEUP_EMITTED",
    "WakeupDecision",
    "WakeupGate",
]
