"""WP1 deterministic run/node transition tables + validation (fail-closed)."""

from __future__ import annotations

from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.kernel.errors import TransitionRejected

# Run-level transitions (source → set of legal targets).
_RUN_TRANSITIONS: dict[str, set[str]] = {
    RunStatus.CREATED.value: {RunStatus.PLANNED.value, RunStatus.CANCELLED.value},
    RunStatus.PLANNED.value: {RunStatus.RUNNING.value, RunStatus.CANCELLED.value},
    RunStatus.RUNNING.value: {
        RunStatus.PAUSED.value,
        RunStatus.BLOCKED.value,
        RunStatus.COMPLETED.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    },
    RunStatus.PAUSED.value: {RunStatus.RUNNING.value, RunStatus.CANCELLED.value},
    RunStatus.BLOCKED.value: {RunStatus.RUNNING.value, RunStatus.CANCELLED.value},
    RunStatus.COMPLETED.value: set(),
    RunStatus.FAILED.value: set(),
    RunStatus.CANCELLED.value: set(),
}

# Node-level transitions (source → set of legal targets).
_NODE_TRANSITIONS: dict[str, set[str]] = {
    NodeStatus.PENDING.value: {NodeStatus.READY.value, NodeStatus.BLOCKED.value, NodeStatus.CANCELLED.value},
    NodeStatus.READY.value: {NodeStatus.CLAIMED.value, NodeStatus.CANCELLED.value},
    NodeStatus.CLAIMED.value: {NodeStatus.RUNNING.value, NodeStatus.CANCELLED.value, NodeStatus.LEASE_EXPIRED.value},
    NodeStatus.RUNNING.value: {NodeStatus.REVIEWING.value, NodeStatus.FAILED.value, NodeStatus.CANCELLED.value, NodeStatus.LEASE_EXPIRED.value},
    NodeStatus.REVIEWING.value: {NodeStatus.DONE.value, NodeStatus.FAILED.value, NodeStatus.RETRY_READY.value, NodeStatus.CANCELLED.value},
    NodeStatus.DONE.value: set(),
    NodeStatus.BLOCKED.value: {NodeStatus.READY.value, NodeStatus.CANCELLED.value},
    NodeStatus.FAILED.value: {NodeStatus.RETRY_READY.value, NodeStatus.CANCELLED.value},
    NodeStatus.RETRY_READY.value: {NodeStatus.PENDING.value, NodeStatus.READY.value, NodeStatus.CANCELLED.value},
    NodeStatus.LEASE_EXPIRED.value: {NodeStatus.RETRY_READY.value, NodeStatus.CANCELLED.value},
    NodeStatus.CANCELLED.value: set(),
}

_RUN_TERMINAL = {RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value}
_NODE_TERMINAL = {NodeStatus.DONE.value, NodeStatus.CANCELLED.value}


def validate_run_transition(current: str, target: str) -> None:
    """Fail closed: any illegal run transition raises TransitionRejected."""
    cur = RunStatus(current)
    tgt = RunStatus(target)
    allowed = _RUN_TRANSITIONS.get(cur.value, set())
    if tgt.value not in allowed:
        raise TransitionRejected(reason="no allowed transition", current=cur.value, target=tgt.value)


def validate_node_transition(current: str, target: str) -> None:
    """Fail closed: any illegal node transition raises TransitionRejected."""
    cur = NodeStatus(current)
    tgt = NodeStatus(target)
    allowed = _NODE_TRANSITIONS.get(cur.value, set())
    if tgt.value not in allowed:
        raise TransitionRejected(reason="no allowed transition", current=cur.value, target=tgt.value)


def is_run_terminal(status: str) -> bool:
    return RunStatus(status).value in _RUN_TERMINAL


def is_node_terminal(status: str) -> bool:
    return NodeStatus(status).value in _NODE_TERMINAL