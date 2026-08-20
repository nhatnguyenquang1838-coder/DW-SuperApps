"""Projection dataclasses produced by the deterministic reducer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .events import RunProjectionEvent


@dataclass
class NodeState:
    node: str
    status: str = "pending"  # pending | active | done | blocked
    last_event_seq: int = -1


@dataclass
class GateState:
    gate: str
    status: str = "none"  # none | approved | released
    approved_by: Optional[str] = None
    released_by: Optional[str] = None
    last_event_seq: int = -1


@dataclass
class Projection:
    """Deterministic snapshot of a run's projected state.

    `events` are stored sorted by (ts, seq) — the canonical ordering the
    reducer guarantees. Equality is structural so golden comparisons are exact.
    """

    run_id: Optional[str]
    events: List[RunProjectionEvent] = field(default_factory=list)
    nodes: Dict[str, NodeState] = field(default_factory=dict)
    gates: Dict[str, GateState] = field(default_factory=dict)
    started_at: Optional[str] = None
    last_event_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "last_event_at": self.last_event_at,
            "events": [self._event_to_dict(e) for e in self.events],
            "nodes": {
                k: {"node": v.node, "status": v.status, "last_event_seq": v.last_event_seq}
                for k, v in sorted(self.nodes.items())
            },
            "gates": {
                k: {
                    "gate": v.gate,
                    "status": v.status,
                    "approved_by": v.approved_by,
                    "released_by": v.released_by,
                    "last_event_seq": v.last_event_seq,
                }
                for k, v in sorted(self.gates.items())
            },
        }

    @staticmethod
    def _event_to_dict(e: RunProjectionEvent) -> dict:
        return {
            "kind": e.kind,
            "ts": e.ts,
            "seq": e.seq,
            "run_id": e.run_id,
            "node": e.node,
            "gate": e.gate,
            "actor": e.actor,
            "data": e.data,
        }
