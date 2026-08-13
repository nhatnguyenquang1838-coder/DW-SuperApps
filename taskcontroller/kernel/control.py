"""WP1 deterministic control ops over TeamRunState (NO GWC, framework-neutral).

Pause / cancel / replan + the "can release new work" gate. All operations
are pure functions over WP0 dataclasses.
"""

from __future__ import annotations

from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.domain.values import NodeState
from taskcontroller.kernel.errors import KernelError, ReplanPreconditionError, TransitionRejected
from taskcontroller.kernel.transitions import is_run_terminal

# Runs that release no new work (READY->CLAIMED is gated by this).
_NO_NEW_WORK = {
    RunStatus.COMPLETED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
    RunStatus.PAUSED.value,
    RunStatus.PLANNED.value,
    RunStatus.CREATED.value,
}


def can_release_new_work(run_state: TeamRunState) -> bool:
    """True only when run.status == RUNNING."""
    return run_state.status == RunStatus.RUNNING.value


def pause(run_state: TeamRunState) -> TeamRunState:
    """RUNNING -> PAUSED (validated). DONE nodes untouched."""
    if run_state.status != RunStatus.RUNNING.value:
        raise TransitionRejected(
            reason="expected RUNNING to pause",
            current=run_state.status,
            target=RunStatus.PAUSED.value,
        )
    return _replace_run_status(run_state, RunStatus.PAUSED.value)


def cancel(run_state: TeamRunState, contracts: list | None = None) -> TeamRunState:
    """Non-terminal run -> CANCELLED; all non-terminal nodes forced CANCELLED.
    DONE nodes untouched."""
    _require_non_terminal(run_state)
    new_nodes = {
        nid: ns if ns.status == NodeStatus.DONE.value else _make_cancelled_node(ns)
        for nid, ns in run_state.nodes.items()
    }
    return TeamRunState(
        run_id=run_state.run_id,
        status=RunStatus.CANCELLED.value,
        nodes=new_nodes,
        active_attempts=list(run_state.active_attempts),
        active_leases=list(run_state.active_leases),
        artifact_refs=list(run_state.artifact_refs),
        last_event_cursor=run_state.last_event_cursor,
        checkpoint=run_state.checkpoint,
        plan_version=run_state.plan_version,
        run_version=run_state.run_version,
        updated_at=run_state.updated_at,
    )


def replan(
    run_state: TeamRunState,
    contracts: list,
    new_plan_version: str,
    new_run_version: str | None = None,
) -> TeamRunState:
    """Replan selects a new plan_version (and optional run_version) WITHOUT
    rewriting completed historical state.

    Preconditions:
    - run.status in {CREATED, PLANNED, RUNNING, PAUSED, BLOCKED} (FAILED/COMPLETED/CANCELLED rejected
      with ReplanPreconditionError)
    - new_plan_version != current plan_version
    - DONE nodes preserved verbatim (NodeState + artifact_refs)
    - non-terminal nodes reset to PENDING
    - run returns to RUNNING
    """
    # ReplanPreconditionError for FAILED/COMPLETED/CANCELLED (before general terminal check)
    cur = run_state.status
    if cur == RunStatus.FAILED.value:
        raise ReplanPreconditionError("replan on FAILED run is illegal; FAILED stays terminal")
    if cur == RunStatus.COMPLETED.value:
        raise ReplanPreconditionError("replan on COMPLETED run is illegal")
    if cur == RunStatus.CANCELLED.value:
        raise ReplanPreconditionError("replan on CANCELLED run is illegal")

    _require_non_terminal(run_state)

    cv = getattr(run_state, "plan_version", "") or ""
    if new_plan_version == cv:
        raise KernelError("replan requires new_plan_version != current")

    new_rv = new_run_version if new_run_version is not None else (getattr(run_state, "run_version", "") or "")

    # Preserve DONE nodes; reset non-terminal nodes to PENDING.
    new_nodes: dict[str, NodeState] = {}
    for nid, ns in run_state.nodes.items():
        if ns.status == NodeStatus.DONE.value:
            new_nodes[nid] = ns  # immutable preserve
        else:
            new_nodes[nid] = _make_pending_node(ns)

    return TeamRunState(
        run_id=run_state.run_id,
        status=RunStatus.RUNNING.value,
        nodes=new_nodes,
        active_attempts=list(run_state.active_attempts),
        active_leases=list(run_state.active_leases),
        artifact_refs=list(run_state.artifact_refs),
        last_event_cursor=run_state.last_event_cursor,
        checkpoint=run_state.checkpoint,
        plan_version=new_plan_version,
        run_version=new_rv,
        updated_at=run_state.updated_at,
    )


def _require_non_terminal(run_state: TeamRunState) -> None:
    if is_run_terminal(run_state.status):
        raise TransitionRejected(
            reason="cannot operate on terminal run",
            current=run_state.status,
            target=None,
        )


def _replace_run_status(run_state: TeamRunState, new_status: str) -> TeamRunState:
    return TeamRunState(
        run_id=run_state.run_id,
        status=new_status,
        nodes=run_state.nodes,
        active_attempts=list(run_state.active_attempts),
        active_leases=list(run_state.active_leases),
        artifact_refs=list(run_state.artifact_refs),
        last_event_cursor=run_state.last_event_cursor,
        checkpoint=run_state.checkpoint,
        plan_version=run_state.plan_version,
        run_version=run_state.run_version,
        updated_at=run_state.updated_at,
    )


def _make_cancelled_node(ns: NodeState) -> NodeState:
    """Force a node to CANCELLED, preserving contract_ref and artifact_refs."""
    return NodeState(
        status=NodeStatus.CANCELLED.value,
        contract_ref=ns.contract_ref,
        current_attempt=ns.current_attempt,
        lease_ref=ns.lease_ref,
        artifact_refs=list(ns.artifact_refs or []),
    )


def _make_pending_node(ns: NodeState) -> NodeState:
    """Reset a non-terminal node's status to PENDING, preserving contract_ref
    and artifact_refs."""
    return NodeState(
        status=NodeStatus.PENDING.value,
        contract_ref=ns.contract_ref,
        current_attempt=ns.current_attempt,
        lease_ref=ns.lease_ref,
        artifact_refs=list(ns.artifact_refs or []),
    )