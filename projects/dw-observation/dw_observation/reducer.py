"""Deterministic reducer: RunProjectionEvent[] -> Projection.

Pure function. Given the same ordered input, it always produces the same
Projection. No wall-clock, no randomness, no I/O. Ordering is normalized to
(ts, seq) on ingest so callers need not pre-sort.
"""

from __future__ import annotations

from typing import Iterable, List

from .events import RunProjectionEvent
from .projection import GateState, NodeState, Projection


def reduce(events: Iterable[RunProjectionEvent]) -> Projection:
    """Fold an event stream into a Projection deterministically."""
    ordered: List[RunProjectionEvent] = sorted(
        events, key=lambda e: (e.ts, e.seq, e.kind)
    )

    proj = Projection(run_id=None)
    proj.events = ordered

    for e in ordered:
        if proj.run_id is None and e.run_id is not None:
            proj.run_id = e.run_id
        proj.last_event_at = e.ts
        if e.kind == "run_started":
            proj.started_at = e.ts
            if e.run_id is not None:
                proj.run_id = e.run_id
        elif e.kind == "gate_approved":
            if e.gate:
                g = proj.gates.setdefault(e.gate, GateState(gate=e.gate))
                g.status = "approved"
                g.approved_by = e.actor
                g.last_event_seq = e.seq
        elif e.kind == "gate_released":
            if e.gate:
                g = proj.gates.setdefault(e.gate, GateState(gate=e.gate))
                g.status = "released"
                g.released_by = e.actor
                g.last_event_seq = e.seq
        elif e.kind == "node_progress":
            if e.node:
                n = proj.nodes.setdefault(e.node, NodeState(node=e.node))
                n.status = str(e.data.get("status", n.status))
                n.last_event_seq = e.seq
        # projection_snapshot: observation-only; no state mutation.
    return proj
