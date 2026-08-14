"""WP6 S2 domain mapping: WP5 RunProjection -> domain-neutral RunProjectionView.

Pure, deterministic status mapping. No Slack/transport references here.
"""

from __future__ import annotations

from taskcontroller.controlplane.projection import RunProjection
from taskcontroller.projections.types import ProjectionNode, RunProjectionView, TaskStatus

# WP1 NodeStatus -> canonical TaskCard status
_NODE_STATUS_MAP = {
    "PENDING": TaskStatus.PENDING,
    "READY": TaskStatus.PENDING,
    "BLOCKED": TaskStatus.PENDING,
    "RETRY_READY": TaskStatus.PENDING,
    "LEASE_EXPIRED": TaskStatus.PENDING,
    "CLAIMED": TaskStatus.IN_PROGRESS,
    "RUNNING": TaskStatus.IN_PROGRESS,
    "REVIEWING": TaskStatus.IN_PROGRESS,
    "DONE": TaskStatus.COMPLETE,
    "FAILED": TaskStatus.ERROR,
    "CANCELLED": TaskStatus.ERROR,
}

# WP1 RunStatus -> root card status
_RUN_STATUS_MAP = {
    "CREATED": TaskStatus.PENDING,
    "PLANNED": TaskStatus.PENDING,
    "RUNNING": TaskStatus.IN_PROGRESS,
    "PAUSED": TaskStatus.PENDING,
    "BLOCKED": TaskStatus.PENDING,
    "COMPLETED": TaskStatus.COMPLETE,
    "FAILED": TaskStatus.ERROR,
    "CANCELLED": TaskStatus.ERROR,
}


def map_node_status(node_status: str) -> TaskStatus:
    return _NODE_STATUS_MAP.get(node_status, TaskStatus.PENDING)


def map_run_status(run_status: str) -> TaskStatus:
    return _RUN_STATUS_MAP.get(run_status, TaskStatus.PENDING)


def build_view(
    projection: RunProjection,
    session_id: str | None = None,
    model: str | None = None,
    executor: str | None = None,
    token_usage: int | None = None,
) -> RunProjectionView:
    """Map a WP5 RunProjection into the domain-neutral view (ordered stable cards)."""
    nodes = tuple(
        ProjectionNode(
            node_id=n.node_id,
            status=map_node_status(n.status),
            label=n.node_id,
            detail=n.status,
        )
        for n in projection.nodes
    )
    return RunProjectionView(
        run_id=projection.run_id,
        run_status=projection.status,
        version=projection.version,
        plan_version=projection.plan_version,
        journal_position=projection.journal_position,
        is_terminal=projection.is_terminal,
        legal_affordances=projection.legal_affordances,
        nodes=nodes,
        session_id=session_id,
        model=model,
        executor=executor,
        token_usage=token_usage,
    )
