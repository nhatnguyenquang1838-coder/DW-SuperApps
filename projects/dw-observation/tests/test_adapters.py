"""Tests for read-only adapters (no mutation, no Slack parsing, no fabrication)."""

from dw_observation.adapters import TaskControllerAdapter, GwcAdapter
from dw_observation.events import RunProjectionEvent


# --- TaskController adapter: binds to canonical AuditEvent -----------------
def test_tc_adapter_maps_audit_event_identity():
    record = {
        "event_id": "evt_audit_g2_approved",
        "run_id": "DW-OBS-M0-20260821-R2",
        "sequence": 2,
        "source": "taskcontroller",
        "decision_kind": "gate_approved",
        "timestamp": "2026-08-21T18:26:00Z",
        "actor": "Human G2",
        "authority_ref": "G2-DW-OBS-M0-20260821-R2",
        "payload_summary": "Gate G2 approved",
        "before": None,
        "after": {"scope_sha256": "abc"},
        "evidence_refs": [],
    }
    e = TaskControllerAdapter().from_audit_event(record)
    assert e.source_system == "taskcontroller"
    assert e.source_event_id == "evt_audit_g2_approved"  # exact, not tc:{run}:{i}
    assert e.occurred_at == "2026-08-21T18:26:00Z"
    assert e.event_type == "gate_approved"  # decision_kind verbatim
    assert e.actor == "Human G2"
    assert e.authority_ref == "G2-DW-OBS-M0-20260821-R2"
    assert e.outcome is None  # not guessed from decision_kind
    assert e.gate is None     # not inferred
    assert e.read_only_projection is True
    assert e.source_digest is not None and e.source_digest.startswith("sha256:")


def test_tc_adapter_rejects_missing_required_fields():
    import pytest

    # missing event_id -> cannot fabricate source identity
    with pytest.raises(ValueError):
        TaskControllerAdapter().from_audit_event({"run_id": "R", "sequence": 0,
                                                  "decision_kind": "run_started",
                                                  "timestamp": "2026-08-21T00:00:00Z"})
    # missing sequence -> cannot synthesize index
    with pytest.raises(ValueError):
        TaskControllerAdapter().from_audit_event({"event_id": "e1", "run_id": "R",
                                                  "decision_kind": "run_started",
                                                  "timestamp": "2026-08-21T00:00:00Z"})
    # missing timestamp -> cannot fabricate occurred_at
    with pytest.raises(ValueError):
        TaskControllerAdapter().from_audit_event({"event_id": "e1", "run_id": "R",
                                                  "sequence": 0, "decision_kind": "run_started"})


def test_tc_adapter_from_json_list():
    text = ('[{"event_id":"e1","run_id":"R-2","sequence":0,"decision_kind":"run_started",'
            '"timestamp":"2026-08-21T00:00:00Z"},'
            '{"event_id":"e2","run_id":"R-2","sequence":1,"decision_kind":"node_progress",'
            '"timestamp":"2026-08-21T00:01:00Z","node_id":"71","outcome":"done"}]')
    events = TaskControllerAdapter().from_json(text)
    assert len(events) == 2
    assert all(isinstance(e, RunProjectionEvent) for e in events)
    assert events[1].node_id == "71"
    assert events[1].outcome == "done"


# --- GWC adapter: binds to canonical DurableEvent --------------------------
def test_gwc_adapter_maps_durable_event():
    record = {
        "schema_version": "0.1",
        "artifact_type": "durable-event",
        "event_id": "evt_a1b2c3d4_run_started",
        "run_id": "run_dw_obs_m0_r2",
        "sequence": 0,
        "event_type": "run_started",
        "occurred_at_utc": "2026-08-21T09:00:00Z",
        "actor": {"kind": "chatgpt", "id": "agent-hermes-mac", "execution_mode": "local_agent"},
        "gate": "G2_EXECUTION",
        "node_id": "m0",
        "outcome": "success",
        "evidence_refs": ["gwc://runs/run_dw_obs_m0_r2/start"],
    }
    e = GwcAdapter().from_durable_event(record)
    assert e.source_system == "gwc"
    assert e.source_event_id == "evt_a1b2c3d4_run_started"  # exact
    assert e.occurred_at == "2026-08-21T09:00:00Z"          # not 1970 placeholder
    assert e.event_type == "run_started"                    # canonical GWC verbatim
    assert e.gate == "G2_EXECUTION"
    assert e.outcome == "success"
    # structured actor preserved exactly (NOT coerced to "gwc-fastlane")
    assert e.actor == {"kind": "chatgpt", "id": "agent-hermes-mac", "execution_mode": "local_agent"}
    assert e.evidence_refs == ["gwc://runs/run_dw_obs_m0_r2/start"]
    assert e.read_only_projection is True


def test_gwc_adapter_rejects_fabricated_placeholder_paths():
    import pytest

    # missing occurred_at_utc -> must reject, never fall back to epoch
    with pytest.raises(ValueError):
        GwcAdapter().from_durable_event({
            "event_id": "e1", "run_id": "r", "sequence": 0, "event_type": "run_started",
            "actor": {"kind": "chatgpt", "id": "x"}, "gate": "G2_EXECUTION",
            "node_id": "m0", "outcome": "success",
        })
    # missing actor -> must reject, never fabricate "gwc-fastlane"
    with pytest.raises(ValueError):
        GwcAdapter().from_durable_event({
            "event_id": "e1", "run_id": "r", "sequence": 0, "event_type": "run_started",
            "occurred_at_utc": "2026-08-21T00:00:00Z", "gate": "G2_EXECUTION",
            "node_id": "m0", "outcome": "success",
        })


def test_gwc_adapter_from_json_list():
    text = ('[{"event_id":"e1","run_id":"r","sequence":0,"event_type":"run_started",'
            '"occurred_at_utc":"2026-08-21T00:00:00Z","actor":{"kind":"chatgpt","id":"x"},'
            '"gate":"G2_EXECUTION","node_id":"m0","outcome":"success"}]')
    events = GwcAdapter().from_json(text)
    assert events[0].source_event_id == "e1"
    assert events[0].actor == {"kind": "chatgpt", "id": "x"}


def test_gwc_adapter_does_not_map_payload_to_after():
    record = {
        "event_id": "evt_payload", "run_id": "r", "sequence": 0, "event_type": "run_started",
        "occurred_at_utc": "2026-08-21T00:00:00Z", "actor": {"kind": "chatgpt", "id": "x"},
        "gate": "G2_EXECUTION", "node_id": "m0", "outcome": "success",
        "payload": {"runtime_version": "1.0", "node_version": "1.0"},
        "evidence_refs": ["gwc://x"],
    }
    e = GwcAdapter().from_durable_event(record)
    # payload must NOT populate `after`; before/after stay NULL.
    assert e.after is None
    assert e.before is None
    # payload is preserved via source_digest/evidence, not `after`.
    assert e.source_digest is not None and e.source_digest.startswith("sha256:")
    assert e.evidence_refs == ["gwc://x"]


def test_gwc_adapter_is_read_only_no_scan():
    """Adapter maps records directly; it does NOT scan .gwc/tasks/*/g4/*.yaml
    nor fabricate gate_approved events."""
    adapter = GwcAdapter()
    record = {
        "event_id": "evt_x", "run_id": "r", "sequence": 0, "event_type": "run_started",
        "occurred_at_utc": "2026-08-21T00:00:00Z", "actor": {"kind": "chatgpt", "id": "x"},
        "gate": "G2_EXECUTION", "node_id": "m0", "outcome": "success",
    }
    evs = adapter.from_durable_event(record)
    assert evs.event_type == "run_started"  # verbatim, NOT gate_approved
    assert evs.gate == "G2_EXECUTION"
    # no read_gate_states / yaml-scan method exists anymore
    assert not hasattr(adapter, "read_gate_states")
