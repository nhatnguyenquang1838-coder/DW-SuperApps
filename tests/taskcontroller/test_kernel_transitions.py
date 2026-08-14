"""WP1 transition validation: run and node transition tables + fail-closed checks."""

from __future__ import annotations

import pytest

from taskcontroller.domain.enums import (
    NodeStatus,
    RunStatus,
)
from taskcontroller.kernel.errors import TransitionRejected
from taskcontroller.kernel.transitions import (
    _NODE_TERMINAL,
    _RUN_TERMINAL,
    is_node_terminal,
    is_run_terminal,
    validate_node_transition,
    validate_run_transition,
)


# ---------------------------------------------------------------------------
# Run-level transition table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "current,target,allowed",
    [
        # CREATED -> PLANNED, CANCELLED
        (RunStatus.CREATED.value, RunStatus.PLANNED.value, True),
        (RunStatus.CREATED.value, RunStatus.CANCELLED.value, True),
        (RunStatus.CREATED.value, RunStatus.RUNNING.value, False),
        (RunStatus.CREATED.value, RunStatus.FAILED.value, False),
        # PLANNED -> RUNNING, CANCELLED
        (RunStatus.PLANNED.value, RunStatus.RUNNING.value, True),
        (RunStatus.PLANNED.value, RunStatus.CANCELLED.value, True),
        (RunStatus.PLANNED.value, RunStatus.PAUSED.value, False),
        # RUNNING -> PAUSED, BLOCKED, COMPLETED, FAILED, CANCELLED
        (RunStatus.RUNNING.value, RunStatus.PAUSED.value, True),
        (RunStatus.RUNNING.value, RunStatus.BLOCKED.value, True),
        (RunStatus.RUNNING.value, RunStatus.COMPLETED.value, True),
        (RunStatus.RUNNING.value, RunStatus.FAILED.value, True),
        (RunStatus.RUNNING.value, RunStatus.CANCELLED.value, True),
        (RunStatus.RUNNING.value, RunStatus.PLANNED.value, False),
        # PAUSED -> RUNNING, CANCELLED
        (RunStatus.PAUSED.value, RunStatus.RUNNING.value, True),
        (RunStatus.PAUSED.value, RunStatus.CANCELLED.value, True),
        (RunStatus.PAUSED.value, RunStatus.BLOCKED.value, False),
        # BLOCKED -> RUNNING, CANCELLED
        (RunStatus.BLOCKED.value, RunStatus.RUNNING.value, True),
        (RunStatus.BLOCKED.value, RunStatus.CANCELLED.value, True),
        (RunStatus.BLOCKED.value, RunStatus.PAUSED.value, False),
        # Terminal: no outgoing
        (RunStatus.COMPLETED.value, RunStatus.RUNNING.value, False),
        (RunStatus.COMPLETED.value, RunStatus.CANCELLED.value, False),
        (RunStatus.FAILED.value, RunStatus.RUNNING.value, False),
        (RunStatus.CANCELLED.value, RunStatus.RUNNING.value, False),
    ],
)
def test_run_transition_table(current, target, allowed):
    if allowed:
        validate_run_transition(current, target)
    else:
        with pytest.raises(TransitionRejected):
            validate_run_transition(current, target)


def test_run_terminal_states_reject_all_outgoing():
    for terminal in _RUN_TERMINAL:
        for target in (RunStatus.RUNNING.value, RunStatus.PAUSED.value, RunStatus.CANCELLED.value):
            with pytest.raises(TransitionRejected):
                validate_run_transition(terminal, target)


def test_run_terminal_predicate():
    assert is_run_terminal(RunStatus.COMPLETED.value) is True
    assert is_run_terminal(RunStatus.FAILED.value) is True
    assert is_run_terminal(RunStatus.CANCELLED.value) is True
    assert is_run_terminal(RunStatus.RUNNING.value) is False
    assert is_run_terminal(RunStatus.PAUSED.value) is False
    assert is_run_terminal(RunStatus.PLANNED.value) is False
    assert is_run_terminal(RunStatus.CREATED.value) is False
    assert is_run_terminal(RunStatus.BLOCKED.value) is False


# ---------------------------------------------------------------------------
# Node-level transition table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "current,target,allowed",
    [
        # PENDING -> READY, BLOCKED, CANCELLED
        (NodeStatus.PENDING.value, NodeStatus.READY.value, True),
        (NodeStatus.PENDING.value, NodeStatus.BLOCKED.value, True),
        (NodeStatus.PENDING.value, NodeStatus.CANCELLED.value, True),
        (NodeStatus.PENDING.value, NodeStatus.RUNNING.value, False),
        (NodeStatus.PENDING.value, NodeStatus.DONE.value, False),
        # READY -> CLAIMED, CANCELLED
        (NodeStatus.READY.value, NodeStatus.CLAIMED.value, True),
        (NodeStatus.READY.value, NodeStatus.CANCELLED.value, True),
        (NodeStatus.READY.value, NodeStatus.RUNNING.value, False),
        # CLAIMED -> RUNNING, CANCELLED, LEASE_EXPIRED
        (NodeStatus.CLAIMED.value, NodeStatus.RUNNING.value, True),
        (NodeStatus.CLAIMED.value, NodeStatus.CANCELLED.value, True),
        (NodeStatus.CLAIMED.value, NodeStatus.LEASE_EXPIRED.value, True),
        (NodeStatus.CLAIMED.value, NodeStatus.DONE.value, False),
        # RUNNING -> REVIEWING, FAILED, CANCELLED, LEASE_EXPIRED
        (NodeStatus.RUNNING.value, NodeStatus.REVIEWING.value, True),
        (NodeStatus.RUNNING.value, NodeStatus.FAILED.value, True),
        (NodeStatus.RUNNING.value, NodeStatus.CANCELLED.value, True),
        (NodeStatus.RUNNING.value, NodeStatus.LEASE_EXPIRED.value, True),
        (NodeStatus.RUNNING.value, NodeStatus.DONE.value, False),
        (NodeStatus.RUNNING.value, NodeStatus.READY.value, False),
        # REVIEWING -> DONE, FAILED, RETRY_READY, CANCELLED
        (NodeStatus.REVIEWING.value, NodeStatus.DONE.value, True),
        (NodeStatus.REVIEWING.value, NodeStatus.FAILED.value, True),
        (NodeStatus.REVIEWING.value, NodeStatus.RETRY_READY.value, True),
        (NodeStatus.REVIEWING.value, NodeStatus.CANCELLED.value, True),
        (NodeStatus.REVIEWING.value, NodeStatus.RUNNING.value, False),
        # DONE -> terminal, no outgoing
        (NodeStatus.DONE.value, NodeStatus.RUNNING.value, False),
        (NodeStatus.DONE.value, NodeStatus.REVIEWING.value, False),
        (NodeStatus.DONE.value, NodeStatus.FAILED.value, False),
        # BLOCKED -> READY, CANCELLED
        (NodeStatus.BLOCKED.value, NodeStatus.READY.value, True),
        (NodeStatus.BLOCKED.value, NodeStatus.CANCELLED.value, True),
        (NodeStatus.BLOCKED.value, NodeStatus.RUNNING.value, False),
        # FAILED -> RETRY_READY, CANCELLED
        (NodeStatus.FAILED.value, NodeStatus.RETRY_READY.value, True),
        (NodeStatus.FAILED.value, NodeStatus.CANCELLED.value, True),
        (NodeStatus.FAILED.value, NodeStatus.RUNNING.value, False),
        (NodeStatus.FAILED.value, NodeStatus.DONE.value, False),
        # RETRY_READY -> PENDING, READY, CANCELLED
        (NodeStatus.RETRY_READY.value, NodeStatus.PENDING.value, True),
        (NodeStatus.RETRY_READY.value, NodeStatus.READY.value, True),
        (NodeStatus.RETRY_READY.value, NodeStatus.CANCELLED.value, True),
        (NodeStatus.RETRY_READY.value, NodeStatus.RUNNING.value, False),
        (NodeStatus.RETRY_READY.value, NodeStatus.DONE.value, False),
        # LEASE_EXPIRED -> RETRY_READY, CANCELLED
        (NodeStatus.LEASE_EXPIRED.value, NodeStatus.RETRY_READY.value, True),
        (NodeStatus.LEASE_EXPIRED.value, NodeStatus.CANCELLED.value, True),
        (NodeStatus.LEASE_EXPIRED.value, NodeStatus.RUNNING.value, False),
        (NodeStatus.LEASE_EXPIRED.value, NodeStatus.DONE.value, False),
        # CANCELLED -> terminal, no outgoing
        (NodeStatus.CANCELLED.value, NodeStatus.RUNNING.value, False),
        (NodeStatus.CANCELLED.value, NodeStatus.PENDING.value, False),
    ],
)
def test_node_transition_table(current, target, allowed):
    if allowed:
        validate_node_transition(current, target)
    else:
        with pytest.raises(TransitionRejected):
            validate_node_transition(current, target)


def test_node_terminal_states_reject_all_outgoing():
    for terminal in _NODE_TERMINAL:
        for target in (
            NodeStatus.RUNNING.value,
            NodeStatus.REVIEWING.value,
            NodeStatus.DONE.value,
            NodeStatus.READY.value,
        ):
            with pytest.raises(TransitionRejected):
                validate_node_transition(terminal, target)


def test_node_terminal_predicate():
    assert is_node_terminal(NodeStatus.DONE.value) is True
    assert is_node_terminal(NodeStatus.CANCELLED.value) is True
    assert is_node_terminal(NodeStatus.RUNNING.value) is False
    assert is_node_terminal(NodeStatus.PENDING.value) is False
    assert is_node_terminal(NodeStatus.REVIEWING.value) is False
    assert is_node_terminal(NodeStatus.FAILED.value) is False
    assert is_node_terminal(NodeStatus.RETRY_READY.value) is False
    assert is_node_terminal(NodeStatus.LEASE_EXPIRED.value) is False
    assert is_node_terminal(NodeStatus.BLOCKED.value) is False


def test_invalid_status_string_raises():
    with pytest.raises(ValueError):
        validate_run_transition("NOT_A_REAL_STATUS", RunStatus.RUNNING.value)
    with pytest.raises(ValueError):
        validate_node_transition("NOT_A_REAL_STATUS", NodeStatus.RUNNING.value)
