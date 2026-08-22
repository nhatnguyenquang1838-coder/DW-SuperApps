"""M2 — Realtime projection delivery + catch-up sequencing (read-only live layer).

Adds LIVE delivery on top of the M0 deterministic projection WITHOUT making
Realtime the historical source of truth.

Design boundaries (per GitHub #73 M2 contract):

  * ``EventStore`` is the DURABLE projection event store (Postgres in prod).
    Historical replay stays DB-backed. The observer reads it; it NEVER writes
    governance, Slack, or any repo through it. No remote DB/Supabase mutation
    is performed by this module — ``REMOTE_DB_MUTATION`` is ``False``.
  * ``RealtimeTransport`` is Supabase Realtime Broadcast — TRANSPORT ONLY. It
    carries live deltas to the browser; it is NOT canonical history.
  * On reconnect: historical catch-up -> sequence reconcile -> resume LIVE.
    Gaps / duplicates / stale sequences are detected explicitly and recorded
    (never silently dropped or reordered).
  * A temporary Realtime failure degrades to ``DEGRADED`` / ``PROJECTION_UNAVAILABLE``
    (historical snapshot retained) and NEVER fails the canonical runtime.

Anomaly detection (DUPLICATE / OUT_OF_ORDER / STALE / GAP) is delegated to the
M0 ``reduce()`` pipeline so the live layer never duplicates that logic. The live
layer adds only what ``reduce`` cannot know: expected next-sequence continuity,
the high-water mark per source, the catch-up/resync procedure, and the degraded
state machine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from .events import RunProjectionEvent
from .projection import Anomaly, Projection
from .reducer import reduce

# Hard invariant: this live layer never mutates the remote durable store or
# Supabase. It is a read-only projection consumer. Surfaced in the delivery
# evidence mailbox as ``remote_db_mutation=false``.
REMOTE_DB_MUTATION = False


class LiveState(str, Enum):
    """Lifecycle state of a live projection observer.

    The observer starts UNAVAILABLE (no historical seed yet). It becomes LIVE
    once historical catch-up succeeds. A detected sequence gap moves it to
    CATCHING_UP (awaiting resync). Transport/store unavailability moves it to
    DEGRADED / PROJECTION_UNAVAILABLE while the last known snapshot is retained.
    """

    UNAVAILABLE = "UNAVAILABLE"
    LIVE = "LIVE"
    CATCHING_UP = "CATCHING_UP"
    DEGRADED = "DEGRADED"
    PROJECTION_UNAVAILABLE = "PROJECTION_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Durable projection event store (Postgres in prod) — read-only interface.
# ---------------------------------------------------------------------------
class EventStore(ABC):
    """Durable projection event store (historical source of truth).

    Implemented by Postgres in production. The observer only ever READS via
    ``load_all``; it never mutates the store. A local ``InMemoryEventStore`` is
    provided for deterministic offline tests and local dev.
    """

    @abstractmethod
    def load_all(self, run_id: str) -> List[RunProjectionEvent]:
        """Return the full, canonical, ordered event stream for ``run_id``."""


class InMemoryEventStore(EventStore):
    """Local stand-in for the durable Postgres store.

    Mirrors the Postgres read API. ``ingest`` simulates a durable write made by
    the canonical runtime (NOT by this observer) so tests can model new events
    landing in history between reconnects. The observer never calls ``ingest``.
    """

    def __init__(self) -> None:
        self._store: Dict[str, List[RunProjectionEvent]] = {}

    def ingest(self, run_id: str, events: Iterable[RunProjectionEvent]) -> None:
        self._store.setdefault(run_id, []).extend(events)

    def load_all(self, run_id: str) -> List[RunProjectionEvent]:
        return list(self._store.get(run_id, []))


# ---------------------------------------------------------------------------
# Realtime transport (Supabase Broadcast) — transport only.
# ---------------------------------------------------------------------------
class RealtimeTransport(ABC):
    """Supabase Realtime Broadcast channel — transport only, not canonical."""

    @abstractmethod
    def subscribe(self, topic: str, on_message: Any) -> None:
        """Subscribe to ``topic``; ``on_message(payload: dict)`` on each frame."""

    @abstractmethod
    def close(self) -> None:
        """Tear down the subscription (does not publish anything)."""


class FakeRealtimeTransport(RealtimeTransport):
    """In-memory transport double for deterministic offline tests.

    Tests drive it via ``emit``; it never touches a network. It also records a
    ``down`` flag so tests can simulate a transport outage.
    """

    def __init__(self) -> None:
        self._topic: Optional[str] = None
        self._handler: Optional[Any] = None
        self.down = False

    def subscribe(self, topic: str, on_message: Any) -> None:
        self._topic = topic
        self._handler = on_message

    def close(self) -> None:
        self._handler = None

    def emit(self, payload: Dict[str, Any]) -> None:
        if self.down or self._handler is None:
            raise RuntimeError("realtime transport is down / not subscribed")
        self._handler(payload)


class SupabaseRealtimeTransport(RealtimeTransport):
    """Subscriber-only adapter for a Supabase Realtime channel.

    Binds to an ALREADY-CONNECTED Supabase ``RealtimeChannel`` (dependency
    injected by the host app). It listens for ``broadcast`` frames and forwards
    them to ``on_message``. It NEVER publishes and performs no remote mutation —
    Broadcast is transport only, not canonical history. No Supabase import is
    performed at module load; the channel object is supplied at construction.
    """

    def __init__(self, channel: Any) -> None:
        self._channel = channel

    def subscribe(self, topic: str, on_message: Any) -> None:
        # A Supabase channel is already topic-scoped; we only attach a broadcast
        # listener. ``topic`` is accepted for interface parity and ignored here.
        self._channel.on("broadcast", {"event": topic}, lambda payload: on_message(payload))

    def close(self) -> None:
        try:
            self._channel.unsubscribe()
        except Exception:
            # Tearing down must never fail the observer's canonical runtime.
            pass


# ---------------------------------------------------------------------------
# Live observer: catch-up sequencing + degraded state machine.
# ---------------------------------------------------------------------------
@dataclass
class ReceiveResult:
    """Outcome of a single live frame."""

    kind: str  # APPENDED | DUPLICATE | GAP | STALE | REJECTED
    anomaly: Optional[Anomaly] = None
    appended: bool = False


@dataclass
class ResyncReport:
    """Outcome of a historical catch-up / reconnect reconcile."""

    ok: bool
    state: LiveState
    high_water_before: Dict[str, int] = field(default_factory=dict)
    high_water_after: Dict[str, int] = field(default_factory=dict)
    anomalies: List[Anomaly] = field(default_factory=list)
    error: Optional[str] = None


def _high_water(proj: Projection) -> Dict[str, int]:
    hw: Dict[str, int] = {}
    for e in proj.events:
        hw[e.source_system] = max(hw.get(e.source_system, -1), e.sequence)
    return hw


class Observer:
    """Read-only live projection observer for one run.

    Replay contract (per #73): the historical Postgres store is the source of
    truth; Realtime is transport only. Sequence continuity is preserved exactly
    across reconnect via explicit high-water tracking and a full resync.
    """

    def __init__(self, store: EventStore, transport: RealtimeTransport, run_id: str) -> None:
        self.store = store
        self.transport = transport
        self.run_id = run_id
        self.projection: Optional[Projection] = None
        self.high_water: Dict[str, int] = {}
        self.state = LiveState.UNAVAILABLE
        self.last_error: Optional[str] = None

    # -- historical catch-up (bootstrap + reconnect) -------------------------
    def bootstrap(self) -> Projection:
        """Seed historical state from the durable store (source of truth)."""
        events = self.store.load_all(self.run_id)
        self.projection = reduce(events)
        self.high_water = _high_water(self.projection)
        self.state = LiveState.LIVE
        self.last_error = None
        return self.projection

    def resync(self) -> ResyncReport:
        """Reconnect flow: historical catch-up -> sequence reconcile -> LIVE.

        Reloads the full durable stream (the real source of truth), re-derives
        the projection, and reconciles the high-water mark. Newly landed durable
        events fill any prior GAP. On store failure the observer degrades rather
        than failing the canonical runtime.
        """
        prev_hw = dict(self.high_water)
        try:
            fresh = self.store.load_all(self.run_id)
        except Exception as ex:  # store unreachable -> degrade, keep snapshot
            # No prior snapshot means there is nothing to degrade "from"; stay
            # UNAVAILABLE rather than falsely claiming projection state.
            self.state = (
                LiveState.PROJECTION_UNAVAILABLE
                if self.projection is not None
                else LiveState.UNAVAILABLE
            )
            self.last_error = f"durable store unreachable during resync: {ex}"
            return ResyncReport(
                ok=False, state=self.state, high_water_before=prev_hw,
                high_water_after=dict(self.high_water), error=self.last_error,
            )
        self.projection = reduce(fresh)
        self.high_water = _high_water(self.projection)
        self.state = LiveState.LIVE
        self.last_error = None
        return ResyncReport(
            ok=True, state=self.state, high_water_before=prev_hw,
            high_water_after=dict(self.high_water),
            anomalies=list(self.projection.anomalies),
        )

    # -- live frame handling ------------------------------------------------
    def receive_live(self, message: Dict[str, Any]) -> ReceiveResult:
        """Apply one Realtime broadcast frame.

        Returns the classification. Detects DUPLICATE (broadcast redelivery),
        GAP (out-of-order forward jump -> withhold, await resync), STALE (behind
        high-water, non-duplicate), and APPENDED (normal). Invalid/out-of-run
        frames are REJECTED without mutating canonical state.
        """
        if self.projection is None:
            self.state = LiveState.UNAVAILABLE
            return ReceiveResult(kind="REJECTED")

        payload = message.get("event") if isinstance(message, dict) else None
        if not isinstance(payload, dict):
            self.last_error = "live frame missing 'event' envelope"
            return ReceiveResult(kind="REJECTED")

        try:
            evt = RunProjectionEvent.from_dict(payload)
        except Exception as ex:
            self.last_error = f"invalid live envelope: {ex}"
            return ReceiveResult(kind="REJECTED")

        if evt.run_id != self.run_id:
            return ReceiveResult(kind="REJECTED")

        src = evt.source_system
        hw = self.high_water.get(src, -1)

        # Explicit duplicate (same source identity already projected):
        # broadcast redelivery — drop, no state change, no anomaly inflation.
        if any(
            e.source_system == src and e.source_event_id == evt.source_event_id
            for e in self.projection.events
        ):
            return ReceiveResult(kind="DUPLICATE")

        expected = hw + 1
        if evt.sequence > expected:
            # GAP: a non-contiguous forward jump. Withhold the frame and wait
            # for historical catch-up to fill it (we must not append partial /
            # out-of-order state into the canonical projection).
            a = Anomaly(
                kind="GAP",
                at_index=len(self.projection.events),
                source_system=src,
                source_event_id=evt.source_event_id,
                message=(
                    f"live sequence gap at ({src}): seq={evt.sequence} "
                    f"expected next {expected}; awaiting historical catch-up"
                ),
            )
            self.projection.anomalies.append(a)
            self.state = LiveState.CATCHING_UP
            return ReceiveResult(kind="GAP", anomaly=a)

        # Normal or stale: re-derive the full projection so M0's anomaly
        # detection (STALE/OUT_OF_ORDER) stays authoritative.
        before = len(self.projection.anomalies)
        self.projection = reduce(self.projection.events + [evt])
        self.high_water[src] = max(hw, evt.sequence)
        self.state = LiveState.LIVE
        self.last_error = None

        new_anomalies = self.projection.anomalies[before:]
        stale = next((a for a in new_anomalies if a.kind == "STALE"), None)
        if stale is not None:
            return ReceiveResult(kind="STALE", anomaly=stale)
        return ReceiveResult(kind="APPENDED", appended=True)

    # -- degraded state -----------------------------------------------------
    def mark_transport_down(self) -> None:
        """Realtime transport failed; degrade but keep the historical snapshot."""
        if self.projection is not None:
            self.state = LiveState.PROJECTION_UNAVAILABLE
        else:
            self.state = LiveState.UNAVAILABLE
        self.last_error = "realtime transport unavailable"

    def bind_transport(self) -> None:
        """Attach the observer to its transport (supplier pattern)."""
        self.transport.subscribe(self.run_id, self.receive_live)
