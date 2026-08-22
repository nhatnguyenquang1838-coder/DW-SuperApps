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

    # Re-deliver an already-projected identity (broadcast redelivery).
    dup = _ev(sequence=1, node_id="71", outcome="done", source_event_id="e1")
    r1 = obs.receive_live({"event": dup.to_dict()})
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
    # A stale, lower-sequence frame arrives after high-water=2.
    stale = _ev(sequence=1, node_id="71", outcome="active", source_event_id="e1")
    r = obs.receive_live({"event": stale.to_dict()})
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
    r = obs.receive_live({"event": gap.to_dict()})
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
        transport.emit({"event": _ev(sequence=2, source_event_id="e2").to_dict()})
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
