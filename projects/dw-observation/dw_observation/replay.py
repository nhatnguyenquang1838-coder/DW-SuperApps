"""M3 — deterministic historical replay over the immutable projection stream.

Replay is a PURE READ over the same ordered ``RunProjectionEvent`` stream that
M0/M2 already produce. It adds no new authority, no new source of truth, and
performs no mutation: every frame is derived by folding a PREFIX of the stream
through the existing M0 reducer.

Core contract
-------------
1. ``RunState(N) = reduce(events[0..N])`` — a replay frame at cursor ``N`` is
   *exactly* the M0 projection of the first ``N`` events. There is no separate
   replay reducer, so replay can never drift from LIVE semantics.
2. Determinism: the same ordered events always produce an identical frame, and
   an identical ``replay_digest``. Nothing consults wall-clock, randomness, or
   I/O. Re-running a replay N times yields byte-identical projections.
3. Whole-screen synchronization: every visible surface (RootCard, DAG,
   CI/evidence, inspector, timeline) is projected from ONE ``ReplayFrame``.
   Surfaces cannot disagree, because they are not independently computed —
   ``SurfaceSnapshot`` is a single fan-out of one frame.
4. Duplicate / out-of-order / stale / gap behavior is inherited verbatim from
   the M0 reducer (and matches the M2 live client's anomaly vocabulary). Replay
   never hides an anomaly: a frame exposes exactly the anomalies detected within
   its own prefix.
5. LIVE resume: entering replay does NOT mutate the underlying stream or the
   source high-water marks. Frames received while rewound are appended to the
   canonical tip (never dropped, never reordered), so ``resume_live()`` returns
   to a tip whose sequence state is identical to never having replayed at all.

Cursor convention
-----------------
``cursor`` is the NUMBER OF EVENTS APPLIED, so it ranges over ``0..len(events)``:

* ``cursor = 0``            -> empty projection (run not yet observed)
* ``cursor = k``            -> ``reduce(events[:k])``
* ``cursor = len(events)``  -> the tip (equivalent to the LIVE projection)

This makes ``cursor`` a count (not an index), which removes the classic
off-by-one between "rewind to event 3" and "rewind to before event 3".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .events import RunProjectionEvent
from .projection import Anomaly, Projection
from .reducer import reduce as reduce_events

# Anomaly vocabulary shared with the M0 reducer and the M2 live client.
ANOMALY_KINDS = ("DUPLICATE", "OUT_OF_ORDER", "STALE", "GAP")

# Replay session modes.
MODE_LIVE = "LIVE"
MODE_REPLAY = "REPLAY"

# Explicit unknown sentinel (mirrors the UI's UNKNOWN) — never invent a value.
UNKNOWN = "—"


def _canonical_json(payload: Any) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayFrame:
    """An immutable deterministic snapshot of the run at one cursor position.

    A frame is self-describing: it carries the cursor, the projection folded
    from that exact prefix, and the anomalies visible within it. ``state_digest``
    is a canonical hash of the projection, so golden fixtures can pin exact
    replay state without embedding the whole projection.
    """

    cursor: int
    total: int
    projection: Projection
    anomalies: Tuple[Anomaly, ...]
    state_digest: str

    @property
    def at_tip(self) -> bool:
        """True when this frame is the newest observed state."""
        return self.cursor == self.total

    @property
    def at_start(self) -> bool:
        """True when nothing has been applied yet (empty projection)."""
        return self.cursor == 0

    @property
    def events_applied(self) -> int:
        return self.cursor

    @property
    def last_event(self) -> Optional[RunProjectionEvent]:
        """The most recent event folded into this frame (None at cursor 0)."""
        if self.cursor == 0:
            return None
        return self.projection.events[-1]

    def anomaly_kinds(self) -> Dict[str, int]:
        """Counts per anomaly kind visible in this frame (explicit, never hidden)."""
        counts = {kind: 0 for kind in ANOMALY_KINDS}
        for a in self.anomalies:
            counts[a.kind] = counts.get(a.kind, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "cursor": self.cursor,
            "total": self.total,
            "at_tip": self.at_tip,
            "at_start": self.at_start,
            "state_digest": self.state_digest,
            "projection": self.projection.to_dict(),
        }


# ---------------------------------------------------------------------------
# Timeline (pure, immutable view over an ordered stream)
# ---------------------------------------------------------------------------


class ReplayTimeline:
    """A pure, deterministic replay view over one ordered event stream.

    The timeline never mutates the events it is given (it holds its own tuple
    copy) and never reorders them: supplied order IS replay order, exactly as
    the M0 reducer requires.
    """

    def __init__(self, events: Iterable[RunProjectionEvent]) -> None:
        self._events: Tuple[RunProjectionEvent, ...] = tuple(events)

    # -- shape ------------------------------------------------------------
    @property
    def events(self) -> Tuple[RunProjectionEvent, ...]:
        return self._events

    @property
    def total(self) -> int:
        return len(self._events)

    def __len__(self) -> int:
        return len(self._events)

    @property
    def run_id(self) -> Optional[str]:
        for e in self._events:
            if e.run_id is not None:
                return e.run_id
        return None

    # -- cursors ----------------------------------------------------------
    def clamp(self, cursor: int) -> int:
        """Clamp a cursor into ``0..total`` (a rewind can never leave the run)."""
        if cursor < 0:
            return 0
        if cursor > self.total:
            return self.total
        return cursor

    def cursors(self) -> List[int]:
        """Every valid cursor position, start (0) through tip (total)."""
        return list(range(self.total + 1))

    # -- frames -----------------------------------------------------------
    def frame_at(self, cursor: int) -> ReplayFrame:
        """Fold ``events[:cursor]`` through the M0 reducer. Pure and repeatable."""
        c = self.clamp(cursor)
        proj = reduce_events(self._events[:c])
        return ReplayFrame(
            cursor=c,
            total=self.total,
            projection=proj,
            anomalies=tuple(proj.anomalies),
            state_digest=_digest(proj.to_dict()),
        )

    def tip(self) -> ReplayFrame:
        return self.frame_at(self.total)

    def start(self) -> ReplayFrame:
        return self.frame_at(0)

    def frames(self) -> List[ReplayFrame]:
        """Every frame from start to tip (the full deterministic replay)."""
        return [self.frame_at(c) for c in self.cursors()]

    # -- determinism evidence --------------------------------------------
    def replay_digest(self) -> str:
        """Canonical digest over EVERY frame's state digest, in cursor order.

        Two streams share a ``replay_digest`` only when every intermediate
        replay state matches — not merely the final state. This is the value a
        golden replay fixture pins.
        """
        return _digest(
            {
                "run_id": self.run_id,
                "total": self.total,
                "frames": [
                    {"cursor": f.cursor, "state_digest": f.state_digest}
                    for f in self.frames()
                ],
            }
        )

    def verify_determinism(self, repeats: int = 3) -> bool:
        """Re-run the whole replay ``repeats`` times; every pass must be identical."""
        if repeats < 2:
            repeats = 2
        first = [f.state_digest for f in self.frames()]
        for _ in range(repeats - 1):
            if [f.state_digest for f in self.frames()] != first:
                return False
        return True

    def rewind_sequence(self, cursors: Sequence[int]) -> List[ReplayFrame]:
        """Frames for an arbitrary rewind path (forward, backward, or jumping).

        Rewinding is stateless and order-independent: visiting cursor ``k`` always
        yields the same frame regardless of the path taken to reach it. This is
        what makes a whole-screen rewind reproducible.
        """
        return [self.frame_at(c) for c in cursors]

    def is_path_consistent(self, cursors: Sequence[int]) -> bool:
        """True when every revisit of a cursor along a path yields the same state."""
        seen: Dict[int, str] = {}
        for c in cursors:
            f = self.frame_at(c)
            if f.cursor in seen and seen[f.cursor] != f.state_digest:
                return False
            seen[f.cursor] = f.state_digest
        return True


# ---------------------------------------------------------------------------
# Surface projection (whole-screen synchronized rewind)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SurfaceSnapshot:
    """All visible surfaces projected from ONE frame, so they cannot disagree.

    The five surfaces mirror the M1/M2 UI: RootCard, DAG, timeline, CI/evidence,
    and the inspector. Each is a fan-out of the same ``ReplayFrame`` — there is
    no per-surface recomputation and therefore no way for one pane to show a
    different point in history than another.
    """

    cursor: int
    total: int
    mode: str
    state_digest: str
    root_card: Dict[str, Any]
    dag: Dict[str, Any]
    timeline: Dict[str, Any]
    evidence: Dict[str, Any]
    inspector: Dict[str, Any]

    @property
    def surfaces(self) -> Dict[str, Dict[str, Any]]:
        return {
            "root_card": self.root_card,
            "dag": self.dag,
            "timeline": self.timeline,
            "evidence": self.evidence,
            "inspector": self.inspector,
        }

    def synchronized(self) -> bool:
        """Every surface must report the same cursor AND the same state digest."""
        for s in self.surfaces.values():
            if s.get("cursor") != self.cursor:
                return False
            if s.get("state_digest") != self.state_digest:
                return False
        return True

    def to_dict(self) -> dict:
        return {
            "cursor": self.cursor,
            "total": self.total,
            "mode": self.mode,
            "state_digest": self.state_digest,
            "surfaces": self.surfaces,
        }


def project_surfaces(frame: ReplayFrame, mode: str = MODE_REPLAY) -> SurfaceSnapshot:
    """Fan one deterministic frame out to every visible surface.

    Unknown/absent source values stay explicitly UNKNOWN — replay never infers a
    value that the source stream does not carry.
    """
    proj = frame.projection
    stamp = {"cursor": frame.cursor, "state_digest": frame.state_digest}

    last = frame.last_event
    root_card = {
        **stamp,
        "run_id": proj.run_id or UNKNOWN,
        "started_at": proj.started_at or UNKNOWN,
        "last_event_at": proj.last_event_at or UNKNOWN,
        "events_applied": frame.cursor,
        "total_events": frame.total,
        "at_tip": frame.at_tip,
        "mode": mode,
        "anomaly_count": len(frame.anomalies),
    }

    dag = {
        **stamp,
        "nodes": {
            k: {"node": v.node, "status": v.status, "last_event_seq": v.last_event_seq}
            for k, v in sorted(proj.nodes.items())
        },
        "gates": {
            k: {
                "gate": v.gate,
                "status": v.status,
                "authority_ref": v.authority_ref,
                "last_event_seq": v.last_event_seq,
            }
            for k, v in sorted(proj.gates.items())
        },
    }

    timeline = {
        **stamp,
        "applied": [
            {
                "sequence": e.sequence,
                "source_system": e.source_system,
                "source_event_id": e.source_event_id,
                "event_type": e.event_type,
                "occurred_at": e.occurred_at,
                "node_id": e.node_id,
                "gate": e.gate,
            }
            for e in proj.events
        ],
        "pending_count": frame.total - frame.cursor,
        "head": (
            {
                "source_event_id": last.source_event_id,
                "event_type": last.event_type,
                "occurred_at": last.occurred_at,
            }
            if last is not None
            else None
        ),
    }

    evidence = {
        **stamp,
        # Evidence refs accumulate strictly from applied events; a rewind hides
        # evidence that had not yet been observed at that point in history.
        "refs": [
            {"source_event_id": e.source_event_id, "ref": ref}
            for e in proj.events
            for ref in (e.evidence_refs or [])
        ],
        "authority_refs": sorted(
            {e.authority_ref for e in proj.events if e.authority_ref}
        ),
    }

    inspector = {
        **stamp,
        "anomalies": [
            {
                "kind": a.kind,
                "at_index": a.at_index,
                "source_system": a.source_system,
                "source_event_id": a.source_event_id,
                "message": a.message,
            }
            for a in frame.anomalies
        ],
        "anomaly_kinds": frame.anomaly_kinds(),
        "selected": (
            {
                "source_event_id": last.source_event_id,
                "before": last.before,
                "after": last.after,
                "actor": last.actor,
                "summary": last.summary,
            }
            if last is not None
            else None
        ),
    }

    return SurfaceSnapshot(
        cursor=frame.cursor,
        total=frame.total,
        mode=mode,
        state_digest=frame.state_digest,
        root_card=root_card,
        dag=dag,
        timeline=timeline,
        evidence=evidence,
        inspector=inspector,
    )


# ---------------------------------------------------------------------------
# Session (LIVE <-> REPLAY, resume without sequence corruption)
# ---------------------------------------------------------------------------


class ReplaySession:
    """Stateful LIVE/REPLAY cursor over an append-only stream.

    Invariants that protect the LIVE lane:

    * The canonical stream is APPEND-ONLY. Rewinding moves a cursor; it never
      truncates, reorders, or drops events.
    * Events appended while rewound land at the canonical tip and are visible
      immediately on resume — a rewound observer never loses live history.
    * ``resume_live()`` recomputes the tip from the full stream, so the resumed
      projection (and its per-source high-water marks) is identical to a session
      that never entered replay. This is the "no sequence corruption" guarantee.
    """

    def __init__(self, events: Optional[Iterable[RunProjectionEvent]] = None) -> None:
        self._events: List[RunProjectionEvent] = list(events or [])
        self._mode: str = MODE_LIVE
        self._cursor: int = len(self._events)

    # -- state ------------------------------------------------------------
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def total(self) -> int:
        return len(self._events)

    @property
    def is_replaying(self) -> bool:
        return self._mode == MODE_REPLAY

    def timeline(self) -> ReplayTimeline:
        """An immutable timeline over the canonical stream as it stands now."""
        return ReplayTimeline(self._events)

    # -- live ingest ------------------------------------------------------
    def append_live(self, event: RunProjectionEvent) -> int:
        """Append a live event to the canonical tip.

        Allowed in BOTH modes. While replaying, the cursor deliberately stays
        put (the operator keeps looking at the past) but the event is retained,
        so nothing is lost. In LIVE mode the cursor follows the tip.
        """
        self._events.append(event)
        if self._mode == MODE_LIVE:
            self._cursor = len(self._events)
        return len(self._events)

    def extend_live(self, events: Iterable[RunProjectionEvent]) -> int:
        for e in events:
            self.append_live(e)
        return len(self._events)

    # -- replay controls --------------------------------------------------
    def enter_replay(self, cursor: Optional[int] = None) -> ReplayFrame:
        """Switch to REPLAY, optionally rewinding to ``cursor`` (default: tip)."""
        self._mode = MODE_REPLAY
        target = self.total if cursor is None else cursor
        self._cursor = self.timeline().clamp(target)
        return self.frame()

    def rewind_to(self, cursor: int) -> ReplayFrame:
        """Jump the cursor anywhere in ``0..total`` (implies REPLAY mode)."""
        self._mode = MODE_REPLAY
        self._cursor = self.timeline().clamp(cursor)
        return self.frame()

    def step_back(self, n: int = 1) -> ReplayFrame:
        return self.rewind_to(self._cursor - max(0, n))

    def step_forward(self, n: int = 1) -> ReplayFrame:
        return self.rewind_to(self._cursor + max(0, n))

    def resume_live(self) -> ReplayFrame:
        """Return to LIVE at the canonical tip, uncorrupted.

        The resumed frame is recomputed from the FULL stream, so it equals the
        tip of an equivalent never-replayed session, including every event that
        arrived while rewound.
        """
        self._mode = MODE_LIVE
        self._cursor = len(self._events)
        return self.frame()

    # -- projections ------------------------------------------------------
    def frame(self) -> ReplayFrame:
        return self.timeline().frame_at(self._cursor)

    def surfaces(self) -> SurfaceSnapshot:
        """Whole-screen snapshot at the current cursor, tagged with the mode."""
        return project_surfaces(self.frame(), mode=self._mode)

    def rewind_path(self, cursors: Sequence[int]) -> List[SurfaceSnapshot]:
        """Walk a rewind path, returning a synchronized snapshot per stop."""
        out: List[SurfaceSnapshot] = []
        for c in cursors:
            self.rewind_to(c)
            out.append(self.surfaces())
        return out
