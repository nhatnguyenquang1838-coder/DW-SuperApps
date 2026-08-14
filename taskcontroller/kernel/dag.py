"""WP1 DAG validation + readiness (ALL_REQUIRED join only; WP0 has no dependency mode)."""

from __future__ import annotations

from collections import deque
from typing import Sequence

from taskcontroller.domain.enums import NodeStatus
from taskcontroller.domain.ids import TaskRef
from taskcontroller.domain.values import NodeState
from taskcontroller.kernel.errors import CycleDetectedError, UnknownDependencyError

# Node statuses that mean "dependency already satisfied" for join/blocked logic.
_DONE_STATUSES = {
    NodeStatus.DONE.value,
    NodeStatus.CANCELLED.value,
    NodeStatus.FAILED.value,
    NodeStatus.RETRY_READY.value,
}


def validate_plan(contracts: Sequence[object]) -> None:
    """Fail closed: reject cycle and unknown-dependency plans for one run.

    Each contract must expose:
      - node_id: str
      - dependencies: list[TaskRef]  (each TaskRef carries run_id + node_id)
    """
    if not contracts:
        return

    plan_nodes: dict[str, object] = {}
    for c in contracts:
        nid = str(getattr(c, "node_id"))
        plan_nodes[nid] = c

    # 1) unknown dependency detection
    for c in contracts:
        for dep in getattr(c, "dependencies", []) or []:
            dep_nid = str(dep.node_id)
            if dep_nid not in plan_nodes:
                raise UnknownDependencyError(
                    (str(getattr(c, "contract_id", "?")), dep_nid)
                )

    # 2) cycle detection (Kahn's)
    indeg: dict[str, int] = {nid: 0 for nid in plan_nodes}
    succ: dict[str, list[str]] = {nid: [] for nid in plan_nodes}
    for c in contracts:
        src = str(getattr(c, "node_id"))
        for dep in getattr(c, "dependencies", []) or []:
            dst = str(dep.node_id)
            succ[dst].append(src)
            indeg[src] += 1

    q = deque([nid for nid, deg in indeg.items() if deg == 0])
    visited = 0
    while q:
        nid = q.popleft()
        visited += 1
        for s in succ[nid]:
            indeg[s] -= 1
            if indeg[s] == 0:
                q.append(s)

    if visited != len(plan_nodes):
        raise CycleDetectedError()


def compute_readiness(
    contracts: Sequence[object],
    node_states: dict[str, NodeState] | None = None,
) -> dict[str, str]:
    """Return {node_id: readiness} for ALL contracts (even absent nodes -> PENDING).

    ALL_REQUIRED join:
      - READY when every dependency node status is in _DONE_STATUSES.
      - BLOCKED when any dependency node status is FAILED/CANCELLED,
        or when a dependency node is absent (unknown/unplanned).
      - PENDING otherwise (waiting on live dependencies, or node absent from state).
    Terminal nodes (DONE/CANCELLED/FAILED/RETRY_READY) are returned as-is.
    """
    if node_states is None:
        node_states = {}
    result: dict[str, str] = {}
    for c in contracts:
        nid = str(getattr(c, "node_id"))
        ns = node_states.get(nid)
        if ns is None:
            result[nid] = NodeStatus.PENDING.value
            continue
        result[nid] = _readiness_for_node(c, ns, node_states)
    return result


def _readiness_for_node(
    c: object,
    ns: NodeState,
    nodes: dict[str, NodeState],
) -> str:
    if ns.status in _DONE_STATUSES:
        return ns.status

    for dep in getattr(c, "dependencies", []) or []:
        dep_nid = str(dep.node_id)
        dep_ns = nodes.get(dep_nid)
        if dep_ns is None:
            return NodeStatus.BLOCKED.value
        if dep_ns.status in {NodeStatus.FAILED.value, NodeStatus.CANCELLED.value}:
            return NodeStatus.BLOCKED.value
        if dep_ns.status not in _DONE_STATUSES:
            return NodeStatus.PENDING.value

    return NodeStatus.READY.value