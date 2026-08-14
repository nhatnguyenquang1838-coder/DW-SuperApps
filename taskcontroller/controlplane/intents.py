"""WP5 S2 typed control intents + results (NO GWC).

Control intents are bounded, explicit commands over the control-plane. Each carries
the caller-supplied ``expected_version`` (CAS) and an idempotency/command identity so
the engine can fail-closed on stale snapshots and reject conflicting reuse. Results are
normalized and immutable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The only intents the control-plane may issue in WP5.
KNOWN_INTENTS = ("PAUSE", "RESUME", "CANCEL", "REPLAN")


@dataclass(frozen=True)
class ControlIntent:
    """A bounded control command.

    ``intent``  : one of KNOWN_INTENTS
    ``run_id``  : target run
    ``expected_version`` : CAS guard against stale snapshots
    ``command_id`` : caller-supplied idempotency identity (optional)
    ``new_plan_version`` : required for REPLAN (must differ from current)
    ``contracts`` : optional contracts list passed through to kernel cancel/replan
    """

    intent: str
    run_id: str
    expected_version: int
    command_id: str | None = None
    new_plan_version: str | None = None
    contracts: tuple[Any, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.intent not in KNOWN_INTENTS:
            from taskcontroller.controlplane.errors import UnknownIntentError

            raise UnknownIntentError(f"unknown control intent: {self.intent!r}")


@dataclass(frozen=True)
class ControlResult:
    """Normalized control-plane result."""

    intent: str
    run_id: str
    accepted: bool
    new_version: int | None
    status: str | None
    detail: str | None = None
    command_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "run_id": self.run_id,
            "accepted": self.accepted,
            "new_version": self.new_version,
            "status": self.status,
            "detail": self.detail,
            "command_id": self.command_id,
        }
