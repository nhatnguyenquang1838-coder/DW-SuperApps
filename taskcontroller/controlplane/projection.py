"""WP5 S1 deterministic control-plane projection (read model) over WP1-WP4 truth.

A pure, immutable read model built from a ``VersionedRunState``. It materializes
controller-visible state and *legal control affordances* derived from the current
run status (via the WP1 run-transition table) — never guessed. The projection is a
derived view only: it never mutates the runtime and contains no wall-clock/random/
network/GWC logic. ``to_dict`` is canonical (sorted keys, ordered node summaries)
so the same input always yields byte-equivalent output regardless of insertion order.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.kernel.transitions import _RUN_TRANSITIONS
from taskcontroller.runtime.runtime_state import VersionedRunState


# Legal control intents the control-plane may surface for a non-terminal run.
_CONTROL_INTENTS = ("PAUSE", "RESUME", "CANCEL", "REPLAN")


@dataclass(frozen=True)
class NodeSummary:
    """Ordered, stable node summary (canonical ordering by node_id)."""

    node_id: str
    status: str
    contract_ref: str | None
    current_attempt: int
    lease_ref: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.status,
            "contract_ref": self.contract_ref,
            "current_attempt": self.current_attempt,
            "lease_ref": self.lease_ref,
        }


@dataclass(frozen=True)
class RunProjection:
    """Immutable controller read model derived from ``VersionedRunState``.

    Construction is deterministic and side-effect free. ``legal_affordances`` is
    computed from the WP1 run-transition table for the current status; terminal
    runs expose an empty affordance set (no illegal action is ever suggested).
    """

    run_id: str
    status: str
    version: int
    plan_version: str
    run_version: str
    journal_position: int
    node_count: int
    node_counts_by_status: dict[str, int]
    nodes: tuple[NodeSummary, ...]  # ordered by node_id
    active_attempts: tuple[str, ...]
    active_leases: tuple[str, ...]
    has_blockers: bool
    has_reviewing: bool
    is_terminal: bool
    legal_affordances: tuple[str, ...]

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    @classmethod
    def from_versioned(cls, vr: VersionedRunState) -> "RunProjection":
        """Build the projection from a live ``VersionedRunState`` (read only)."""
        state: TeamRunState = vr.state
        status = state.status

        # node counts + ordered summaries
        counts: dict[str, int] = {}
        summaries: list[NodeSummary] = []
        blockers = 0
        reviewing = 0
        for nid in sorted(state.nodes.keys()):
            ns = state.nodes[nid]
            counts[ns.status] = counts.get(ns.status, 0) + 1
            if ns.status == NodeStatus.BLOCKED.value:
                blockers += 1
            if ns.status == NodeStatus.REVIEWING.value:
                reviewing += 1
            summaries.append(
                NodeSummary(
                    node_id=nid,
                    status=ns.status,
                    contract_ref=ns.contract_ref,
                    current_attempt=ns.current_attempt or 0,
                    lease_ref=ns.lease_ref,
                )
            )

        is_terminal = status in (
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        )

        # legal affordances derived from WP1 run-transition table + kernel intents
        if is_terminal:
            affordances: tuple[str, ...] = ()
        else:
            allowed = _RUN_TRANSITIONS.get(status, set())
            legal: list[str] = []
            # PAUSE / CANCEL map directly onto legal run transitions.
            if RunStatus.PAUSED.value in allowed:
                legal.append("PAUSE")
            if RunStatus.CANCELLED.value in allowed:
                legal.append("CANCEL")
            # RESUME is only an affordance when the run is PAUSED or BLOCKED
            # (both legitimately transition back to RUNNING).
            if status in (RunStatus.PAUSED.value, RunStatus.BLOCKED.value):
                legal.append("RESUME")
            # REPLAN is a kernel command available for any non-terminal run that
            # the kernel allows to enter a new plan (CREATED/PLANNED/RUNNING/
            # PAUSED/BLOCKED); it is not a raw run-level transition.
            if status in (
                RunStatus.CREATED.value,
                RunStatus.PLANNED.value,
                RunStatus.RUNNING.value,
                RunStatus.PAUSED.value,
                RunStatus.BLOCKED.value,
            ):
                legal.append("REPLAN")
            affordances = tuple(sorted(legal))

        journal_position = 0
        meta = vr.meta
        if isinstance(meta, dict):
            journal_position = int(meta.get("journal_position", 0) or 0)
        else:
            journal_position = int(getattr(meta, "journal_position", 0) or 0)

        return cls(
            run_id=state.run_id,
            status=status,
            version=vr.version,
            plan_version=getattr(state, "plan_version", "") or "",
            run_version=getattr(state, "run_version", "") or "",
            journal_position=journal_position,
            node_count=len(state.nodes),
            node_counts_by_status=dict(sorted(counts.items())),
            nodes=tuple(summaries),
            active_attempts=tuple(sorted(state.active_attempts)),
            active_leases=tuple(sorted(state.active_leases)),
            has_blockers=blockers > 0,
            has_reviewing=reviewing > 0,
            is_terminal=is_terminal,
            legal_affordances=affordances,
        )

    # ------------------------------------------------------------------
    # canonical serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Canonical, deterministic dict (sorted keys everywhere)."""
        return {
            "run_id": self.run_id,
            "status": self.status,
            "version": self.version,
            "plan_version": self.plan_version,
            "run_version": self.run_version,
            "journal_position": self.journal_position,
            "node_count": self.node_count,
            "node_counts_by_status": dict(sorted(self.node_counts_by_status.items())),
            "nodes": [n.to_dict() for n in self.nodes],
            "active_attempts": list(self.active_attempts),
            "active_leases": list(self.active_leases),
            "has_blockers": self.has_blockers,
            "has_reviewing": self.has_reviewing,
            "is_terminal": self.is_terminal,
            "legal_affordances": list(self.legal_affordances),
        }

    def to_canonical_json(self) -> str:
        """Byte-stable canonical JSON (sorted keys, no whitespace)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def nodes_by_status(self, status: str) -> list[str]:
        """Node ids (ordered) currently in ``status`` — convenience for assertions."""
        return [n.node_id for n in self.nodes if n.status == status]
