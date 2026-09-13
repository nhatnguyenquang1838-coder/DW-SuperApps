"""TC-MBX-804: deterministic terminal-signal race resolution.

This module is a pure Controller policy seam.  It consumes durable, identity-bound
signals and returns one terminal winner plus evidence-only observations.  It does
not read a wall clock, mutate a lease/manifest/mailbox, invoke a provider, or
activate fan-out.

The policy is deliberately explicit:

* only signals for the current run/node/attempt/generation can compete;
* the highest durable logical sequence wins;
* equal sequences use the canonical signal priority
  ``cancellation -> timeout -> lease_expiry -> terminal_child`` and then
  lexicographic ``signal_id``;
* once a winner is committed, every later or duplicate signal is evidence-only.

A caller commits the returned winner through ``commit_terminal_race``.  Keeping
selection and commit separate makes the conditional-write boundary visible to
higher-level adapters without introducing a second state store here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, NoReturn

from taskcontroller.execution.fanout import ChildLifecycle


_ID_RE = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SIGNAL_FIELDS = frozenset(
    {
        "signal_id",
        "kind",
        "run_id",
        "node_id",
        "attempt_id",
        "lease_generation",
        "logical_seq",
        "child_status",
        "evidence_ref",
    }
)


class TerminalRaceError(ValueError):
    """Fail-closed error for malformed or conflicting race input."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        failed_checks: tuple[str, ...] = (),
    ) -> None:
        self.code = code
        self.failed_checks = tuple(failed_checks)
        super().__init__(f"{code}: {message}")


class TerminalSignalKind(str, Enum):
    """Terminal signals that may compete for one current execution."""

    CANCELLATION = "CANCELLATION"
    TIMEOUT = "TIMEOUT"
    LEASE_EXPIRY = "LEASE_EXPIRY"
    CHILD_TERMINAL = "CHILD_TERMINAL"


class TerminalRaceDisposition(str, Enum):
    """Normalized terminal disposition selected by the race policy."""

    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    CHILD_TERMINAL = "CHILD_TERMINAL"


# Lower rank wins only when durable logical sequence is equal.
_SIGNAL_PRIORITY = {
    TerminalSignalKind.CANCELLATION: 0,
    TerminalSignalKind.TIMEOUT: 1,
    TerminalSignalKind.LEASE_EXPIRY: 2,
    TerminalSignalKind.CHILD_TERMINAL: 3,
}
_TERMINAL_CHILD_STATES = frozenset(
    {
        ChildLifecycle.SUCCEEDED,
        ChildLifecycle.FAILED,
        ChildLifecycle.TIMED_OUT,
        ChildLifecycle.CANCELLED,
    }
)


def _fail(
    code: str,
    message: str,
    *,
    failed_checks: tuple[str, ...] = (),
) -> NoReturn:
    raise TerminalRaceError(code, message, failed_checks=failed_checks)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        _fail("SCHEMA_INVALID", f"{field} must be a non-empty text value")
    return value.strip()


def _identifier(value: Any, field: str) -> str:
    normalized = _text(value, field)
    if _ID_RE.fullmatch(normalized) is None:
        _fail("SCHEMA_INVALID", f"{field} must be a stable identifier")
    return normalized


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("SCHEMA_INVALID", f"{field} must be a non-negative integer")
    return value


def _positive_sequence(value: Any, field: str) -> int:
    sequence = _non_negative_int(value, field)
    if sequence == 0:
        _fail("INVALID_SEQUENCE", f"{field} must be greater than zero")
    return sequence


def _kind(value: TerminalSignalKind | str) -> TerminalSignalKind:
    try:
        return value if isinstance(value, TerminalSignalKind) else TerminalSignalKind(value)
    except (TypeError, ValueError) as exc:
        _fail("SCHEMA_INVALID", f"kind is not supported: {exc}")
    raise AssertionError("_fail must raise")


def _child_state(value: ChildLifecycle | str) -> ChildLifecycle:
    try:
        return value if isinstance(value, ChildLifecycle) else ChildLifecycle(value)
    except (TypeError, ValueError) as exc:
        _fail("SCHEMA_INVALID", f"child_status is not supported: {exc}")
    raise AssertionError("_fail must raise")


@dataclass(frozen=True, slots=True)
class TerminalRaceIdentity:
    """Current execution identity and last accepted durable logical sequence."""

    run_id: str
    node_id: str
    attempt_id: str
    lease_generation: int
    logical_cursor: int = 0

    def __post_init__(self) -> None:
        for field in ("run_id", "node_id", "attempt_id"):
            object.__setattr__(self, field, _identifier(getattr(self, field), field))
        object.__setattr__(
            self,
            "lease_generation",
            _non_negative_int(self.lease_generation, "lease_generation"),
        )
        object.__setattr__(
            self,
            "logical_cursor",
            _non_negative_int(self.logical_cursor, "logical_cursor"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt_id": self.attempt_id,
            "lease_generation": self.lease_generation,
            "logical_cursor": self.logical_cursor,
        }


@dataclass(frozen=True, slots=True)
class TerminalRaceSignal:
    """One immutable, identity-bound terminal signal."""

    signal_id: str
    kind: TerminalSignalKind | str
    run_id: str
    node_id: str
    attempt_id: str
    lease_generation: int
    logical_seq: int
    child_status: ChildLifecycle | str | None = None
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_id", _identifier(self.signal_id, "signal_id"))
        selected_kind = _kind(self.kind)
        object.__setattr__(self, "kind", selected_kind)
        for field in ("run_id", "node_id", "attempt_id"):
            object.__setattr__(self, field, _identifier(getattr(self, field), field))
        object.__setattr__(
            self,
            "lease_generation",
            _non_negative_int(self.lease_generation, "lease_generation"),
        )
        object.__setattr__(
            self,
            "logical_seq",
            _positive_sequence(self.logical_seq, "logical_seq"),
        )

        if selected_kind is TerminalSignalKind.CHILD_TERMINAL:
            if self.child_status is None:
                _fail("SCHEMA_INVALID", "child_status is required for CHILD_TERMINAL")
            selected_child_status = _child_state(self.child_status)
            if selected_child_status not in _TERMINAL_CHILD_STATES:
                _fail(
                    "SCHEMA_INVALID",
                    "CHILD_TERMINAL requires a current terminal child status",
                )
            object.__setattr__(self, "child_status", selected_child_status)
        elif self.child_status is not None:
            _fail("SCHEMA_INVALID", "child_status is only valid for CHILD_TERMINAL")

        if self.evidence_ref is not None:
            object.__setattr__(self, "evidence_ref", _text(self.evidence_ref, "evidence_ref"))

    @property
    def disposition(self) -> TerminalRaceDisposition:
        selected_kind = _kind(self.kind)
        return {
            TerminalSignalKind.CANCELLATION: TerminalRaceDisposition.CANCELLED,
            TerminalSignalKind.TIMEOUT: TerminalRaceDisposition.TIMED_OUT,
            TerminalSignalKind.LEASE_EXPIRY: TerminalRaceDisposition.LEASE_EXPIRED,
            TerminalSignalKind.CHILD_TERMINAL: TerminalRaceDisposition.CHILD_TERMINAL,
        }[selected_kind]

    def to_dict(self) -> dict[str, Any]:
        selected_kind = _kind(self.kind)
        payload: dict[str, Any] = {
            "signal_id": self.signal_id,
            "kind": selected_kind.value,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt_id": self.attempt_id,
            "lease_generation": self.lease_generation,
            "logical_seq": self.logical_seq,
        }
        if self.child_status is not None:
            payload["child_status"] = _child_state(self.child_status).value
        if self.evidence_ref is not None:
            payload["evidence_ref"] = self.evidence_ref
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TerminalRaceSignal":
        if not isinstance(value, Mapping):
            _fail("SCHEMA_INVALID", "signal must be an object")
        candidate = dict(value)
        missing = {
            "signal_id",
            "kind",
            "run_id",
            "node_id",
            "attempt_id",
            "lease_generation",
            "logical_seq",
        } - set(candidate)
        unknown = sorted(set(candidate) - _SIGNAL_FIELDS)
        if missing:
            _fail("SCHEMA_INVALID", "signal is missing: " + ", ".join(sorted(missing)))
        if unknown:
            _fail("SCHEMA_INVALID", "unsupported signal fields: " + ", ".join(unknown))
        return cls(
            signal_id=candidate["signal_id"],
            kind=candidate["kind"],
            run_id=candidate["run_id"],
            node_id=candidate["node_id"],
            attempt_id=candidate["attempt_id"],
            lease_generation=candidate["lease_generation"],
            logical_seq=candidate["logical_seq"],
            child_status=candidate.get("child_status"),
            evidence_ref=candidate.get("evidence_ref"),
        )


@dataclass(frozen=True, slots=True)
class TerminalRaceEvidence:
    """Bounded classification for a signal that cannot advance state."""

    signal_id: str
    kind: TerminalSignalKind
    logical_seq: int
    reason: str
    advances_state: bool = False
    evidence_only: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_id", _identifier(self.signal_id, "signal_id"))
        object.__setattr__(self, "kind", _kind(self.kind))
        object.__setattr__(self, "logical_seq", _positive_sequence(self.logical_seq, "logical_seq"))
        object.__setattr__(self, "reason", _identifier(self.reason, "reason"))
        if self.advances_state or not self.evidence_only:
            _fail("SCHEMA_INVALID", "race evidence must be evidence-only")

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "kind": self.kind.value,
            "logical_seq": self.logical_seq,
            "reason": self.reason,
            "advances_state": self.advances_state,
            "evidence_only": self.evidence_only,
        }


def _evidence(signal: TerminalRaceSignal, reason: str) -> TerminalRaceEvidence:
    return TerminalRaceEvidence(
        signal_id=signal.signal_id,
        kind=_kind(signal.kind),
        logical_seq=signal.logical_seq,
        reason=reason,
    )


@dataclass(frozen=True, slots=True)
class TerminalRaceDecision:
    """One selection result and every non-advancing observation."""

    winner: TerminalRaceSignal | None
    disposition: TerminalRaceDisposition | str | None
    state_advancing: bool
    evidence_only: tuple[TerminalRaceEvidence, ...] = ()

    def __post_init__(self) -> None:
        if self.winner is None:
            if self.disposition is not None or self.state_advancing:
                _fail("SCHEMA_INVALID", "a decision without a winner cannot advance")
        else:
            if not isinstance(self.winner, TerminalRaceSignal):
                _fail("SCHEMA_INVALID", "winner must be a TerminalRaceSignal")
            selected = self.disposition
            try:
                selected = (
                    selected
                    if isinstance(selected, TerminalRaceDisposition)
                    else TerminalRaceDisposition(selected)
                )
            except (TypeError, ValueError) as exc:
                _fail("SCHEMA_INVALID", f"unsupported terminal disposition: {exc}")
            if selected is not self.winner.disposition:
                _fail("SCHEMA_INVALID", "disposition does not match winner signal")
            object.__setattr__(self, "disposition", selected)
        if any(not isinstance(item, TerminalRaceEvidence) for item in self.evidence_only):
            _fail("SCHEMA_INVALID", "evidence_only must contain TerminalRaceEvidence values")

    def to_dict(self) -> dict[str, Any]:
        disposition = (
            None
            if self.disposition is None
            else TerminalRaceDisposition(self.disposition).value
        )
        return {
            "winner": self.winner.to_dict() if self.winner is not None else None,
            "disposition": disposition,
            "state_advancing": self.state_advancing,
            "evidence_only": [item.to_dict() for item in self.evidence_only],
        }


@dataclass(frozen=True, slots=True)
class TerminalRaceState:
    """Immutable current race state used by the pure selection/commit seam."""

    identity: TerminalRaceIdentity
    committed_winner: TerminalRaceSignal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, TerminalRaceIdentity):
            _fail("SCHEMA_INVALID", "identity must be a TerminalRaceIdentity")
        winner = self.committed_winner
        if winner is None:
            return
        if not isinstance(winner, TerminalRaceSignal):
            _fail("SCHEMA_INVALID", "committed_winner must be a TerminalRaceSignal")
        mismatches = _identity_mismatches(winner, self.identity)
        if mismatches:
            _fail(
                "CONTRACT_MISMATCH",
                "committed winner does not match current identity",
                failed_checks=mismatches,
            )
        if winner.logical_seq > self.identity.logical_cursor:
            _fail(
                "INVALID_SEQUENCE",
                "committed winner cannot be newer than the current logical cursor",
            )

    @property
    def terminal_disposition(self) -> TerminalRaceDisposition | None:
        return self.committed_winner.disposition if self.committed_winner else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "committed_winner": (
                self.committed_winner.to_dict() if self.committed_winner is not None else None
            ),
        }


def _identity_mismatches(
    signal: TerminalRaceSignal,
    identity: TerminalRaceIdentity,
) -> tuple[str, ...]:
    failed: list[str] = []
    for field in ("run_id", "node_id", "attempt_id", "lease_generation"):
        if getattr(signal, field) != getattr(identity, field):
            failed.append(field)
    return tuple(failed)


def _coerce_signal(value: TerminalRaceSignal | Mapping[str, Any]) -> TerminalRaceSignal:
    if isinstance(value, TerminalRaceSignal):
        return value
    if isinstance(value, Mapping):
        return TerminalRaceSignal.from_dict(value)
    _fail("SCHEMA_INVALID", "signals must contain TerminalRaceSignal values or objects")
    raise AssertionError("_fail must raise")


def _classify_ineligible(
    signal: TerminalRaceSignal,
    identity: TerminalRaceIdentity,
) -> str | None:
    mismatches = _identity_mismatches(signal, identity)
    if "run_id" in mismatches or "node_id" in mismatches:
        return "FOREIGN_IDENTITY"
    if "attempt_id" in mismatches:
        return "ATTEMPT_MISMATCH"
    if "lease_generation" in mismatches:
        return "STALE_GENERATION"
    if signal.logical_seq <= identity.logical_cursor:
        return "STALE_SEQUENCE"
    return None


def _winner_key(signal: TerminalRaceSignal) -> tuple[int, int, str]:
    return (
        -signal.logical_seq,
        _SIGNAL_PRIORITY[_kind(signal.kind)],
        signal.signal_id,
    )


def resolve_terminal_race(
    state: TerminalRaceState,
    signals: Sequence[TerminalRaceSignal | Mapping[str, Any]],
) -> TerminalRaceDecision:
    """Select one winner and classify all other signals as evidence-only.

    The function is deterministic for the same state and signal set.  A durable
    committed winner seals the race: a later signal never replaces it, even when
    that later signal has a higher sequence.  Before commit, the highest
    durable sequence wins; a same-sequence tie uses the canonical priority and
    signal ID ordering described in the module docstring.
    """

    if not isinstance(state, TerminalRaceState):
        _fail("SCHEMA_INVALID", "state must be a TerminalRaceState")
    if isinstance(signals, (str, bytes, bytearray, Mapping)) or not isinstance(signals, Sequence):
        _fail("SCHEMA_INVALID", "signals must be a non-empty array")
    if not signals:
        _fail("EMPTY_ELIGIBLE_INPUT", "at least one terminal signal is required")

    normalized: list[TerminalRaceSignal] = []
    evidence: list[TerminalRaceEvidence] = []
    seen: dict[str, TerminalRaceSignal] = {}
    for raw in signals:
        signal = _coerce_signal(raw)
        prior = seen.get(signal.signal_id)
        if prior is not None:
            if prior != signal:
                _fail(
                    "IDEMPOTENCY_CONFLICT",
                    f"conflicting duplicate signal_id: {signal.signal_id}",
                    failed_checks=("signal_id",),
                )
            evidence.append(_evidence(signal, "DUPLICATE_SIGNAL"))
            continue
        seen[signal.signal_id] = signal
        normalized.append(signal)

    if state.committed_winner is not None:
        for signal in normalized:
            if signal == state.committed_winner:
                reason = "DUPLICATE_SIGNAL"
            else:
                reason = _classify_ineligible(signal, state.identity) or "LATE_AFTER_COMMIT"
            evidence.append(_evidence(signal, reason))
        evidence.sort(key=lambda item: (item.logical_seq, item.reason, item.signal_id))
        winner = state.committed_winner
        return TerminalRaceDecision(
            winner=winner,
            disposition=winner.disposition,
            state_advancing=False,
            evidence_only=tuple(evidence),
        )

    eligible: list[TerminalRaceSignal] = []
    for signal in normalized:
        reason = _classify_ineligible(signal, state.identity)
        if reason is None:
            eligible.append(signal)
        else:
            evidence.append(_evidence(signal, reason))

    if not eligible:
        return TerminalRaceDecision(
            winner=None,
            disposition=None,
            state_advancing=False,
            evidence_only=tuple(evidence),
        )

    winner = sorted(eligible, key=_winner_key)[0]
    for signal in eligible:
        if signal != winner:
            evidence.append(_evidence(signal, "RACE_LOSER"))
    evidence.sort(key=lambda item: (item.logical_seq, item.reason, item.signal_id))
    return TerminalRaceDecision(
        winner=winner,
        disposition=winner.disposition,
        state_advancing=True,
        evidence_only=tuple(evidence),
    )


def commit_terminal_race(
    state: TerminalRaceState,
    decision: TerminalRaceDecision,
) -> TerminalRaceState:
    """Return the next immutable state after a successful conditional commit."""

    if not isinstance(state, TerminalRaceState):
        _fail("SCHEMA_INVALID", "state must be a TerminalRaceState")
    if not isinstance(decision, TerminalRaceDecision):
        _fail("SCHEMA_INVALID", "decision must be a TerminalRaceDecision")
    if not decision.state_advancing:
        return state
    winner = decision.winner
    if winner is None:  # pragma: no cover - guarded by TerminalRaceDecision
        _fail("NO_WINNER", "state-advancing decision requires a winner")
    if state.committed_winner is not None:
        _fail("TERMINAL_ALREADY_COMMITTED", "terminal race is already committed")
    assert winner is not None
    mismatches = _identity_mismatches(winner, state.identity)
    if mismatches:
        _fail(
            "CONTRACT_MISMATCH",
            "winner does not match current identity",
            failed_checks=mismatches,
        )
    if winner.logical_seq <= state.identity.logical_cursor:
        _fail("INVALID_SEQUENCE", "winner sequence is not newer than the current cursor")
    return TerminalRaceState(
        identity=replace(state.identity, logical_cursor=winner.logical_seq),
        committed_winner=winner,
    )


__all__ = [
    "TerminalRaceDecision",
    "TerminalRaceDisposition",
    "TerminalRaceError",
    "TerminalRaceEvidence",
    "TerminalRaceIdentity",
    "TerminalRaceSignal",
    "TerminalRaceState",
    "TerminalSignalKind",
    "commit_terminal_race",
    "resolve_terminal_race",
]
