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


def test_reducer_is_deterministic_regardless_of_input_order():
    a = RunProjectionEvent(kind="node_progress", ts="2026-08-21T19:00:00Z", seq=5, node="71", data={"status": "done"})
    b = RunProjectionEvent(kind="run_started", ts="2026-08-21T09:00:00Z", seq=0)
    c = RunProjectionEvent(kind="gate_released", ts="2026-08-21T18:27:00Z", seq=3, gate="G2-X", actor="Ctrl")

    p1 = reduce([a, b, c])
    p2 = reduce([c, b, a])
    assert _as_dict(p1) == _as_dict(p2)
    # event ordering normalized
    assert [e.seq for e in p1.events] == [0, 3, 5]


def test_reducer_gate_released_preserves_approved_by():
    events = [
        RunProjectionEvent(kind="gate_approved", ts="2026-08-21T18:26:00Z", seq=2, gate="G2-X", actor="Human G2"),
        RunProjectionEvent(kind="gate_released", ts="2026-08-21T18:27:00Z", seq=3, gate="G2-X", actor="Ctrl"),
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
        RunProjectionEvent(kind="run_started", ts="2026-08-21T09:00:00Z", seq=0),
        RunProjectionEvent(kind="projection_snapshot", ts="2026-08-21T19:00:01Z", seq=6, data={"captured": True}),
    ]
    proj = reduce(events)
    assert proj.nodes == {}
    assert proj.gates == {}
