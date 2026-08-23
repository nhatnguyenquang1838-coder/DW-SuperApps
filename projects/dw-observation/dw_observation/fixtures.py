"""Golden fixture loader. Local JSON only — no network, no Slack.

The golden event fixtures contain CANONICAL SOURCE records (TaskController
AuditEvent / GWC DurableEvent), NOT normalized projection envelopes. This
loader routes each source record through the real adapter (TaskControllerAdapter
or GwcAdapter) so the projection event carries the source-computed digest —
provenance semantics are preserved (source_event_id / source_digest / actor /
before / after survive source -> adapter -> projection exactly).

Routing is EXPLICIT: each fixture must declare a top-level
``source_system: "taskcontroller" | "gwc"``. Heuristic guessing is intentionally
forbidden so fixture/contract drift is caught.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .adapters import GwcAdapter, TaskControllerAdapter
from .events import RunProjectionEvent

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures"

_KNOWN_SOURCES = ("taskcontroller", "gwc")


def _require_source(fixture: Dict[str, Any]) -> str:
    """Require an explicit top-level ``source_system``; no heuristic fallback."""
    src = fixture.get("source_system")
    if src not in _KNOWN_SOURCES:
        raise ValueError(
            f"fixture must declare explicit top-level source_system in {_KNOWN_SOURCES!r}, got {src!r}"
        )
    return src  # type: ignore[return-value]


def load_event_stream(name: str) -> List[RunProjectionEvent]:
    """Load a golden source-record fixture and map it via the real adapter.

    The fixture is canonical SOURCE data (AuditEvent / DurableEvent). It is
    routed through TaskControllerAdapter or GwcAdapter (chosen by the explicit
    top-level ``source_system``); the resulting RunProjectionEvent carries the
    adapter-computed source_digest (never a digest derived from a normalized
    envelope).
    """
    path = _FIXTURE_ROOT / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {path}")
    fixture = json.loads(path.read_text())
    source = _require_source(fixture)

    if source == "gwc":
        adapter = GwcAdapter()
    else:
        adapter = TaskControllerAdapter()

    records = fixture["events"]
    return [_map(adapter, source, rec) for rec in records]


def _map(adapter: Any, source: str, record: Dict[str, Any]) -> RunProjectionEvent:
    if source == "gwc":
        return adapter.from_durable_event(record)  # type: ignore[attr-defined]
    return adapter.from_audit_event(record)  # type: ignore[attr-defined]


def load_expected_projection(name: str) -> Dict[str, Any]:
    """Load a golden expected projection fixture by base name."""
    path = _FIXTURE_ROOT / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {path}")
    return json.loads(path.read_text())
