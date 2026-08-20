"""Deterministic reducer tests + golden fixture replay.

Replay contract: the reducer consumes the exact supplied order and never
silently reorders or hides duplicate/out-of-order/stale/gap — those are
recorded explicitly in ``proj.anomalies``.
"""

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
            k: {
                "status": v.status,
                "approved_by": v.approved_by,
                "released_by": v.released_by,
                "authority_ref": v.authority_ref,
            }
            for k, v in proj.gates.items()
        },
        "anomalies": [(a.kind, a.at_index) for a in proj.anomalies],
    }


def _ev(**kw):
    base = dict(
        run_id="R-1",
        source_system="taskcontroller",
        source_event_id="evt:R-1:0",
        source_digest="sha256:test",
        occurred_at="2026-08-21T09:00:00Z",
        event_type="projection_snapshot",
        outcome=None,
    )
    base.update(kw)
    return RunProjectionEvent(**base)


def test_reducer_golden_fixture_replay():
    events = load_event_stream("run_scrum555_m0")
    proj = reduce(events)
    expected = load_expected_projection("projection_scrum555_m0")
    assert proj.run_id == expected["run_id"]
    assert proj.started_at == expected["started_at"]
    assert proj.last_event_at == expected["last_event_at"]
    assert proj.to_dict()["nodes"] == expected["nodes"]
    assert proj.to_dict()["gates"] == expected["gates"]
    # clean golden stream -> no anomalies
    assert proj.anomalies == []


def test_reducer_gwc_durable_golden_replay():
    events = load_event_stream("run_gwc_durable_m0")
    proj = reduce(events)
    expected = load_expected_projection("projection_gwc_durable_m0")
    assert proj.to_dict()["nodes"] == expected["nodes"]
    assert proj.to_dict()["gates"] == expected["gates"]
    # node_completed advances node state; structured actor preserved in gate
    assert proj.gates["G2_EXECUTION"].approved_by == {
        "kind": "chatgpt",
        "id": "agent-hermes-mac",
        "execution_mode": "local_agent",
    }
    assert proj.anomalies == []


def test_reducer_preserves_supplied_order_not_sorted():
    # Deliberately NOT in (occurred_at, sequence) order; reduce must keep it.
    a = _ev(sequence=5, node_id="71", event_type="node_progress", outcome="done",
            source_event_id="evt:R-1:5", occurred_at="2026-08-21T19:00:00Z")
    b = _ev(sequence=0, event_type="run_started", outcome=None,
            source_event_id="evt:R-1:0", occurred_at="2026-08-21T09:00:00Z")
    c = _ev(sequence=3, gate="G2-X", event_type="gate_released", outcome=None,
            actor="Ctrl", source_event_id="evt:R-1:3", occurred_at="2026-08-21T18:27:00Z")
    proj = reduce([a, b, c])
    # No silent reorder: events remain in supplied order.
    assert [e.source_event_id for e in proj.events] == ["evt:R-1:5", "evt:R-1:0", "evt:R-1:3"]
    # State still computed correctly (node 71 done, G2-X released).
    assert proj.nodes["71"].status == "done"
    assert proj.gates["G2-X"].status == "released"


def test_reducer_detects_duplicate_explicitly_not_silent():
    e1 = _ev(sequence=1, gate="G2-X", event_type="gate_approved", outcome=None,
             actor="Human", source_event_id="evt:R-1:dup", occurred_at="2026-08-21T18:00:00Z")
    e2 = _ev(sequence=1, gate="G2-X", event_type="gate_approved", outcome=None,
             actor="Human", source_event_id="evt:R-1:dup", occurred_at="2026-08-21T18:00:00Z")
    proj = reduce([e1, e2])
    # BOTH events retained (not collapsed) and a DUPLICATE anomaly recorded.
    assert len(proj.events) == 2
    assert ("DUPLICATE", 1) in [(a.kind, a.at_index) for a in proj.anomalies]
    assert proj.gates["G2-X"].status == "approved"


def test_reducer_detects_stale_explicitly():
    newer = _ev(sequence=3, gate="G2-X", event_type="gate_released", outcome=None,
                actor="Ctrl", source_event_id="evt:R-1:3", occurred_at="2026-08-21T18:27:00Z")
    older = _ev(sequence=2, gate="G2-X", event_type="gate_approved", outcome=None,
                actor="Human", source_event_id="evt:R-1:2", occurred_at="2026-08-21T18:26:00Z")
    # older delivered after newer (stale): recorded, state stays released.
    proj = reduce([newer, older])
    assert ("STALE", 1) in [(a.kind, a.at_index) for a in proj.anomalies]
    assert proj.gates["G2-X"].status == "released"


def test_reducer_detects_gap_explicitly():
    e0 = _ev(sequence=0, event_type="run_started", outcome=None,
             source_event_id="evt:R-1:0", occurred_at="2026-08-21T09:00:00Z")
    e3 = _ev(sequence=3, gate="G2-X", event_type="gate_released", outcome=None,
             actor="Ctrl", source_event_id="evt:R-1:3", occurred_at="2026-08-21T18:27:00Z")
    proj = reduce([e0, e3])
    # gap recorded; reduction still keys on explicit sequence.
    assert any(a.kind == "GAP" for a in proj.anomalies)
    assert proj.gates["G2-X"].status == "released"


def test_reducer_projection_snapshot_is_observation_only():
    events = [
        _ev(sequence=0, event_type="run_started", outcome=None,
            source_event_id="evt:R-1:0", occurred_at="2026-08-21T09:00:00Z"),
        _ev(sequence=6, event_type="projection_snapshot", outcome=None, summary="snap",
            source_event_id="evt:R-1:6", source_system="taskcontroller",
            occurred_at="2026-08-21T19:00:01Z"),
    ]
    proj = reduce(events)
    assert proj.nodes == {}
    assert proj.gates == {}


def test_gate_failed_projects_to_failed_not_released():
    e = _ev(sequence=1, gate="G2-X", event_type="gate_failed", outcome=None,
            actor="Bot", source_event_id="evt:R-1:fail", occurred_at="2026-08-21T18:30:00Z")
    proj = reduce([e])
    assert proj.gates["G2-X"].status == "failed"
    # Failure actor lands in failed_by, never in released_by.
    assert proj.gates["G2-X"].failed_by == "Bot"
    assert proj.gates["G2-X"].released_by is None


def test_gate_passed_projects_to_passed():
    e = _ev(sequence=1, gate="G2-X", event_type="gate_passed", outcome=None,
            actor="Bot", source_event_id="evt:R-1:pass", occurred_at="2026-08-21T18:30:00Z")
    proj = reduce([e])
    assert proj.gates["G2-X"].status == "passed"


def test_forward_jump_is_gap_not_out_of_order():
    # 0 -> 3 is a forward non-contiguous jump: GAP only, never OUT_OF_ORDER.
    e0 = _ev(sequence=0, event_type="run_started", outcome=None,
             source_event_id="evt:R-1:0", occurred_at="2026-08-21T09:00:00Z")
    e3 = _ev(sequence=3, gate="G2-X", event_type="gate_released", outcome=None,
             actor="Ctrl", source_event_id="evt:R-1:3", occurred_at="2026-08-21T18:27:00Z")
    proj = reduce([e0, e3])
    kinds = [a.kind for a in proj.anomalies]
    assert "GAP" in kinds
    assert "OUT_OF_ORDER" not in kinds


def test_source_sequence_regression_is_out_of_order():
    # 3 -> 2 regresses on SOURCE SEQUENCE: OUT_OF_ORDER (and not a gap).
    e3 = _ev(sequence=3, gate="G2-X", event_type="gate_released", outcome=None,
             actor="Ctrl", source_event_id="evt:R-1:3", occurred_at="2026-08-21T18:27:00Z")
    e2 = _ev(sequence=2, gate="G2-X", event_type="gate_approved", outcome=None,
             actor="Human", source_event_id="evt:R-1:2", occurred_at="2026-08-21T18:26:00Z")
    proj = reduce([e3, e2])
    kinds = [a.kind for a in proj.anomalies]
    assert "OUT_OF_ORDER" in kinds
    assert "GAP" not in kinds  # regression is not a forward jump


def test_interleaved_tc_gwc_no_cross_source_anomalies():
    # A unified run interleaves GWC and TaskController streams. Each has its own
    # independent sequence ledger; the reducer must NOT raise false GAP/OUT_OF_ORDER
    # just because the two streams don't share a contiguous global sequence.
    tc0 = RunProjectionEvent(
        run_id="R-1", source_system="taskcontroller", source_event_id="tc:0",
        source_digest="sha256:tc0", occurred_at="2026-08-21T09:00:00Z",
        sequence=0, event_type="run_started",
    )
    gwc0 = RunProjectionEvent(
        run_id="R-1", source_system="gwc", source_event_id="gwc:0",
        source_digest="sha256:gwc0", occurred_at="2026-08-21T09:01:00Z",
        sequence=0, event_type="run_started",
    )
    tc1 = RunProjectionEvent(
        run_id="R-1", source_system="taskcontroller", source_event_id="tc:1",
        source_digest="sha256:tc1", occurred_at="2026-08-21T09:02:00Z",
        sequence=1, event_type="gate_approved", gate="G2-X", actor="Human",
    )
    gwc1 = RunProjectionEvent(
        run_id="R-1", source_system="gwc", source_event_id="gwc:1",
        source_digest="sha256:gwc1", occurred_at="2026-08-21T09:03:00Z",
        sequence=1, event_type="node_completed", node_id="m0", outcome="success",
    )
    # Interleaved order: tc0, gwc0, tc1, gwc1. Each source's sequence is
    # contiguous within its own ledger, so no cross-source false anomalies.
    proj = reduce([tc0, gwc0, tc1, gwc1])
    kinds = [a.kind for a in proj.anomalies]
    assert "GAP" not in kinds
    assert "OUT_OF_ORDER" not in kinds
    assert "STALE" not in kinds
    # Both source ledgers advanced state correctly.
    assert proj.gates["G2-X"].status == "approved"
    assert proj.nodes["m0"].status == "success"
