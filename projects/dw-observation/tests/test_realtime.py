"""M2 live delivery + catch-up sequencing tests (read-only live layer).

Covers GitHub #73 acceptance criteria:
  1. Exact sequence continuity preserved across reconnect.
  2. Duplicate/stale events do not silently reorder state.
  3. Temporary Realtime failure does not fail canonical runtime.
  4. Reconnect/catch-up and sequence-gap handling.
  5. Live view remains read-only (no remote mutation).

All remote I/O (Postgres store, Supabase Realtime) is behind injectable
interfaces; tests use the offline doubles. ``REMOTE_DB_MUTATION`` must stay
``False``.
"""

import pytest

from dw_observation.events import RunProjectionEvent
from dw_observation.realtime import (
    FakeRealtimeTransport,
    InMemoryEventStore,
    Observer,
    REMOTE_DB_MUTATION,
    ResyncReport,
    SupabaseRealtimeTransport,
)


def _ev(**kw) -> RunProjectionEvent:
    base = dict(
        run_id="R-1",
        source_system="taskcontroller",
        source_event_id="evt:R-1:0",
        source_digest="sha256:test",
        occurred_at="2026-08-22T09:00:00Z",
        event_type="node_progress",
        outcome="active",
    )
    base.update(kw)
    return RunProjectionEvent(**base)


def test_remote_db_mutation_is_false():
    # Hard contract invariant for the live layer.
    assert REMOTE_DB_MUTATION is False


def test_bootstrap_seeds_historical_source_of_truth():
    store = InMemoryEventStore()
    store.ingest(
        "R-1",
        [
            _ev(sequence=0, event_type="run_started", source_event_id="e0"),
            _ev(sequence=1, node_id="71", outcome="done", source_event_id="e1"),
        ],
    )
    obs = Observer(store, FakeRealtimeTransport(), "R-1")
    proj = obs.bootstrap()
    assert obs.state.value == "LIVE"
    assert len(proj.events) == 2
    assert obs.high_water["taskcontroller"] == 1
    # Observer never wrote to the store.
    assert REMOTE_DB_MUTATION is False


def test_sequence_continuity_preserved_across_resync():
    # Initial durable state: seq 0..2.
    store = InMemoryEventStore()
    store.ingest(
        "R-1",
        [
            _ev(sequence=0, event_type="run_started", source_event_id="e0"),
            _ev(sequence=1, node_id="71", outcome="done", source_event_id="e1"),
            _ev(sequence=2, gate="G2", event_type="gate_released", source_event_id="e2"),
        ],
    )
    obs = Observer(store, FakeRealtimeTransport(), "R-1")
    obs.bootstrap()
    assert obs.high_water["taskcontroller"] == 2

    # New durable events land (seq 3,4) between reconnects.
    store.ingest(
        "R-1",
        [
            _ev(sequence=3, node_id="72", outcome="active", source_event_id="e3"),
            _ev(sequence=4, event_type="run_completed", source_event_id="e4"),
        ],
    )
    report: ResyncReport = obs.resync()
    assert report.ok is True
    assert report.state.value == "LIVE"
    # High-water advanced exactly; no lost/duplicated sequences.
    assert obs.high_water["taskcontroller"] == 4
    assert [e.sequence for e in obs.projection.events] == [0, 1, 2, 3, 4]
    assert obs.projection.anomalies == []


def test_duplicate_broadcast_does_not_reorder_or_inflate_state():
    store = InMemoryEventStore()
    store.ingest(
        "R-1",
        [
            _ev(sequence=0, event_type="run_started", source_event_id="e0"),
            _ev(sequence=1, node_id="71", outcome="done", source_event_id="e1"),
        ],
    )
    transport = FakeRealtimeTransport()
    obs = Observer(store, transport, "R-1")
    obs.bootstrap()
    obs.bind_transport()

    # Re-deliver an already-projected identity (broadcast redelivery). Use the
    # canonical envelope: event == "projection_event", payload == <object>.
    dup = _ev(sequence=1, node_id="71", outcome="done", source_event_id="e1")
    r1 = obs.receive_live({"event": "projection_event", "payload": dup.to_dict()})
    assert r1.kind == "DUPLICATE"
    # Canonical state unchanged: still 2 events, node 71 still done, no anomaly.
    assert len(obs.projection.events) == 2
    assert obs.projection.nodes["71"].status == "done"
    assert obs.projection.anomalies == []


def test_stale_live_event_does_not_silently_reorder():
    store = InMemoryEventStore()
    store.ingest(
        "R-1",
        [
            _ev(sequence=0, event_type="run_started", source_event_id="e0"),
            _ev(sequence=2, node_id="71", outcome="done", source_event_id="e2"),
        ],
    )
    obs = Observer(store, FakeRealtimeTransport(), "R-1")
    obs.bootstrap()
    # A stale, lower-sequence frame arrives after high-water=2. Use the canonical
    # envelope (event == "projection_event", payload == <object>).
    stale = _ev(sequence=1, node_id="71", outcome="active", source_event_id="e1")
    r = obs.receive_live({"event": "projection_event", "payload": stale.to_dict()})
    # STALE recorded; the canonical projection retains supplied order and the
    # later 'done' (seq 2) still dominates node state (monotone, no regress).
    assert r.kind == "STALE"
    assert r.anomaly is not None and r.anomaly.kind == "STALE"
    assert obs.projection.nodes["71"].status == "done"
    assert obs.state.value == "LIVE"


def test_gap_withheld_awaiting_catch_up():
    store = InMemoryEventStore()
    store.ingest(
        "R-1",
        [_ev(sequence=0, event_type="run_started", source_event_id="e0")],
    )
    obs = Observer(store, FakeRealtimeTransport(), "R-1")
    obs.bootstrap()
    # Live frame jumps to seq 2 (missing seq 1): gap detected, frame withheld.
    gap = _ev(sequence=2, node_id="71", outcome="active", source_event_id="e2")
    r = obs.receive_live({"event": "projection_event", "payload": gap.to_dict()})
    assert r.kind == "GAP"
    assert obs.state.value == "CATCHING_UP"
    # Frame not appended into canonical projection.
    assert len(obs.projection.events) == 1
    # Catch-up fills the gap exactly: the withheld seq 2 PLUS the missing seq 1
    # now land in the durable store (the real source of truth).
    store.ingest("R-1", [_ev(sequence=1, node_id="71", outcome="active", source_event_id="e1")])
    store.ingest("R-1", [_ev(sequence=2, node_id="71", outcome="active", source_event_id="e2")])
    report = obs.resync()
    assert report.ok is True
    assert [e.sequence for e in obs.projection.events] == [0, 1, 2]
    assert obs.state.value == "LIVE"


def test_transport_failure_does_not_fail_canonical_runtime():
    store = InMemoryEventStore()
    store.ingest(
        "R-1",
        [
            _ev(sequence=0, event_type="run_started", source_event_id="e0"),
            _ev(sequence=1, node_id="71", outcome="done", source_event_id="e1"),
        ],
    )
    transport = FakeRealtimeTransport()
    obs = Observer(store, transport, "R-1")
    obs.bootstrap()
    obs.bind_transport()

    # Realtime transport goes down mid-stream (frames routed through transport).
    transport.down = True
    # The transport double raises on emit while down; the observer's bound
    # handler must not crash the canonical runtime.
    try:
        transport.emit({"event": "projection_event", "payload": _ev(sequence=2, source_event_id="e2").to_dict()})
    except Exception:
        pass  # transport outage must not crash the observer
    obs.mark_transport_down()
    # Degrades to PROJECTION_UNAVAILABLE while the historical snapshot is kept.
    assert obs.state.value == "PROJECTION_UNAVAILABLE"
    # The last known historical state is intact (canonical runtime preserved).
    assert len(obs.projection.events) == 2
    assert obs.projection.nodes["71"].status == "done"
    # Restore: rebuild from durable store (source of truth) recovers to LIVE.
    transport.down = False
    report = obs.resync()
    assert report.ok is True
    assert obs.state.value == "LIVE"


def test_store_unreachable_on_resync_degrades_gracefully():
    class BrokenStore(InMemoryEventStore):
        def load_all(self, run_id):
            raise RuntimeError("postgres unreachable")

    obs = Observer(BrokenStore(), FakeRealtimeTransport(), "R-1")
    with pytest.raises(RuntimeError):
        obs.bootstrap()  # initial seed cannot recover
    # But a reconnect resync degrades instead of raising.
    obs.projection = None
    report = obs.resync()
    assert report.ok is False
    assert report.state.value == "UNAVAILABLE"
    assert "postgres unreachable" in (report.error or "")


# ---------------------------------------------------------------------------
# R4_B5 — Python M2 adapter must align with the canonical TS/Supabase contract:
#   topic   = "observatory:<run_id>"   (channel topic, NOT the event name)
#   event   = "projection_event"       (fixed string event name)
#   payload = <RunProjectionEvent>      (the canonical envelope object)
# The old incompatible envelope ({"event": <object>}) is no longer canonical.
# ---------------------------------------------------------------------------
def test_realtime_subscribes_on_fixed_projection_event_with_observatory_topic():
    captured = {}

    class FakeChannel:
        def on(self, kind, filt, cb=None):
            captured.setdefault(kind, []).append((filt, cb))

        def unsubscribe(self):
            pass

    ch = FakeChannel()
    transport = SupabaseRealtimeTransport(ch)  # type: ignore[arg-type]
    transport.subscribe("observatory:R-1", lambda p: None)
    # Must bind a 'broadcast' listener on the FIXED event name, NOT the topic.
    (filt, _cb) = captured["broadcast"][0]
    assert filt == {"event": "projection_event"}
    assert "R-1" not in str(filt)  # topic is not the event name


def test_receive_live_accepts_canonical_event_string_payload_envelope():
    store = InMemoryEventStore()
    store.ingest("R-1", [_ev(sequence=0, source_event_id="e0")])
    obs = Observer(store, FakeRealtimeTransport(), "R-1")
    obs.bootstrap()
    # Canonical frame: event == "projection_event" (string); object under payload.
    frame = {
        "type": "broadcast",
        "event": "projection_event",
        "topic": "observatory:R-1",
        "payload": _ev(sequence=1, source_event_id="e1").to_dict(),
    }
    r = obs.receive_live(frame)
    assert r.kind == "APPENDED"
    assert len(obs.projection.events) == 2


def test_receive_live_r41_sql_producer_payload_appends():
    # R4.1: the SQL realtime.send producer must pass the RAW ProjectionEvent
    # (row columns) as the first argument. Supabase wraps it into the delivered
    # callback frame as `payload`, so the subscriber receives the ProjectionEvent
    # at frame.payload (top-level), NOT frame.payload.payload.
    store = InMemoryEventStore()
    store.ingest("R-1", [_ev(sequence=0, source_event_id="e0")])
    obs = Observer(store, FakeRealtimeTransport(), "R-1")
    obs.bootstrap()
    # The RAW ProjectionEvent is what realtime.send() is called with (row cols),
    # and it is what arrives as `payload` in the delivered frame.
    raw_projection_event = _ev(
        sequence=1,
        source_event_id="e1",
        node_id="71",
        outcome="active",
    ).to_dict()
    delivered = {
        "type": "broadcast",
        "event": "projection_event",
        "payload": raw_projection_event,
    }
    r = obs.receive_live(delivered)
    assert r.kind == "APPENDED"
    # The ProjectionEvent is at payload top-level — no .payload.payload nesting.
    assert obs.projection.events[-1].source_event_id == "e1"
    assert obs.projection.events[-1].source_system == "taskcontroller"
    # Sanity: a NESTED (wrong) envelope would NOT place identity at top level and
    # must be rejected — proving the producer contract must be raw, not nested.
    nested = {
        "type": "broadcast",
        "event": "projection_event",
        "payload": {"type": "broadcast", "event": "projection_event",
                    "payload": raw_projection_event},
    }
    r2 = obs.receive_live(nested)
    assert r2.kind == "REJECTED"


def test_receive_live_rejects_old_incompatible_event_as_object_envelope():
    store = InMemoryEventStore()
    store.ingest("R-1", [_ev(sequence=0, source_event_id="e0")])
    obs = Observer(store, FakeRealtimeTransport(), "R-1")
    obs.bootstrap()
    # Old/drifted envelope: {"event": <ProjectionEvent object>} where event is a
    # dict. The canonical contract now requires event to be the STRING
    # "projection_event" and the object under payload. The old shape is no
    # longer accepted as canonical (it would silently map a projection object to
    # the wrong field), so it must be REJECTED.
    frame = {"event": _ev(sequence=1, source_event_id="e1").to_dict()}
    r = obs.receive_live(frame)
    assert r.kind == "REJECTED"
    assert len(obs.projection.events) == 1

