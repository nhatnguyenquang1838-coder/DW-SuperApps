"""Deterministic reducer: RunProjectionEvent[] -> Projection.

Pure function. Given the same ordered input, it always produces the same
Projection. No wall-clock, no randomness, no I/O.

Replay contract (per Controller addendum):
  - The reducer consumes the event stream in the EXACT order supplied and keeps
    that order (it does NOT sort by occurred_at/sequence and does NOT silently
    reorder). ``RunState(N) = reduce(events[0..N])`` holds.
  - DUPLICATE / OUT-OF-ORDER / STALE / GAP are detected explicitly and recorded
    as typed ``Anomaly`` entries in ``Projection.anomalies``. They are NEVER
    silently dropped or hidden:
      * DUPLICATE   — two events share the same (source_system, source_event_id).
      * OUT_OF_ORDER— an event's supplied position runs against a divergent
                      (occurred_at, sequence) relative to the running stream.
      * STALE       — an event's (occurred_at, sequence) is behind the current
                      high-water mark but was not a duplicate.
      * GAP         — non-contiguous sequence numbers (informational; tolerated).
  The reducer advances node/gate *state* deterministically from the events in
  supplied order, applying the same monotone (no-regress) rule for stale input,
  but the underlying events and any anomaly are always retained for review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from .events import RunProjectionEvent
from .projection import Anomaly, GateState, NodeState, Projection


def reduce(events: Iterable[RunProjectionEvent]) -> Projection:
    """Fold an event stream into a Projection, preserving supplied order."""
    stream: List[RunProjectionEvent] = list(events)

    proj = Projection(run_id=None)
    proj.events = []
    proj.anomalies = []

    seen_identities: set = set()
    hw_time: Optional[str] = None
    hw_seq: int = -1

    for idx, e in enumerate(stream):
        identity = (e.source_system, e.source_event_id)

        # Explicit duplicate detection (never silently collapsed).
        if identity in seen_identities:
            proj.anomalies.append(
                Anomaly(
                    kind="DUPLICATE",
                    at_index=idx,
                    source_system=e.source_system,
                    source_event_id=e.source_event_id,
                    message=f"duplicate source identity {identity!r} at index {idx}",
                )
            )
        else:
            seen_identities.add(identity)

        # Explicit ordering/stale detection against running high-water mark.
        cur_seq = e.sequence
        if hw_time is not None:
            if (e.occurred_at, cur_seq) < (hw_time, hw_seq):
                if identity in seen_identities and idx > 0:
                    proj.anomalies.append(
                        Anomaly(
                            kind="STALE",
                            at_index=idx,
                            source_system=e.source_system,
                            source_event_id=e.source_event_id,
                            message=(
                                f"stale event at index {idx}: "
                                f"(occurred_at={e.occurred_at}, seq={cur_seq}) behind "
                                f"high-water (occurred_at={hw_time}, seq={hw_seq})"
                            ),
                        )
                    )
            elif (e.occurred_at, cur_seq) > (hw_time, hw_seq):
                # Out-of-order relative to prior stream position (informational).
                if idx > 0 and cur_seq != hw_seq + 1:
                    proj.anomalies.append(
                        Anomaly(
                            kind="OUT_OF_ORDER",
                            at_index=idx,
                            source_system=e.source_system,
                            source_event_id=e.source_event_id,
                            message=(
                                f"out-of-order event at index {idx}: "
                                f"seq={cur_seq} jumped past high-water seq={hw_seq}"
                            ),
                        )
                    )
        # Update high-water mark (monotone on (occurred_at, sequence)).
        prev_hw_seq = hw_seq
        if hw_time is None or (e.occurred_at, cur_seq) > (hw_time, hw_seq):
            hw_time, hw_seq = e.occurred_at, cur_seq

        # GAP: informational when sequence is not contiguous with prior max.
        if idx > 0 and abs(cur_seq - prev_hw_seq) > 1:
            proj.anomalies.append(
                Anomaly(
                    kind="GAP",
                    at_index=idx,
                    source_system=e.source_system,
                    source_event_id=e.source_event_id,
                    message=f"sequence gap at index {idx}: seq={cur_seq}, prior max={prev_hw_seq}",
                )
            )

        proj.events.append(e)
        if proj.run_id is None and e.run_id is not None:
            proj.run_id = e.run_id
        proj.last_event_at = e.occurred_at

        _apply_event(proj, e)

    return proj


def _apply_event(proj: Projection, e: RunProjectionEvent) -> None:
    """Advance node/gate state deterministically, monotone (no regress)."""
    if e.event_type == "run_started":
        proj.started_at = e.occurred_at
        if e.run_id is not None:
            proj.run_id = e.run_id
    elif e.event_type in ("gate_approved", "gate_passed"):
        if e.gate:
            g = proj.gates.setdefault(e.gate, GateState(gate=e.gate))
            if g.last_event_seq <= e.sequence or g.status in (None, "none"):
                g.status = "approved"
                g.approved_by = e.actor
                g.authority_ref = e.authority_ref
                g.last_event_seq = e.sequence
    elif e.event_type in ("gate_released", "gate_failed"):
        if e.gate:
            g = proj.gates.setdefault(e.gate, GateState(gate=e.gate))
            if g.last_event_seq <= e.sequence or g.status in (None, "none"):
                g.status = "released"
                g.released_by = e.actor
                g.authority_ref = e.authority_ref
                g.last_event_seq = e.sequence
    elif e.event_type in ("node_progress", "node_started", "node_completed"):
        if e.node_id:
            n = proj.nodes.setdefault(e.node_id, NodeState(node=e.node_id))
            if n.last_event_seq <= e.sequence or n.status == "pending":
                # node outcome is taken verbatim from the source (open vocab);
                # fall back to after.status when not explicitly provided.
                n.status = str(e.outcome or (e.after or {}).get("status", n.status))
                n.last_event_seq = e.sequence
    # Any other event_type (gate_passed, gate_failed, node_completed, etc.):
    # observation-only; state only advances for known transitions above.
