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
    MailboxActorCursor,
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

    def read_cursor(
        self,
        mailbox_ref: str,
        run_id: str,
        node_id: str,
        actor_namespace: str,
    ) -> MailboxActorCursor:
        """Read the durable per-actor cursor used by Controller or Executor."""

        return self._repository.read_cursor(mailbox_ref, run_id, node_id, actor_namespace)

    def scan_after_cursor(self, cursor: MailboxActorCursor) -> Tuple[MailboxEvent, ...]:
        """Return only events newer than a bound durable actor cursor."""

        return self._repository.scan_after_cursor(cursor)

    def acknowledge_cursor(self, cursor: MailboxActorCursor) -> MailboxActorCursor:
        """Persist a verified actor cursor after semantic consumption."""

        return self._repository.acknowledge_cursor(cursor)


__all__ = ["TaskControllerMailbox"]
