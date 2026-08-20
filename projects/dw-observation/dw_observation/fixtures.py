"""Golden fixture loader. Local JSON only — no network, no Slack."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from .events import RunProjectionEvent

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def _derive_digest(record: Dict[str, Any]) -> str:
    """Deterministic digest of a source record when it carries no digest.

    Mirrors the adapters: a canonical v1 event always carries provenance. The
    golden fixtures are source records, so we fingerprint their canonical
    content rather than let an event silently carry no digest.
    """
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_event_stream(name: str) -> List[RunProjectionEvent]:
    """Load a golden event stream fixture by base name (without .json)."""
    path = _FIXTURE_ROOT / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {path}")
    raw = json.loads(path.read_text())
    events = []
    for e in raw["events"]:
        # Canonical v1 requires provenance; derive it when the source record
        # did not include one (golden fixtures are source records).
        if not e.get("source_digest"):
            e = dict(e)
            e["source_digest"] = _derive_digest(e)
        events.append(RunProjectionEvent.from_dict(e))
    return events


def load_expected_projection(name: str) -> Dict[str, Any]:
    """Load a golden expected projection fixture by base name."""
    path = _FIXTURE_ROOT / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {path}")
    return json.loads(path.read_text())
