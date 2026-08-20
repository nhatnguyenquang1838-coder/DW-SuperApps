"""Tests for read-only adapters (no mutation, no Slack parsing)."""

from dw_observation.adapters import TaskControllerAdapter, GwcAdapter
from dw_observation.events import RunProjectionEvent


def test_tc_adapter_parses_structured_run_log():
    log = {
        "run_id": "R-1",
        "events": [
            {"kind": "run_started", "ts": "2026-08-21T09:00:00Z", "seq": 0},
            {"kind": "gate_approved", "ts": "2026-08-21T18:00:00Z", "seq": 1, "gate": "G2-X", "actor": "Human"},
        ],
    }
    events = TaskControllerAdapter().from_run_log(log)
    assert len(events) == 2
    assert all(e.run_id == "R-1" for e in events)
    assert events[0].kind == "run_started"
    assert events[1].gate == "G2-X"


def test_tc_adapter_rejects_malformed_event():
    import pytest

    log = {"run_id": "R-1", "events": [{"kind": "bad", "ts": "2026-08-21T00:00:00Z"}]}
    with pytest.raises(ValueError):
        TaskControllerAdapter().from_run_log(log)


def test_tc_adapter_from_json():
    text = '{"run_id":"R-2","events":[{"kind":"run_started","ts":"2026-08-21T00:00:00Z","seq":0}]}'
    events = TaskControllerAdapter().from_json(text)
    assert isinstance(events[0], RunProjectionEvent)
    assert events[0].run_id == "R-2"


def test_gwc_adapter_is_read_only(tmp_path):
    """GwcAdapter must not raise/modify; it only scans existing artifacts."""
    tasks = tmp_path / ".gwc" / "tasks" / "t1" / "g4"
    tasks.mkdir(parents=True)
    (tasks / "merge-approval.yaml").write_text("ok: true\n")
    adapter = GwcAdapter(tmp_path)
    evs = adapter.read_gate_states(run_id="R-9")
    assert len(evs) == 1
    assert evs[0].kind == "gate_approved"
    assert evs[0].gate == "G4"
    # ensure no writes happened (only the file we created exists)
    assert sorted(p.name for p in tasks.iterdir()) == ["merge-approval.yaml"]


def test_gwc_adapter_missing_root_raises():
    import pytest

    with pytest.raises(FileNotFoundError):
        GwcAdapter("/nonexistent/path/xyz")
