"""Golden fixture loader. Local JSON only — no network, no Slack.

The golden event fixtures contain CANONICAL SOURCE records (TaskController
AuditEvent / GWC DurableEvent), NOT normalized projection envelopes. This
loader routes each source record through the real adapter (TaskControllerAdapter
or GwcAdapter) so the projection event carries the source-computed digest —
provenance semantics are preserved (source_event_id / source_digest / actor /
before / after survive source -> adapter -> projection exactly).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .adapters import GwcAdapter, TaskControllerAdapter
from .events import RunProjectionEvent

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def _detect_source(fixture: Dict[str, Any]) -> str:
    """Infer the canonical source schema from the first event record.

    AuditEvent -> 'taskcontroller'; DurableEvent -> 'gwc'.
    """
    events = fixture.get("events") or []
    if events:
        first = events[0]
        if "decision_kind" in first or first.get("source") == "taskcontroller":
            return "taskcontroller"
        if first.get("artifact_type") == "durable-event" or "occurred_at_utc" in first:
            return "gwc"
    # Static routing fallback for known fixture names.
    if "gwc" in fixture.get("run_id_dup_note", "") or "DurableEvent" in fixture.get("run_id_dup_note", ""):
        return "gwc"
    return "taskcontroller"


def load_event_stream(name: str) -> List[RunProjectionEvent]:
    """Load a golden source-record fixture and map it via the real adapter.

    The fixture is canonical SOURCE data (AuditEvent / DurableEvent). It is
    routed through TaskControllerAdapter or GwcAdapter; the resulting
    RunProjectionEvent carries the adapter-computed source_digest (never a
    digest derived from a normalized envelope).
    """
    path = _FIXTURE_ROOT / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {path}")
    fixture = json.loads(path.read_text())
    source = _detect_source(fixture)

    if source == "gwc":
        adapter, key = GwcAdapter(), "event_id"
    else:
        adapter, key = TaskControllerAdapter(), "event_id"

    records = fixture["events"]
    return [
        _map(adapter, source, rec, key)
        for rec in records
    ]


def _map(adapter: Any, source: str, record: Dict[str, Any], key: str) -> RunProjectionEvent:
    if source == "gwc":
        return adapter.from_durable_event(record)  # type: ignore[attr-defined]
    return adapter.from_audit_event(record)  # type: ignore[attr-defined]


def load_expected_projection(name: str) -> Dict[str, Any]:
    """Load a golden expected projection fixture by base name."""
    path = _FIXTURE_ROOT / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {path}")
    return json.loads(path.read_text())
