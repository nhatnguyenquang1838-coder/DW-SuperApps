"""Deterministic reducer: RunProjectionEvent[] -> Projection.

Pure function. Given the same ordered input, it always produces the same
Projection. No wall-clock, no randomness, no I/O. Ordering is normalized to
(occurred_at, sequence) on ingest so callers need not pre-sort.

Replay safety:
  - DUPLICATE: events sharing the same (source_system, source_event_id) are
    collapsed to a single canonical record (first occurrence wins; the event
    stream preserves exact source identity so reviewers can see the dup).
  - STALE: an event whose (occurred_at, sequence) is older than the current
    high-water mark is still retained in the ordered stream but does not
    move forward gate/node state that has already advanced past it.
  - GAP: missing sequence numbers do not break reduction; the reducer keys off
    the explicit sequence, not contiguous numbering.
"""

from __future__ import annotations

from typing import Iterable, List

from .events import RunProjectionEvent
from .projection import GateState, NodeState, Projection


def reduce(events: Iterable[RunProjectionEvent]) -> Projection:
    """Fold an event stream into a Projection deterministically."""
    ordered: List[RunProjectionEvent] = sorted(
        events, key=lambda e: (e.occurred_at, e.sequence, e.source_event_id or "")
    )

    # De-duplicate by exact source identity while preserving order.
    seen: set = set()
    deduped: List[RunProjectionEvent] = []
    for e in ordered:
        key = (e.source_system, e.source_event_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    proj = Projection(run_id=None)
    proj.events = deduped

    for e in deduped:
        if proj.run_id is None and e.run_id is not None:
            proj.run_id = e.run_id
        proj.last_event_at = e.occurred_at

        if e.event_type == "run_started":
            proj.started_at = e.occurred_at
            if e.run_id is not None:
                proj.run_id = e.run_id
        elif e.event_type == "gate_approved":
            if e.gate:
                g = proj.gates.setdefault(e.gate, GateState(gate=e.gate))
                # Do not regress an already-advanced state (stale handling).
                if g.last_event_seq <= e.sequence or g.status in (None, "none"):
                    g.status = "approved"
                    g.approved_by = e.actor
                    g.authority_ref = e.authority_ref
                    g.last_event_seq = e.sequence
        elif e.event_type == "gate_released":
            if e.gate:
                g = proj.gates.setdefault(e.gate, GateState(gate=e.gate))
                if g.last_event_seq <= e.sequence or g.status in (None, "none"):
                    g.status = "released"
                    g.released_by = e.actor
                    g.authority_ref = e.authority_ref
                    g.last_event_seq = e.sequence
        elif e.event_type == "node_progress":
            if e.node_id:
                n = proj.nodes.setdefault(e.node_id, NodeState(node=e.node_id))
                # Stale handling: only advance when newer or unset.
                if n.last_event_seq <= e.sequence or n.status == "pending":
                    n.status = str(e.outcome or (e.after or {}).get("status", n.status))
                    n.last_event_seq = e.sequence
        # projection_snapshot: observation-only; no state mutation.
    return proj
