"""TC-MBX-804 hardening tests for terminal-signal races."""

from __future__ import annotations

import pytest

from taskcontroller.controlplane.terminal_race import (
    TerminalRaceError,
    TerminalRaceIdentity,
    TerminalRaceState,
    TerminalSignalKind,
    TerminalRaceDisposition,
    TerminalRaceSignal,
    commit_terminal_race,
    resolve_terminal_race,
)
from taskcontroller.execution.fanout import ChildLifecycle


_RUN = "run.1"
_NODE = "node.1"
_ATTEMPT = "attempt.2"
_GENERATION = 3


def _identity(*, logical_cursor: int = 0) -> TerminalRaceIdentity:
    return TerminalRaceIdentity(
        run_id=_RUN,
        node_id=_NODE,
        attempt_id=_ATTEMPT,
        lease_generation=_GENERATION,
        logical_cursor=logical_cursor,
    )


def _state(*, logical_cursor: int = 0) -> TerminalRaceState:
    return TerminalRaceState(identity=_identity(logical_cursor=logical_cursor))


def _signal(
    kind: TerminalSignalKind | str,
    *,
    signal_id: str,
    logical_seq: int,
    attempt_id: str = _ATTEMPT,
    lease_generation: int = _GENERATION,
    child_status: ChildLifecycle | str | None = None,
) -> TerminalRaceSignal:
    return TerminalRaceSignal(
        signal_id=signal_id,
        kind=kind,
        run_id=_RUN,
        node_id=_NODE,
        attempt_id=attempt_id,
        lease_generation=lease_generation,
        logical_seq=logical_seq,
        child_status=child_status,
    )


@pytest.mark.parametrize(
    ("first_kind", "second_kind"),
    [
        (TerminalSignalKind.CANCELLATION, TerminalSignalKind.TIMEOUT),
        (TerminalSignalKind.CANCELLATION, TerminalSignalKind.LEASE_EXPIRY),
        (TerminalSignalKind.CANCELLATION, TerminalSignalKind.CHILD_TERMINAL),
        (TerminalSignalKind.TIMEOUT, TerminalSignalKind.LEASE_EXPIRY),
        (TerminalSignalKind.TIMEOUT, TerminalSignalKind.CHILD_TERMINAL),
        (TerminalSignalKind.LEASE_EXPIRY, TerminalSignalKind.CHILD_TERMINAL),
    ],
)
def test_highest_durable_sequence_wins_each_race_pair(first_kind, second_kind) -> None:
    first = _signal(first_kind, signal_id="signal.low", logical_seq=10)
    second = _signal(
        second_kind,
        signal_id="signal.high",
        logical_seq=11,
        child_status=(ChildLifecycle.SUCCEEDED if second_kind is TerminalSignalKind.CHILD_TERMINAL else None),
    )

    decision = resolve_terminal_race(_state(), [second, first])

    assert decision.state_advancing is True
    assert decision.winner == second
    assert decision.disposition == second.disposition
    assert [item.reason for item in decision.evidence_only] == ["RACE_LOSER"]
    assert decision.evidence_only[0].signal_id == first.signal_id


def test_same_sequence_uses_kind_priority_then_signal_id() -> None:
    signals = [
        _signal(
            TerminalSignalKind.CHILD_TERMINAL,
            signal_id="signal.child",
            logical_seq=20,
            child_status=ChildLifecycle.SUCCEEDED,
        ),
        _signal(TerminalSignalKind.LEASE_EXPIRY, signal_id="signal.lease", logical_seq=20),
        _signal(TerminalSignalKind.TIMEOUT, signal_id="signal.timeout", logical_seq=20),
        _signal(TerminalSignalKind.CANCELLATION, signal_id="signal.cancel.z", logical_seq=20),
        _signal(TerminalSignalKind.CANCELLATION, signal_id="signal.cancel.a", logical_seq=20),
    ]

    decision = resolve_terminal_race(_state(), signals)

    assert decision.winner is not None
    assert decision.winner.signal_id == "signal.cancel.a"
    assert decision.disposition is TerminalRaceDisposition.CANCELLED
    assert {item.reason for item in decision.evidence_only} == {"RACE_LOSER"}


def test_duplicate_replay_is_evidence_only_and_does_not_change_winner() -> None:
    signal = _signal(TerminalSignalKind.TIMEOUT, signal_id="signal.timeout", logical_seq=4)

    decision = resolve_terminal_race(_state(), [signal, signal])

    assert decision.winner == signal
    assert decision.state_advancing is True
    assert len(decision.evidence_only) == 1
    assert decision.evidence_only[0].reason == "DUPLICATE_SIGNAL"


def test_conflicting_duplicate_signal_id_fails_closed() -> None:
    first = _signal(TerminalSignalKind.TIMEOUT, signal_id="signal.same", logical_seq=4)
    conflicting = _signal(TerminalSignalKind.CANCELLATION, signal_id="signal.same", logical_seq=5)

    with pytest.raises(TerminalRaceError) as exc:
        resolve_terminal_race(_state(), [first, conflicting])

    assert exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_committed_winner_seals_race_and_late_signal_is_evidence_only() -> None:
    winner = _signal(TerminalSignalKind.CANCELLATION, signal_id="signal.cancel", logical_seq=7)
    first = resolve_terminal_race(_state(), [winner])
    committed = commit_terminal_race(_state(), first)

    late = _signal(TerminalSignalKind.CHILD_TERMINAL, signal_id="signal.late", logical_seq=99, child_status=ChildLifecycle.SUCCEEDED)
    replay = resolve_terminal_race(committed, [late, winner])

    assert replay.winner == winner
    assert replay.disposition is TerminalRaceDisposition.CANCELLED
    assert replay.state_advancing is False
    assert [(item.signal_id, item.reason) for item in replay.evidence_only] == [
        (winner.signal_id, "DUPLICATE_SIGNAL"),
        (late.signal_id, "LATE_AFTER_COMMIT"),
    ]
    assert committed.identity.logical_cursor == 7


def test_wrong_generation_is_retained_as_evidence_only() -> None:
    stale = _signal(
        TerminalSignalKind.LEASE_EXPIRY,
        signal_id="signal.old-generation",
        logical_seq=9,
        lease_generation=2,
    )

    decision = resolve_terminal_race(_state(), [stale])

    assert decision.winner is None
    assert decision.state_advancing is False
    assert decision.evidence_only[0].reason == "STALE_GENERATION"


def test_wrong_attempt_is_rejected_from_advancement_as_evidence_only() -> None:
    foreign = _signal(
        TerminalSignalKind.TIMEOUT,
        signal_id="signal.old-attempt",
        logical_seq=9,
        attempt_id="attempt.old",
    )

    decision = resolve_terminal_race(_state(), [foreign])

    assert decision.winner is None
    assert decision.state_advancing is False
    assert decision.evidence_only[0].reason == "ATTEMPT_MISMATCH"


@pytest.mark.parametrize(
    "signals",
    [
        [],
        (),
    ],
)
def test_empty_signal_input_fails_closed(signals) -> None:
    with pytest.raises(TerminalRaceError) as exc:
        resolve_terminal_race(_state(), signals)

    assert exc.value.code == "EMPTY_ELIGIBLE_INPUT"


def test_malformed_identity_fails_closed() -> None:
    with pytest.raises(TerminalRaceError) as exc:
        TerminalRaceIdentity(run_id="", node_id=_NODE, attempt_id=_ATTEMPT, lease_generation=1)

    assert exc.value.code == "SCHEMA_INVALID"


def test_invalid_sequence_fails_closed() -> None:
    with pytest.raises(TerminalRaceError) as exc:
        _signal(TerminalSignalKind.TIMEOUT, signal_id="signal.zero", logical_seq=0)

    assert exc.value.code == "INVALID_SEQUENCE"


def test_child_terminal_requires_a_current_terminal_child_state() -> None:
    with pytest.raises(TerminalRaceError) as exc:
        _signal(
            TerminalSignalKind.CHILD_TERMINAL,
            signal_id="signal.running-child",
            logical_seq=5,
            child_status=ChildLifecycle.RUNNING,
        )

    assert exc.value.code == "SCHEMA_INVALID"


def test_commit_is_immutable_and_repeated_evaluation_cannot_advance_again() -> None:
    signal = _signal(TerminalSignalKind.TIMEOUT, signal_id="signal.timeout", logical_seq=12)
    initial = _state()
    decision = resolve_terminal_race(initial, [signal])
    committed = commit_terminal_race(initial, decision)
    repeated = commit_terminal_race(committed, resolve_terminal_race(committed, [signal]))

    assert initial.committed_winner is None
    assert committed.committed_winner == signal
    assert committed.identity.logical_cursor == 12
    assert repeated == committed
