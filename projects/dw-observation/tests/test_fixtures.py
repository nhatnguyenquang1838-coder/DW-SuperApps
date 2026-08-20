"""Tests for golden fixture loading (canonical source records -> adapter -> projection)."""

from pathlib import Path
from typing import Any, Dict

from dw_observation.adapters import TaskControllerAdapter
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
    # Faithful canonical source: before/after present as {} where the source
    # defaults them; the adapter carries them verbatim (not coerced to None).
    assert e0.before == {}
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


# --- Source-fidelity: fixture records are faithful canonical source objects ---
def _canonical_audit_event(record: Dict[str, Any]):
    """Construct an exact-shaped TaskController AuditEvent source object.

    The real ``taskcontroller.audit.event.AuditEvent`` class is not present in
    this worktree (it lives on the TaskController repo/branch), so we mirror its
    canonical defaults/types exactly (node_id='', actor='', authority_ref='',
    payload_summary='', raw_payload_ref='', before={}, after={},
    evidence_refs=list, annotations={}, version=1 int). The point is to prove
    each fixture record serializes to a deterministic contract-compatible dict
    BEFORE routing through TaskControllerAdapter, catching fixture/contract drift.
    """
    return {
        "event_id": record["event_id"],
        "timestamp": record["timestamp"],
        "run_id": record["run_id"],
        "source": record["source"],
        "decision_kind": record["decision_kind"],
        "node_id": record.get("node_id", ""),
        "actor": record.get("actor", ""),
        "authority_ref": record.get("authority_ref", ""),
        "payload_summary": record.get("payload_summary", ""),
        "raw_payload_ref": record.get("raw_payload_ref", ""),
        "sequence": record["sequence"],
        "before": record.get("before", {}),
        "after": record.get("after", {}),
        "evidence_refs": list(record.get("evidence_refs", [])),
        "annotations": record.get("annotations", {}),
        "version": int(record.get("version", 1)),
    }


def test_tc_fixture_records_are_faithful_canonical_source_objects():
    import json as _json

    fixture = _json.loads(
        (Path(__file__).resolve().parent.parent / "fixtures" / "run_scrum555_m0.json").read_text()
    )
    assert fixture["source_system"] == "taskcontroller"
    for rec in fixture["events"]:
        # Faithful serialized types (canonical defaults are "" / {} / [] / int 1;
        # explicit source values like node_id="71" remain as-is — never null).
        assert rec["node_id"] in ("",) or isinstance(rec["node_id"], str)
        assert rec["actor"] == "" or isinstance(rec["actor"], str)
        assert rec["authority_ref"] == "" or isinstance(rec["authority_ref"], str)
        assert rec["raw_payload_ref"] == ""
        assert isinstance(rec["before"], dict)
        assert isinstance(rec["after"], dict)
        assert isinstance(rec["evidence_refs"], list)
        assert isinstance(rec["annotations"], dict)
        assert isinstance(rec["version"], int) and rec["version"] == 1

        # Deterministic serialization-to-dict succeeds and round-trips, proving
        # the fixture record is a contract-compatible source object before any
        # adapter routing.
        src = _canonical_audit_event(rec)
        serialized = _json.loads(_json.dumps(src, sort_keys=True, default=str))
        assert serialized["event_id"] == rec["event_id"]
        assert serialized["version"] == 1
        # Routing the faithful source object through the real adapter succeeds.
        ev = TaskControllerAdapter().from_audit_event(src)
        assert ev.source_event_id == rec["event_id"]
        assert ev.source_digest.startswith("sha256:")

