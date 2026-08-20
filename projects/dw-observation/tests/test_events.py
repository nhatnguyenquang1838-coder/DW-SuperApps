"""Tests for RunProjectionEvent v1 validation and parsing."""

from dw_observation.events import RunProjectionEvent, VALID_KINDS


def test_valid_event_roundtrip():
    e = RunProjectionEvent.from_dict(
        {"kind": "gate_approved", "ts": "2026-08-21T18:26:00Z", "gate": "G2-X", "actor": "Human"}
    )
    assert e.kind == "gate_approved"
    assert e.gate == "G2-X"
    assert e.actor == "Human"
    assert e.seq == 0


def test_invalid_kind_rejected():
    import pytest

    with pytest.raises(ValueError):
        RunProjectionEvent.from_dict({"kind": "not_a_kind", "ts": "2026-08-21T00:00:00Z"})


def test_unknown_field_rejected():
    import pytest

    with pytest.raises(ValueError):
        RunProjectionEvent.from_dict(
            {"kind": "run_started", "ts": "2026-08-21T00:00:00Z", "bogus": 1}
        )


def test_timestamp_normalized_to_utc_z():
    e = RunProjectionEvent(kind="run_started", ts="2026-08-21T12:00:00+02:00")
    assert e.ts == "2026-08-21T10:00:00Z"


def test_timestamp_epoch_seconds_normalized():
    import datetime as _dt

    expected = "2026-08-21T10:00:00Z"
    epoch = int(
        _dt.datetime(2026, 8, 21, 10, 0, 0, tzinfo=_dt.timezone.utc).timestamp()
    )
    e = RunProjectionEvent(kind="run_started", ts=epoch)
    assert e.ts == expected


def test_negative_seq_rejected():
    import pytest

    with pytest.raises(ValueError):
        RunProjectionEvent(kind="run_started", ts="2026-08-21T00:00:00Z", seq=0 - 1)


def test_valid_kinds_closed_set():
    assert "run_started" in VALID_KINDS
    assert "gate_released" in VALID_KINDS
    assert len(VALID_KINDS) == 5
