"""WP6 S3 interaction mapping / authority boundary (NO GWC, NO transport).

Maps a UI/Slack action payload to either:
- a WP5 typed ControlIntent (PAUSE/RESUME/CANCEL/REPLAN) carrying the caller-
  supplied expected_version + command_id, OR
- an authority-only projection result for APPROVE/MERGE (MUST NOT mutate WP5
  runtime; the adapter only emits an AUTHORITY_REQUIRED projection signal).

Unknown actions fail closed. The mapping is pure: it builds intents/results but
never calls the engine or any transport, so a stale expected_version is passed
through untouched to WP5 CAS (which rejects it) — the adapter must not mask it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from taskcontroller.controlplane.intents import ControlIntent

# Control actions that map directly to WP5 ControlIntent.
CONTROL_ACTIONS = ("PAUSE", "RESUME", "CANCEL", "REPLAN")
# Authority actions that must NOT mutate the runtime directly.
AUTHORITY_ACTIONS = ("APPROVE", "MERGE")


@dataclass(frozen=True)
class AuthorityResult:
    """Typed result for an authority-only action (no runtime mutation)."""

    action: str
    run_id: str
    authority_required: bool = True
    detail: str = "external authority required; runtime not mutated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "run_id": self.run_id,
            "authority_required": self.authority_required,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ActionMapping:
    """Result of mapping a UI action payload.

    Exactly one of ``control_intent`` / ``authority_result`` is set.
    """

    action: str
    run_id: str
    control_intent: ControlIntent | None = None
    authority_result: AuthorityResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "run_id": self.run_id,
            "control_intent": self.control_intent.to_dict() if self.control_intent else None,
            "authority_result": self.authority_result.to_dict() if self.authority_result else None,
        }


def map_action(
    action: str,
    run_id: str,
    expected_version: int,
    command_id: str | None = None,
    new_plan_version: str | None = None,
) -> ActionMapping:
    """Map a UI action payload to a WP5 intent or an authority-only result.

    Raises ValueError for unknown actions (fail closed).
    """
    action = action.upper()
    if action in CONTROL_ACTIONS:
        if action == "REPLAN" and new_plan_version is None:
            raise ValueError("REPLAN requires new_plan_version")
        return ActionMapping(
            action=action,
            run_id=run_id,
            control_intent=ControlIntent(
                intent=action,
                run_id=run_id,
                expected_version=expected_version,
                command_id=command_id,
                new_plan_version=new_plan_version,
            ),
        )
    if action in AUTHORITY_ACTIONS:
        return ActionMapping(
            action=action,
            run_id=run_id,
            authority_result=AuthorityResult(action=action, run_id=run_id),
        )
    raise ValueError(f"unknown action: {action!r}")
