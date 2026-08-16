"""MVP public human action model — PAUSE | STOP | APPROVE | MERGE (NO GWC).

Authority
---------
The MVP RootCard exposes exactly four contextual human actions
(``agents/chatgpt-agent/slack-controller-mvp.md`` and
``agents/shared/slack-controller-executor-protocol.md``)::

    PAUSE | STOP | APPROVE | MERGE

This module is the thin, self-contained MVP control model for that public API.
It is deliberately SEPARATE from the richer runtime verb set
(``RESUME`` / ``CANCEL`` / ``REPLAN`` in ``taskcontroller.projections.actions``
and ``taskcontroller.controlplane.intents``), which stays internal to the
deferred Full-E2E surface and is never default public MVP UI.

Hard rules upheld here
----------------------
1. NO DEFERRED-CORE DEPENDENCY. Nothing from ``controlplane`` / ``runtime`` /
   ``projections`` / ``routing`` / ``execution`` / ``packs`` is imported, so the
   MVP default path can never activate the dormant Full-E2E machinery. If a
   richer runtime adapter is ever needed to represent a safe stop, it must be
   injected through the narrow :class:`SafeBoundaryResolver` callable contract —
   the default resolver is local and pure.
2. STOP IS FIRST CLASS AND IS NOT CANCEL. ``STOP`` has its own disposition and
   its own semantics. It is never translated, aliased, mapped or degraded into
   ``CANCEL``, and it never becomes destructive cancellation implicitly.
3. NO FABRICATED COMPLETION. No action in this module can ever produce a
   ``DONE`` / ``COMPLETED`` disposition. ``STOP`` yields ``STOPPED`` and
   ``PAUSE`` yields ``PAUSED``; both are surfaced for Controller review.
4. EVIDENCE IS PRESERVED. A control action never drops, rewrites or truncates
   accumulated evidence; state transitions are additive and immutable.
5. AUTHORITY STAYS EXTERNAL. ``APPROVE`` / ``MERGE`` return an authority-required
   projection intent and mutate nothing. Action intent is not authority.
6. FAIL CLOSED. Unknown actions, an unrepresentable safe boundary, and stale
   control requests are rejected; nothing degrades to "allowed".
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from taskcontroller.errors import TaskControllerValidationError

# --------------------------------------------------------------------------
# Exact public vocabulary.
# --------------------------------------------------------------------------
PAUSE = "PAUSE"
STOP = "STOP"
APPROVE = "APPROVE"
MERGE = "MERGE"

#: The ONLY human-facing MVP actions, in contract order.
PUBLIC_ACTIONS = (PAUSE, STOP, APPROVE, MERGE)

#: Soft/hard control actions (they affect the MVP control state).
CONTROL_ACTIONS = (PAUSE, STOP)

#: Authority-only actions (they never mutate anything).
AUTHORITY_ACTIONS = (APPROVE, MERGE)

#: Richer runtime verbs that remain INTERNAL to the deferred Full-E2E surface.
#: They are never part of the public MVP API and never a STOP alias.
INTERNAL_RUNTIME_VERBS = ("RESUME", "CANCEL", "REPLAN")


class Disposition:
    """MVP control dispositions. There is deliberately no DONE/COMPLETED here."""

    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"

    ALL = (RUNNING, PAUSED, STOPPED)
    #: Dispositions that forbid starting a new meaningful work unit.
    HALTED = (PAUSED, STOPPED)


#: Dispositions this module must never be able to emit (anti-fabrication guard).
FORBIDDEN_DISPOSITIONS = ("DONE", "COMPLETED", "CANCELLED", "SUCCESS")


# --------------------------------------------------------------------------
# Narrow safe-boundary interface.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SafeBoundary:
    """A representable safe boundary: the point control may take effect at.

    ``work_unit_id`` is the currently executing meaningful unit; the boundary is
    the end of that unit. A safe boundary is a *representation* only — it starts
    nothing, stops nothing, and touches no runtime.
    """

    work_unit_id: str
    description: str

    def __post_init__(self) -> None:
        for name in ("work_unit_id", "description"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise TaskControllerValidationError(
                    f"{name} must be a non-empty string"
                )

    def to_dict(self) -> dict[str, Any]:
        return {"work_unit_id": self.work_unit_id, "description": self.description}


#: Narrow injection point. A richer runtime adapter may be supplied here, but
#: the MVP default resolver below is local, pure and activates nothing.
SafeBoundaryResolver = Callable[["MvpControlState"], SafeBoundary | None]


def default_safe_boundary(state: "MvpControlState") -> SafeBoundary | None:
    """Default MVP resolver: the end of the current work unit.

    Returns ``None`` when no current work unit exists, i.e. when a safe boundary
    cannot be represented — the caller must then fail closed.
    """
    if not state.current_work_unit:
        return None
    return SafeBoundary(
        work_unit_id=state.current_work_unit,
        description=f"end of work unit {state.current_work_unit}",
    )


class SafeBoundaryUnavailableError(TaskControllerValidationError):
    """Raised when control is requested but no safe boundary is representable."""


class StaleControlRequestError(TaskControllerValidationError):
    """Raised when a control request carries a stale expected_revision."""


# --------------------------------------------------------------------------
# MVP control state (thin, immutable, additive).
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MvpControlState:
    """The thin MVP control state. Immutable; every transition returns a new one.

    This is NOT a runtime store: no CAS against a backend, no lease, no journal,
    no checkpoint. ``revision`` exists solely so a stale human click can fail
    closed.
    """

    run_id: str
    disposition: str = Disposition.RUNNING
    current_work_unit: str | None = None
    evidence: tuple[str, ...] = field(default_factory=tuple)
    revision: int = 0
    stopped_at: SafeBoundary | None = None
    paused_at: SafeBoundary | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise TaskControllerValidationError("run_id must be a non-empty string")
        if self.disposition not in Disposition.ALL:
            raise TaskControllerValidationError(
                f"invalid disposition: {self.disposition!r}; "
                f"expected one of {Disposition.ALL}"
            )
        if self.current_work_unit is not None:
            if not isinstance(self.current_work_unit, str) or not self.current_work_unit.strip():
                raise TaskControllerValidationError(
                    "current_work_unit must be a non-empty string or None"
                )
        evidence = self.evidence
        if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence):
            raise TaskControllerValidationError(
                "evidence must be a sequence of strings, not a bare string"
            )
        for item in evidence:
            if not isinstance(item, str) or not item.strip():
                raise TaskControllerValidationError(
                    "evidence entries must be non-empty strings"
                )
        object.__setattr__(self, "evidence", tuple(evidence))
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise TaskControllerValidationError("revision must be an int")
        if self.revision < 0:
            raise TaskControllerValidationError("revision must not be negative")

    # -- pure predicates -----------------------------------------------------
    @property
    def is_stopped(self) -> bool:
        return self.disposition == Disposition.STOPPED

    @property
    def is_paused(self) -> bool:
        return self.disposition == Disposition.PAUSED

    @property
    def halted(self) -> bool:
        """True when no new meaningful work unit may start."""
        return self.disposition in Disposition.HALTED

    def may_start_work_unit(self) -> bool:
        """The safe-boundary gate: a halted run starts nothing new."""
        return not self.halted

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "disposition": self.disposition,
            "current_work_unit": self.current_work_unit,
            "evidence": list(self.evidence),
            "revision": self.revision,
            "stopped_at": self.stopped_at.to_dict() if self.stopped_at else None,
            "paused_at": self.paused_at.to_dict() if self.paused_at else None,
        }


class WorkUnitBlockedError(TaskControllerValidationError):
    """Raised when a new work unit is attempted on a halted (paused/stopped) run."""


def start_work_unit(state: MvpControlState, work_unit_id: str) -> MvpControlState:
    """Start a new meaningful work unit, honouring the safe-boundary gate.

    Fails closed on a halted run: after ``STOP`` (or ``PAUSE``) no new
    meaningful mutation/work unit may start. Existing evidence is preserved.
    """
    if not isinstance(work_unit_id, str) or not work_unit_id.strip():
        raise TaskControllerValidationError("work_unit_id must be a non-empty string")
    if state.halted:
        raise WorkUnitBlockedError(
            f"run {state.run_id!r} is {state.disposition}; no new work unit may start "
            f"(requested {work_unit_id!r})"
        )
    return replace(
        state,
        current_work_unit=work_unit_id,
        revision=state.revision + 1,
    )


# --------------------------------------------------------------------------
# Action request / result.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class PublicActionRequest:
    """One human RootCard action click. Intent only — never authority."""

    action: str
    run_id: str
    expected_revision: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or self.action not in PUBLIC_ACTIONS:
            raise TaskControllerValidationError(
                f"unknown or non-public action: {self.action!r}; "
                f"the public MVP API is exactly {PUBLIC_ACTIONS}"
            )
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise TaskControllerValidationError("run_id must be a non-empty string")
        if self.expected_revision is not None:
            if isinstance(self.expected_revision, bool) or not isinstance(
                self.expected_revision, int
            ):
                raise TaskControllerValidationError(
                    "expected_revision must be an int or None"
                )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PublicActionRequest":
        if not isinstance(payload, Mapping):
            raise TaskControllerValidationError("action payload must be a mapping")
        return cls(
            action=payload.get("action", ""),
            run_id=payload.get("run_id", ""),
            expected_revision=payload.get("expected_revision"),
        )


@dataclass(frozen=True)
class PublicActionResult:
    """The outcome of one public action.

    ``authority_required`` is set for ``APPROVE`` / ``MERGE`` only, and in that
    case ``runtime_mutated`` is ``False`` and ``state`` is the caller's state
    object unchanged (identity preserved).
    """

    action: str
    run_id: str
    state: MvpControlState
    disposition: str
    detail: str
    authority_required: bool = False
    runtime_mutated: bool = False
    boundary: SafeBoundary | None = None

    def __post_init__(self) -> None:
        if self.action not in PUBLIC_ACTIONS:
            raise TaskControllerValidationError(f"invalid action: {self.action!r}")
        if self.disposition in FORBIDDEN_DISPOSITIONS:
            raise TaskControllerValidationError(
                f"MVP action model must never emit disposition {self.disposition!r}"
            )
        if self.disposition not in Disposition.ALL:
            raise TaskControllerValidationError(
                f"invalid disposition: {self.disposition!r}"
            )
        if self.runtime_mutated:
            raise TaskControllerValidationError(
                "public MVP actions must never report a direct runtime mutation"
            )
        if self.authority_required and self.action not in AUTHORITY_ACTIONS:
            raise TaskControllerValidationError(
                "authority_required is only valid for APPROVE/MERGE"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "run_id": self.run_id,
            "disposition": self.disposition,
            "detail": self.detail,
            "authority_required": self.authority_required,
            "runtime_mutated": self.runtime_mutated,
            "boundary": self.boundary.to_dict() if self.boundary else None,
            "state": self.state.to_dict(),
        }


def apply_public_action(
    request: PublicActionRequest | Mapping[str, Any],
    state: MvpControlState,
    resolve_safe_boundary: SafeBoundaryResolver = default_safe_boundary,
) -> PublicActionResult:
    """Apply one public human action to the MVP control state.

    * ``PAUSE`` -> bounded pause at the next safe boundary. ``PAUSED``.
    * ``STOP``  -> hard stop at the current safe boundary. ``STOPPED``. Never
      ``CANCEL``, never destructive, never ``DONE``.
    * ``APPROVE`` / ``MERGE`` -> authority-required projection intent; the state
      object is returned unchanged (same identity).

    Fails closed: unknown action, mismatched run, stale ``expected_revision``,
    or an unrepresentable safe boundary.
    """
    if isinstance(request, Mapping):
        request = PublicActionRequest.from_payload(request)
    if not isinstance(request, PublicActionRequest):
        raise TaskControllerValidationError("request must be a PublicActionRequest")
    if not isinstance(state, MvpControlState):
        raise TaskControllerValidationError("state must be an MvpControlState")
    if request.run_id != state.run_id:
        raise TaskControllerValidationError(
            f"action targets run {request.run_id!r}, state is {state.run_id!r}"
        )
    if (
        request.expected_revision is not None
        and request.expected_revision != state.revision
    ):
        raise StaleControlRequestError(
            f"stale control request: expected_revision={request.expected_revision}, "
            f"current revision={state.revision}"
        )

    if request.action in AUTHORITY_ACTIONS:
        return PublicActionResult(
            action=request.action,
            run_id=state.run_id,
            state=state,  # identity preserved: zero mutation
            disposition=state.disposition,
            detail=(
                f"{request.action} is an authority-only projection intent; "
                "runtime not mutated, not approved, not merged"
            ),
            authority_required=True,
        )

    boundary = resolve_safe_boundary(state)
    if boundary is None:
        raise SafeBoundaryUnavailableError(
            f"cannot represent a safe boundary for run {state.run_id!r}; "
            f"{request.action} fails closed"
        )
    if not isinstance(boundary, SafeBoundary):
        raise TaskControllerValidationError(
            "resolve_safe_boundary must return a SafeBoundary or None"
        )

    if request.action == STOP:
        new_state = replace(
            state,
            disposition=Disposition.STOPPED,
            stopped_at=boundary,
            revision=state.revision + 1,
        )
        return PublicActionResult(
            action=STOP,
            run_id=state.run_id,
            state=new_state,
            disposition=Disposition.STOPPED,
            detail=(
                "hard stop at safe boundary; no new work unit may start, existing "
                "evidence preserved, stopped disposition surfaced for Controller "
                "review; NOT a cancellation and NOT DONE"
            ),
            boundary=boundary,
        )

    # PAUSE — soft, bounded, no fabricated completion.
    new_state = replace(
        state,
        disposition=Disposition.PAUSED,
        paused_at=boundary,
        revision=state.revision + 1,
    )
    return PublicActionResult(
        action=PAUSE,
        run_id=state.run_id,
        state=new_state,
        disposition=Disposition.PAUSED,
        detail=(
            "bounded pause before the next meaningful action boundary; existing "
            "evidence preserved, no completion fabricated"
        ),
        boundary=boundary,
    )


def contextual_actions(
    state: MvpControlState,
    authority_boundary: bool = False,
    merge_ready: bool = False,
) -> tuple[str, ...]:
    """The contextual public affordances for this control state.

    ``PAUSE`` is hidden once the run is halted (nothing left to pause).
    ``STOP`` remains available while not already stopped. ``APPROVE`` /
    ``MERGE`` appear only at an exact authority / merge-ready boundary.
    ``RESUME`` / ``CANCEL`` / ``REPLAN`` are never returned.
    """
    if not isinstance(state, MvpControlState):
        raise TaskControllerValidationError("state must be an MvpControlState")
    allowed: list[str] = []
    if not state.halted:
        allowed.append(PAUSE)
    if not state.is_stopped:
        allowed.append(STOP)
    if authority_boundary:
        allowed.append(APPROVE)
    if merge_ready:
        allowed.append(MERGE)
    return tuple(a for a in PUBLIC_ACTIONS if a in allowed)
