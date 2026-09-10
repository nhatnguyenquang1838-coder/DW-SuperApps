"""Controller-facing mailbox port for the additive mailbox/v2 boundary.

The controller depends on this narrow repository port instead of a
transport-specific mailbox representation.  GitHub adapters, when added, must
implement ``MailboxRepository`` and remain outside the TaskController kernel.
"""

from __future__ import annotations

from typing import Any, Mapping, Tuple

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_repository import (
    EnvelopeInput,
    MailboxEvent,
    MailboxRepository,
    MailboxSnapshot,
    WriteReceipt,
)


class TaskControllerMailbox:
    """Injectable controller boundary over a ``MailboxRepository``.

    This façade intentionally delegates persistence semantics to the repository:
    CAS, idempotency, exact readback, cursor scanning, quarantine and capability
    discovery stay in one transport-neutral contract.
    """

    def __init__(self, repository: MailboxRepository) -> None:
        if not isinstance(repository, MailboxRepository):
            raise TaskControllerValidationError(
                "TaskControllerMailbox requires a MailboxRepository implementation"
            )
        self._repository = repository

    @property
    def repository(self) -> MailboxRepository:
        """Return the injected repository boundary for composition/testing."""

        return self._repository

    def capabilities(self) -> Mapping[str, Any]:
        """Return the repository's advertised protocol capabilities."""

        return dict(self._repository.capabilities())

    def read(self, mailbox_ref: str) -> MailboxSnapshot:
        """Read the deterministic accepted snapshot for one mailbox."""

        return self._repository.read(mailbox_ref)

    def write(
        self,
        mailbox_ref: str,
        expected_seq: int,
        envelope: EnvelopeInput,
        *,
        expected_identity: Mapping[str, Any] | None = None,
    ) -> WriteReceipt:
        """Append through the repository's monotonic CAS boundary."""

        return self._repository.write(
            mailbox_ref,
            expected_seq,
            envelope,
            expected_identity=expected_identity,
        )

    def exact_readback(self, receipt: WriteReceipt) -> MailboxSnapshot:
        """Verify and return the exact repository write readback."""

        return self._repository.exact_readback(receipt)

    def scan_after(self, mailbox_ref: str, cursor: int) -> Tuple[MailboxEvent, ...]:
        """Return repository events strictly newer than ``cursor``."""

        return self._repository.scan_after(mailbox_ref, cursor)


__all__ = ["TaskControllerMailbox"]
