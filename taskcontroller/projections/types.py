"""WP6 S1 generic, domain-neutral projection port types (NO GWC).

These are provider/UI-neutral. Slack (S2) is the first concrete renderer; the
types here never reference Slack. A projection is a pure, immutable view of a run
plus the operations a renderer may emit. Binding identity is the stable task/run
identity + projection target; session/model/executor metadata is mutable content
only, never part of binding identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Canonical UI task-card statuses (contract with the renderer).
class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass(frozen=True)
class ProjectionNode:
    """One ordered task card in the projection (PlanBlock -> ordered TaskCard)."""

    node_id: str
    status: TaskStatus
    label: str
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status.value,
            "label": self.label,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RunProjectionView:
    """Immutable domain/UI projection derived from a WP5 RunProjection.

    Mutable session/provider/model metadata is content, not identity.
    """

    run_id: str
    run_status: str
    version: int
    plan_version: str
    journal_position: int
    is_terminal: bool
    legal_affordances: tuple[str, ...]
    nodes: tuple[ProjectionNode, ...]  # ordered, stable by node_id
    # mutable projection metadata (content only, NOT binding identity)
    session_id: str | None = None
    model: str | None = None
    executor: str | None = None
    token_usage: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_status": self.run_status,
            "version": self.version,
            "plan_version": self.plan_version,
            "journal_position": self.journal_position,
            "is_terminal": self.is_terminal,
            "legal_affordances": list(self.legal_affordances),
            "nodes": [n.to_dict() for n in self.nodes],
            "session_id": self.session_id,
            "model": self.model,
            "executor": self.executor,
            "token_usage": self.token_usage,
        }


@dataclass(frozen=True)
class ProjectionOp:
    """A renderer operation. The renderer NEVER emits CREATE_ROOT for an existing binding."""

    op: str  # "CREATE_ROOT" | "UPDATE_ROOT" | "REPLY_THREAD"
    binding_key: str
    channel: str
    root: str | None = None  # target root/thread id for UPDATE_ROOT/REPLY_THREAD/CREATE_ROOT
    payload: dict[str, Any] = field(default_factory=dict)
    # marker for authority-only actions (APPROVE/MERGE) that must NOT mutate runtime
    authority_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "binding_key": self.binding_key,
            "channel": self.channel,
            "root": self.root,
            "payload": self.payload,
            "authority_required": self.authority_required,
        }
