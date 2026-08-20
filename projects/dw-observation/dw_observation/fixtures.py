"""Golden fixture loader. Local JSON only — no network, no Slack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .events import RunProjectionEvent

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def load_event_stream(name: str) -> List[RunProjectionEvent]:
    """Load a golden event stream fixture by base name (without .json)."""
    path = _FIXTURE_ROOT / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {path}")
    raw = json.loads(path.read_text())
    return [RunProjectionEvent.from_dict(e) for e in raw["events"]]


def load_expected_projection(name: str) -> Dict[str, Any]:
    """Load a golden expected projection fixture by base name."""
    path = _FIXTURE_ROOT / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {path}")
    return json.loads(path.read_text())
