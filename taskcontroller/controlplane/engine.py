"""WP5 S2 control-plane engine: bounded intents through existing authority (NO GWC).

The engine is the SOLE mutation entrypoint. It never bypasses WP1 transition
tables or WP2 CAS/version authority:

- PAUSE   -> kernel.control.pause (RUNNING -> PAUSED)
- RESUME  -> validate_run_transition(PAUSED|BLOCKED -> RUNNING); run status to RUNNING
- CANCEL  -> kernel.control.cancel (non-terminal -> CANCELLED; DONE nodes preserved)
- REPLAN  -> kernel.control.replan (requires new_plan_version != current; non-terminal)

All state writes go through ``store.put_run(new_state, expected_version)`` so a stale
``expected_version`` raises StaleVersionError (CAS) and produces ZERO partial mutation.
Terminal runs fail closed (kernel raises; mapped to TerminalRunError where appropriate).
Idempotency: a repeated ``command_id`` returns the prior result without re-applying.

The engine does NOT dispatch work and does NOT call any execution adapter (WP5 only
projects + controls; no intent in scope requires adapter dispatch).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from taskcontroller.domain.enums import RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.kernel.control import cancel, pause, replan
from taskcontroller.kernel.control import _replace_run_status as _set_run_status
from taskcontroller.kernel.errors import (
    KernelError,
    ReplanPreconditionError,
    TransitionRejected,
)
from taskcontroller.kernel.transitions import validate_run_transition
from taskcontroller.runtime.errors import ConcurrentStateError
from taskcontroller.runtime.runtime_state import VersionedRunState

from taskcontroller.controlplane.errors import (
    ControlPlaneError,
    StaleVersionError,
    TerminalRunError,
)
from taskcontroller.controlplane.intents import ControlIntent, ControlResult


def _resume(state: TeamRunState) -> TeamRunState:
    """PAUSED/BLOCKED -> RUNNING without touching node state."""
    validate_run_transition(state.status, RunStatus.RUNNING.value)
    return _set_run_status(state, RunStatus.RUNNING.value)


@dataclass
class ControlEngine:
    """CAS-backed control-plane engine bound to one store snapshot source."""

    store: Any  # StateStore (InMemoryStateStore)

    def __post_init__(self) -> None:
        # per-engine idempotency log: command_id -> ControlResult
        self._applied: dict[str, ControlResult] = {}

    def apply(self, intent: ControlIntent) -> ControlResult:
        """Apply one bounded intent under CAS; returns a normalized result."""
        # idempotency: repeat command_id => prior result (no re-application)
        if intent.command_id is not None and intent.command_id in self._applied:
            return self._applied[intent.command_id]

        current = self.store.get_run(intent.run_id)
        if current is None:
            raise ControlPlaneError(f"no such run: {intent.run_id!r}")

        # CAS guard first: a stale expected_version must fail before any mutation.
        if current.version != intent.expected_version:
            raise StaleVersionError(
                f"stale expected_version {intent.expected_version} "
                f"!= live {current.version} for {intent.run_id!r}"
            )

        try:
            new_state = self._compute_new_state(intent, current)
        except TransitionRejected as exc:
            # terminal / illegal run transition => fail closed, typed
            raise TerminalRunError(str(exc)) from exc
        except (ReplanPreconditionError, KernelError) as exc:
            raise ControlPlaneError(str(exc)) from exc

        # commit under CAS (expected_version already matched above; store re-checks)
        try:
            committed = self.store.put_run(new_state, intent.expected_version)
        except ConcurrentStateError as exc:
            raise StaleVersionError(str(exc)) from exc

        result = ControlResult(
            intent=intent.intent,
            run_id=intent.run_id,
            accepted=True,
            new_version=committed.version,
            status=committed.state.status,
            command_id=intent.command_id,
        )
        if intent.command_id is not None:
            self._applied[intent.command_id] = result
        return result

    def _compute_new_state(self, intent: ControlIntent, current: VersionedRunState) -> VersionedRunState:
        state = current.state
        if intent.intent == "PAUSE":
            ns = pause(state)
        elif intent.intent == "RESUME":
            ns = _resume(state)
        elif intent.intent in ("CANCEL", "STOP"):
            ns = cancel(state, list(intent.contracts) if intent.contracts else None)
        elif intent.intent == "REPLAN":
            if intent.new_plan_version is None:
                raise ControlPlaneError("REPLAN requires new_plan_version")
            ns = replan(
                state,
                list(intent.contracts) if intent.contracts else [],
                intent.new_plan_version,
            )
        else:  # pragma: no cover - validated at construction
            from taskcontroller.controlplane.errors import UnknownIntentError

            raise UnknownIntentError(f"unknown intent {intent.intent!r}")

        return VersionedRunState(
            state=ns, version=current.version + 1, meta=current.meta
        )
