"""Tests for golden fixture loading (canonical source records -> adapter -> projection)."""

from dw_observation.fixtures import load_event_stream, load_expected_projection
from dw_observation.events import RunProjectionEvent


def test_load_event_stream_returns_typed_events():
    events = load_event_stream("run_scrum555_m0")
    assert len(events) == 7
    assert all(isinstance(e, RunProjectionEvent) for e in events)
    assert events[0].event_type == "run_started"
    # source_event_id is the EXACT AuditEvent.event_id (no tc:{run_id}:{index})
    assert events[0].source_event_id == "evt_audit_run_started_0"


def test_load_gwc_durable_event_stream():
    events = load_event_stream("run_gwc_durable_m0")
    assert len(events) == 5
    assert all(isinstance(e, RunProjectionEvent) for e in events)
    assert all(e.source_system == "gwc" for e in events)
    # canonical GWC vocabulary preserved verbatim from DurableEvent
    assert events[2].event_type == "node_started"
    assert events[2].gate == "G2_EXECUTION"
    assert events[2].outcome == "success"
    # structured actor preserved exactly
    assert events[2].actor == {"kind": "chatgpt", "id": "agent-hermes-mac", "execution_mode": "local_agent"}


def test_load_expected_projection_shape():
    proj = load_expected_projection("projection_scrum555_m0")
    assert proj["run_id"] == "DW-OBS-M0-20260821-R2"
    assert "nodes" in proj and "gates" in proj


def test_load_missing_fixture_raises():
    import pytest

    with pytest.raises(FileNotFoundError):
        load_event_stream("does_not_exist")


# --- Provenance: source identity/digest/before/after/evidence/actor survive ---
def test_tc_source_provenance_survives_adapter_and_reducer():
    events = load_event_stream("run_scrum555_m0")
    # Every event is typed and the EXACT source identity is preserved.
    e0 = events[0]
    assert e0.source_event_id == "evt_audit_run_started_0"
    assert e0.source_system == "taskcontroller"
    # source_digest is the ADAPTER-computed digest of the canonical AuditEvent
    # (sha256:..), NOT a digest of a normalized envelope.
    assert e0.source_digest.startswith("sha256:")
    # before/after preserved verbatim from the AuditEvent.
    assert e0.before is None
    assert e0.after == {"jira": "SCRUM-555", "node": "M0", "parent_issue": 70}
    # actor preserved exactly.
    assert e0.actor == "ChatGPT TaskController"

    # The reducer fold keeps the digest on the projected event.
    from dw_observation.reducer import reduce

    proj = reduce(events)
    assert proj.events[0].source_digest == e0.source_digest
    assert proj.events[0].source_event_id == e0.source_event_id


def test_gwc_source_provenance_survives_adapter_and_reducer():
    events = load_event_stream("run_gwc_durable_m0")
    # structured actor + GWC vocabulary survive from DurableEvent verbatim.
    e0 = events[0]
    assert e0.source_event_id == "evt_a1b2c3d4_run_started"
    assert e0.source_system == "gwc"
    assert e0.actor == {"kind": "chatgpt", "id": "agent-hermes-mac", "execution_mode": "local_agent"}
    assert e0.outcome == "success"
    # DurableEvent has no before/after state fields; payload must NOT become after.
    assert e0.before is None
    assert e0.after is None
    assert e0.source_digest.startswith("sha256:")
    assert e0.evidence_refs == ["gwc://runs/run_dw_obs_m0_r2/start"]

    from dw_observation.reducer import reduce

    proj = reduce(events)
    assert proj.events[0].source_digest == e0.source_digest
    assert proj.gates["G2_EXECUTION"].status == "passed"
