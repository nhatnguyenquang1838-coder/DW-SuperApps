"""Tests for golden fixture loading."""

from dw_observation.fixtures import load_event_stream, load_expected_projection
from dw_observation.events import RunProjectionEvent


def test_load_event_stream_returns_typed_events():
    events = load_event_stream("run_scrum555_m0")
    assert len(events) == 7
    assert all(isinstance(e, RunProjectionEvent) for e in events)
    assert events[0].event_type == "run_started"
    # source_event_id is the EXACT source id (no tc:{run_id}:{index})
    assert events[0].source_event_id == "evt_audit_run_started_0"


def test_load_gwc_durable_event_stream():
    events = load_event_stream("run_gwc_durable_m0")
    assert len(events) == 5
    assert all(isinstance(e, RunProjectionEvent) for e in events)
    assert all(e.source_system == "gwc" for e in events)
    # canonical GWC vocabulary preserved verbatim
    assert events[2].event_type == "node_started"
    assert events[2].gate == "G2_EXECUTION"
    assert events[2].outcome == "success"
    # structured actor preserved exactly
    assert events[2].actor == {"kind": "chatgpt", "id": "agent-hermes-mac", "execution_mode": "local_agent"}


def test_load_expected_projection_shape():
    proj = load_expected_projection("projection_scrum555_m0")
    assert proj["run_id"] == "DW-OBS-M0-20260821-R2"
    assert "nodes" in proj and "gates" in proj
    assert proj["gates"]["G2-DW-OBS-M0-20260821-R2"]["status"] == "released"


def test_load_missing_fixture_raises():
    import pytest

    with pytest.raises(FileNotFoundError):
        load_event_stream("does_not_exist")
