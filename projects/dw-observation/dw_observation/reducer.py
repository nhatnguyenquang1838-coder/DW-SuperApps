"""Deterministic reducer: RunProjectionEvent[] -> Projection.

Pure function. Given the same ordered input, it always produces the same
Projection. No wall-clock, no randomness, no I/O.

Replay contract (per Controller addendum + semantic correction):
  - The reducer consumes the event stream in the EXACT order supplied and keeps
    that order (it does NOT sort by occurred_at/sequence and does NOT silently
    reorder). ``RunState(N) = reduce(events[0..N])`` holds.
  - DUPLICATE / OUT_OF_ORDER / STALE / GAP are detected explicitly and recorded
    as typed ``Anomaly`` entries in ``Projection.anomalies``. They are NEVER
    silently dropped or hidden.
      * DUPLICATE    — two events share the same (source_system, source_event_id).
      * OUT_OF_ORDER — a supplied event's SOURCE SEQUENCE regresses relative to
                       the running high-water sequence (e.g. 3 -> 2).
      * STALE        — a non-duplicate event's (occurred_at, sequence) is behind
                       the current high-water mark.
      * GAP          — a forward non-contiguous jump in source sequence
                       (e.g. 1 -> 3). Forward jumps are GAP only, NOT out-of-order.
  The reducer advances node/gate *state* deterministically from the events in
  supplied order, applying the same monotone (no-regress) rule for stale input,
  but the underlying events and any anomaly are always retained for review.

Gate semantics (source truth preserved):
  - gate_passed   -> status "passed"
  - gate_failed   -> status "failed"   (NOT "released")
  - gate_approved -> status "approved" (TC lane approval)
  - gate_released -> status "released" (TC lane release)
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

        cur_seq = e.sequence
        # Out-of-order (regression) is decided on SOURCE SEQUENCE vs high-water.
        if idx > 0 and cur_seq < hw_seq:
            proj.anomalies.append(
                Anomaly(
                    kind="OUT_OF_ORDER",
                    at_index=idx,
                    source_system=e.source_system,
                    source_event_id=e.source_event_id,
                    message=(
                        f"source sequence regressed at index {idx}: "
                        f"seq={cur_seq} < high-water seq={hw_seq}"
                    ),
                )
            )
        # Stale: non-duplicate behind the running (occurred_at, sequence) mark.
        if hw_time is not None and (e.occurred_at, cur_seq) < (hw_time, hw_seq):
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
        # GAP: forward non-contiguous jump in source sequence (1 -> 3, etc.).
        # Forward jumps are GAP only; they are NOT out-of-order.
        if idx > 0 and cur_seq > hw_seq and cur_seq != hw_seq + 1:
            proj.anomalies.append(
                Anomaly(
                    kind="GAP",
                    at_index=idx,
                    source_system=e.source_system,
                    source_event_id=e.source_event_id,
                    message=f"sequence gap at index {idx}: seq={cur_seq}, prior max={hw_seq}",
                )
            )
        # Update high-water mark (monotone on (occurred_at, sequence)).
        if hw_time is None or (e.occurred_at, cur_seq) > (hw_time, hw_seq):
            hw_time, hw_seq = e.occurred_at, cur_seq

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
    elif e.event_type == "gate_passed":
        if e.gate:
            g = proj.gates.setdefault(e.gate, GateState(gate=e.gate))
            if g.last_event_seq <= e.sequence or g.status in (None, "none"):
                g.status = "passed"
                g.approved_by = e.actor
                g.authority_ref = e.authority_ref
                g.last_event_seq = e.sequence
    elif e.event_type == "gate_approved":
        if e.gate:
            g = proj.gates.setdefault(e.gate, GateState(gate=e.gate))
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
    elif e.event_type == "gate_failed":
        # Source truth: failure is NOT release.
        if e.gate:
            g = proj.gates.setdefault(e.gate, GateState(gate=e.gate))
            if g.last_event_seq <= e.sequence or g.status in (None, "none"):
                g.status = "failed"
                g.released_by = e.actor
                g.authority_ref = e.authority_ref
                g.last_event_seq = e.sequence
    elif e.event_type in ("node_progress", "node_started", "node_completed"):
        if e.node_id:
            n = proj.nodes.setdefault(e.node_id, NodeState(node=e.node_id))
            if n.last_event_seq <= e.sequence or n.status == "pending":
                # node outcome taken verbatim from the source (open vocab);
                # fall back to after.status when not explicitly provided.
                n.status = str(e.outcome or (e.after or {}).get("status", n.status))
                n.last_event_seq = e.sequence
    # Any other event_type (run_completed, readback_completed, etc.):
    # observation-only; state only advances for known transitions above.
