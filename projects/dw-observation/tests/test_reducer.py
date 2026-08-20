"""Deterministic reducer tests + golden fixture replay."""

from dw_observation.reducer import reduce
from dw_observation.events import RunProjectionEvent
from dw_observation.fixtures import (
    load_event_stream,
    load_expected_projection,
)


def _as_dict(proj):
    return {
        "run_id": proj.run_id,
        "started_at": proj.started_at,
        "last_event_at": proj.last_event_at,
        "nodes": {k: v.status for k, v in proj.nodes.items()},
        "gates": {
            k: {"status": v.status, "approved_by": v.approved_by, "released_by": v.released_by}
            for k, v in proj.gates.items()
        },
    }


def _ev(**kw):
    base = dict(
        run_id="R-1",
        source_system="taskcontroller",
        source_event_id="tc:R-1:0",
        occurred_at="2026-08-21T09:00:00Z",
        event_type="projection_snapshot",
        outcome="captured",
    )
    base.update(kw)
    return RunProjectionEvent(**base)


def test_reducer_is_deterministic_regardless_of_input_order():
    a = _ev(sequence=5, node_id="71", event_type="node_progress", outcome="done", source_event_id="tc:R-1:5", occurred_at="2026-08-21T19:00:00Z")
    b = _ev(sequence=0, event_type="run_started", outcome="started", source_event_id="tc:R-1:0", occurred_at="2026-08-21T09:00:00Z")
    c = _ev(sequence=3, gate="G2-X", event_type="gate_released", outcome="released", actor="Ctrl", source_event_id="tc:R-1:3", occurred_at="2026-08-21T18:27:00Z")

    p1 = reduce([a, b, c])
    p2 = reduce([c, b, a])
    assert _as_dict(p1) == _as_dict(p2)
    # event ordering normalized by (occurred_at, sequence)
    assert [e.sequence for e in p1.events] == [0, 3, 5]


def test_reducer_gate_released_preserves_approved_by():
    events = [
        _ev(sequence=2, gate="G2-X", event_type="gate_approved", outcome="approved", actor="Human G2", source_event_id="tc:R-1:2", occurred_at="2026-08-21T18:26:00Z"),
        _ev(sequence=3, gate="G2-X", event_type="gate_released", outcome="released", actor="Ctrl", source_event_id="tc:R-1:3", occurred_at="2026-08-21T18:27:00Z"),
    ]
    proj = reduce(events)
    g = proj.gates["G2-X"]
    assert g.status == "released"
    assert g.approved_by == "Human G2"
    assert g.released_by == "Ctrl"


def test_reducer_golden_fixture_replay():
    events = load_event_stream("run_scrum555_m0")
    proj = reduce(events)
    expected = load_expected_projection("projection_scrum555_m0")
    assert proj.run_id == expected["run_id"]
    assert proj.started_at == expected["started_at"]
    assert proj.last_event_at == expected["last_event_at"]
    assert proj.to_dict()["nodes"] == expected["nodes"]
    assert proj.to_dict()["gates"] == expected["gates"]


def test_reducer_projection_snapshot_is_observation_only():
    events = [
        _ev(sequence=0, event_type="run_started", outcome="started", source_event_id="tc:R-1:0", occurred_at="2026-08-21T09:00:00Z"),
        _ev(sequence=6, event_type="projection_snapshot", outcome="captured", summary="snap", source_event_id="tc:R-1:6", occurred_at="2026-08-21T19:00:01Z"),
    ]
    proj = reduce(events)
    assert proj.nodes == {}
    assert proj.gates == {}


def test_reducer_duplicate_source_identity_collapsed():
    # Two events with the same (source_system, source_event_id) -> one record.
    e1 = _ev(sequence=1, gate="G2-X", event_type="gate_approved", outcome="approved", actor="Human", source_event_id="tc:R-1:dup", occurred_at="2026-08-21T18:00:00Z")
    e2 = _ev(sequence=1, gate="G2-X", event_type="gate_approved", outcome="approved", actor="Human", source_event_id="tc:R-1:dup", occurred_at="2026-08-21T18:00:00Z")
    proj = reduce([e1, e2])
    assert len(proj.events) == 1  # duplicate collapsed
    assert proj.gates["G2-X"].status == "approved"


def test_reducer_stale_event_does_not_regress_state():
    # Newer release then an older approval arrives late (stale): state stays released.
    newer = _ev(sequence=3, gate="G2-X", event_type="gate_released", outcome="released", actor="Ctrl", source_event_id="tc:R-1:3", occurred_at="2026-08-21T18:27:00Z")
    older = _ev(sequence=2, gate="G2-X", event_type="gate_approved", outcome="approved", actor="Human", source_event_id="tc:R-1:2", occurred_at="2026-08-21T18:26:00Z")
    proj = reduce([newer, older])  # older delivered after newer (stale)
    assert proj.gates["G2-X"].status == "released"


def test_reducer_gap_in_sequence_ok():
    # Missing sequence 2; reduction keys on explicit sequence, not contiguity.
    e0 = _ev(sequence=0, event_type="run_started", outcome="started", source_event_id="tc:R-1:0", occurred_at="2026-08-21T09:00:00Z")
    e3 = _ev(sequence=3, gate="G2-X", event_type="gate_released", outcome="released", actor="Ctrl", source_event_id="tc:R-1:3", occurred_at="2026-08-21T18:27:00Z")
    proj = reduce([e0, e3])
    assert proj.gates["G2-X"].status == "released"
    assert [e.sequence for e in proj.events] == [0, 3]
