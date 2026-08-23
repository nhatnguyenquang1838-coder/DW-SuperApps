"""Projection dataclasses produced by the deterministic reducer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .events import RunProjectionEvent, _thaw


@dataclass
class Anomaly:
    """An explicitly surfaced replay inconsistency (never hidden)."""

    kind: str  # DUPLICATE | OUT_OF_ORDER | STALE | GAP
    at_index: int
    source_system: Optional[str]
    source_event_id: Optional[str]
    message: str


@dataclass
class NodeState:
    node: str
    status: str = "pending"  # pending | active | done | blocked | (source verbatim)
    last_event_seq: int = -1


@dataclass
class GateState:
    gate: str
    status: str = "none"  # none | approved | released | passed | failed
    approved_by: Optional[object] = None  # actor (string OR structured object)
    released_by: Optional[object] = None  # actor that released the gate
    failed_by: Optional[object] = None    # actor responsible for a failure (NOT released_by)
    authority_ref: Optional[str] = None
    last_event_seq: int = -1


@dataclass
class Projection:
    """Deterministic snapshot of a run's projected state.

    `events` preserve the EXACT supplied order (the reducer does not reorder).
    `anomalies` records explicit duplicate/out-of-order/stale/gap detections.
    Equality is structural so golden comparisons are exact.
    """

    run_id: Optional[str]
    events: List[RunProjectionEvent] = field(default_factory=list)
    nodes: Dict[str, NodeState] = field(default_factory=dict)
    gates: Dict[str, GateState] = field(default_factory=dict)
    anomalies: List[Anomaly] = field(default_factory=list)
    started_at: Optional[str] = None
    last_event_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "last_event_at": self.last_event_at,
            "anomalies": [
                {
                    "kind": a.kind,
                    "at_index": a.at_index,
                    "source_system": a.source_system,
                    "source_event_id": a.source_event_id,
                    "message": a.message,
                }
                for a in self.anomalies
            ],
            "events": [self._event_to_dict(e) for e in self.events],
            "nodes": {
                k: {"node": v.node, "status": v.status, "last_event_seq": v.last_event_seq}
                for k, v in sorted(self.nodes.items())
            },
            "gates": {
                k: {
                    "gate": v.gate,
                    "status": v.status,
                    # Gate actors may be a structured GWC actor stored as an immutable
                    # MappingProxyType on the source event; thaw to a fresh ordinary
                    # JSON-compatible dict so projection output stays serializable and
                    # callers can mutate the copy without touching stored state.
                    "approved_by": _thaw(v.approved_by),
                    "released_by": _thaw(v.released_by),
                    "failed_by": _thaw(v.failed_by),
                    "authority_ref": v.authority_ref,
                    "last_event_seq": v.last_event_seq,
                }
                for k, v in sorted(self.gates.items())
            },
        }

    @staticmethod
    def _event_to_dict(e: RunProjectionEvent) -> dict:
        # Thaw the event's immutable internal forms into fresh JSON-compatible
        # containers (consistent with events.to_dict); callers may mutate the
        # returned copy without affecting the frozen event.
        return {
            "schema_version": e.schema_version,
            "projection_type": e.projection_type,
            "run_id": e.run_id,
            "sequence": e.sequence,
            "source_system": e.source_system,
            "source_event_id": e.source_event_id,
            "occurred_at": e.occurred_at,
            "gate": e.gate,
            "node_id": e.node_id,
            "parent_event_id": e.parent_event_id,
            "event_type": e.event_type,
            "outcome": e.outcome,
            "actor": _thaw(e.actor),
            "summary": e.summary,
            "before": _thaw(e.before),
            "after": _thaw(e.after),
            "evidence_refs": _thaw(e.evidence_refs),
            "authority_ref": e.authority_ref,
            "source_digest": e.source_digest,
            "read_only_projection": e.read_only_projection,
        }
