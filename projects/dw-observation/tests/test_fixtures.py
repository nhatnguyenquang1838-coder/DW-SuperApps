"""Tests for golden fixture loading."""

from dw_observation.fixtures import load_event_stream, load_expected_projection
from dw_observation.events import RunProjectionEvent


def test_load_event_stream_returns_typed_events():
    events = load_event_stream("run_scrum555_m0")
    assert len(events) == 7
    assert all(isinstance(e, RunProjectionEvent) for e in events)
    assert events[0].kind == "run_started"


def test_load_expected_projection_shape():
    proj = load_expected_projection("projection_scrum555_m0")
    assert proj["run_id"] == "DW-OBS-M0-20260821-R2"
    assert "nodes" in proj and "gates" in proj
    assert proj["gates"]["G2-DW-OBS-M0-20260821-R2"]["status"] == "released"


def test_load_missing_fixture_raises():
    import pytest

    with pytest.raises(FileNotFoundError):
        load_event_stream("does_not_exist")
