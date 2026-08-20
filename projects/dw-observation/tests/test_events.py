"""Tests for RunProjectionEvent v1 validation and parsing."""

from dw_observation.events import RunProjectionEvent, SCHEMA_VERSION, PROJECTION_TYPE


def test_valid_event_roundtrip():
    e = RunProjectionEvent.from_dict(
        {
            "occurred_at": "2026-08-21T18:26:00Z",
            "gate": "G2-DW-OBS-M0-20260821-R2",  # open vocabulary: lane id accepted verbatim
            "actor": "Human",
            "event_type": "gate_approved",
            "outcome": "approved",
            "source_event_id": "evt_real_0",
        }
    )
    assert e.event_type == "gate_approved"
    assert e.gate == "G2-DW-OBS-M0-20260821-R2"
    assert e.actor == "Human"
    assert e.outcome == "approved"
    assert e.sequence == 0
    assert e.projection_type == PROJECTION_TYPE
    assert e.read_only_projection is True


def test_canonical_gwc_event_type_and_gate_accepted_verbatim():
    # Source-compatible: GWC DurableEvent vocabulary must NOT be rejected.
    e = RunProjectionEvent(
        occurred_at="2026-08-21T09:05:00Z",
        event_type="node_completed",  # canonical GWC DurableEvent event_type
        gate="G2_EXECUTION",          # canonical GWC gate
        outcome="success",            # canonical GWC outcome
        actor={"kind": "chatgpt", "id": "agent-hermes-mac", "execution_mode": "local_agent"},
        source_event_id="evt_abc",
    )
    assert e.event_type == "node_completed"
    assert e.gate == "G2_EXECUTION"
    assert e.outcome == "success"
    # structured actor preserved exactly, not coerced to a string
    assert e.actor == {"kind": "chatgpt", "id": "agent-hermes-mac", "execution_mode": "local_agent"}


def test_invalid_event_type_rejected_when_empty():
    import pytest

    with pytest.raises(ValueError):
        RunProjectionEvent.from_dict(
            {"occurred_at": "2026-08-21T00:00:00Z", "event_type": ""}
        )


def test_unknown_field_rejected():
    import pytest

    with pytest.raises(ValueError):
        RunProjectionEvent.from_dict(
            {"occurred_at": "2026-08-21T00:00:00Z", "event_type": "run_started", "bogus": 1}
        )


def test_timestamp_normalized_to_utc_z():
    e = RunProjectionEvent(occurred_at="2026-08-21T12:00:00+02:00", event_type="run_started")
    assert e.occurred_at == "2026-08-21T10:00:00Z"


def test_timestamp_epoch_seconds_normalized():
    import datetime as _dt

    expected = "2026-08-21T10:00:00Z"
    epoch = int(_dt.datetime(2026, 8, 21, 10, 0, 0, tzinfo=_dt.timezone.utc).timestamp())
    e = RunProjectionEvent(occurred_at=epoch, event_type="run_started")
    assert e.occurred_at == expected


def test_negative_seq_rejected():
    import pytest

    with pytest.raises(ValueError):
        RunProjectionEvent(occurred_at="2026-08-21T00:00:00Z", sequence=0 - 1, event_type="run_started")


def test_read_only_projection_enforced_true():
    import pytest

    with pytest.raises(ValueError):
        RunProjectionEvent(
            occurred_at="2026-08-21T00:00:00Z",
            event_type="run_started",
            read_only_projection=False,
        )


def test_actor_may_be_null_or_string_or_structured():
    s = RunProjectionEvent(occurred_at="2026-08-21T00:00:00Z", event_type="run_started", actor="Human")
    assert s.actor == "Human"
    o = RunProjectionEvent(
        occurred_at="2026-08-21T00:00:00Z",
        event_type="run_started",
        actor={"kind": "chatgpt", "id": "x"},
    )
    assert o.actor == {"kind": "chatgpt", "id": "x"}


def test_schema_version_locked():
    import pytest

    with pytest.raises(ValueError):
        RunProjectionEvent(occurred_at="2026-08-21T00:00:00Z", schema_version="2")


def test_full_v1_envelope_fields_present():
    e = RunProjectionEvent(
        run_id="R-1",
        sequence=3,
        source_system="taskcontroller",
        source_event_id="evt_real_3",
        occurred_at="2026-08-21T18:26:00Z",
        gate="G2_EXECUTION",
        node_id="71",
        parent_event_id="evt_real_2",
        event_type="node_progress",
        outcome="done",
        actor="Ctrl",
        summary="Node 71 done",
        before={"status": "active"},
        after={"status": "done"},
        evidence_refs=["artifacts/run.json"],
        authority_ref="G2-X",
        source_digest="sha256:abc",
    )
    assert e.schema_version == SCHEMA_VERSION
    assert e.projection_type == PROJECTION_TYPE
    assert e.run_id == "R-1"
    assert e.sequence == 3
    assert e.source_system == "taskcontroller"
    assert e.source_event_id == "evt_real_3"
    assert e.node_id == "71"
    assert e.parent_event_id == "evt_real_2"
    assert e.before == {"status": "active"}
    assert e.after == {"status": "done"}
    assert e.evidence_refs == ["artifacts/run.json"]
    assert e.authority_ref == "G2-X"
    assert e.source_digest == "sha256:abc"
    assert e.read_only_projection is True
