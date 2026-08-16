from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from taskcontroller.audit.event import AuditEvent


class AuditFacade(ABC):
    @abstractmethod
    def emit(self, event: AuditEvent) -> None:
        """Persist a single audit event."""

    def log_checkpoint(self, run_id: str, checkpoint: str, summary: str) -> None:
        """Convenience wrapper for checkpoint audit."""
        raise NotImplementedError

    def log_external_action(
        self,
        source: str,
        before: dict[str, Any],
        after: dict[str, Any],
        authority_ref: str = "",
        evidence_refs: tuple[str, ...] = (),
    ) -> None:
        """Convenience wrapper for external-action audit."""
        raise NotImplementedError


class NoOpAuditFacade(AuditFacade):
    """Zero-cost facade for tests and pure-library contexts."""

    def emit(self, event: AuditEvent) -> None:
        pass

    def log_checkpoint(self, run_id: str, checkpoint: str, summary: str) -> None:
        pass

    def log_external_action(
        self,
        source: str,
        before: dict[str, Any],
        after: dict[str, Any],
        authority_ref: str = "",
        evidence_refs: tuple[str, ...] = (),
    ) -> None:
        pass
