"""RunProjectionEvent v1 — the canonical normalized event envelope for dw-observation.

Read-only model. No Slack parsing, no governance mutation. Validated with
stdlib dataclasses only (no external deps) so the contract stays reviewable.

Hardening (Controller G2R1 semantic correction): direct construction REQUIRES
canonical identity (`source_event_id`, `run_id`) and `occurred_at`; there is no
epoch/empty default that could masquerade as source evidence. `from_dict` also
rejects missing/empty identity and unknown fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1"
PROJECTION_TYPE = "run_observatory"

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _normalize_ts(value) -> str:
    """Return an ISO-8601 UTC 'Z' string.

    Accepts an ISO string (with or without offset) or a numeric Unix epoch
    (seconds). Raises ValueError on anything else — no silent epoch fallback.
    """
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise ValueError(f"invalid occurred_at timestamp: {value!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RunProjectionEvent:
    # ---- REQUIRED canonical identity + timestamp (no fabrication defaults) ----
    occurred_at: str                 # exact source timestamp (no epoch default)
    run_id: str                      # exact source run id
    source_event_id: str             # EXACT source record id (no tc:{run}:{i})
    # ---- envelope constants (locked) ----
    schema_version: str = SCHEMA_VERSION
    projection_type: str = PROJECTION_TYPE
    sequence: int = 0
    source_system: str = ""
    gate: Optional[str] = None       # nullable; copied from source, never inferred
    node_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    event_type: str = ""             # open vocabulary (verbatim source kind)
    outcome: Optional[str] = None     # nullable; open vocabulary, copied from source
    actor: Any = None                # exact source actor (string OR structured object)
    summary: str = ""
    before: Optional[Dict[str, Any]] = None   # NULL unless source has named before-state
    after: Optional[Dict[str, Any]] = None    # NULL unless source has named after-state
    evidence_refs: List[str] = field(default_factory=list)
    authority_ref: Optional[str] = None
    source_digest: Optional[str] = None
    read_only_projection: bool = True

    def __post_init__(self) -> None:
        # Lock envelope constants.
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION!r}, got {self.schema_version!r}")
        if self.projection_type != PROJECTION_TYPE:
            raise ValueError(f"projection_type must be {PROJECTION_TYPE!r}, got {self.projection_type!r}")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 0:
            raise ValueError(f"sequence must be a non-negative int, got {self.sequence!r}")
        # Required canonical identity + timestamp must be present and non-empty.
        if not self.run_id or not str(self.run_id).strip():
            raise ValueError("run_id is required (canonical source identity)")
        if not self.source_event_id or not str(self.source_event_id).strip():
            raise ValueError("source_event_id is required (exact source record id)")
        if not self.event_type or not str(self.event_type).strip():
            raise ValueError("event_type is required")
        if not self.occurred_at or not str(self.occurred_at).strip():
            raise ValueError("occurred_at is required (exact source timestamp)")
        if not isinstance(self.read_only_projection, bool) or self.read_only_projection is not True:
            raise ValueError("read_only_projection must be True")
        self.occurred_at = _normalize_ts(self.occurred_at)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunProjectionEvent":
        allowed = set(cls.__dataclass_fields__.keys())
        # Required canonical fields must be present and non-empty.
        for req in ("occurred_at", "run_id", "source_event_id", "event_type"):
            if req not in data or not str(data.get(req, "")).strip():
                raise ValueError(f"missing or empty required field: {req}")
        unknown = set(data.keys()) - allowed
        if unknown:
            raise ValueError(f"unknown envelope fields: {sorted(unknown)}")
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "projection_type": self.projection_type,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "source_system": self.source_system,
            "source_event_id": self.source_event_id,
            "occurred_at": self.occurred_at,
            "gate": self.gate,
            "node_id": self.node_id,
            "parent_event_id": self.parent_event_id,
            "event_type": self.event_type,
            "outcome": self.outcome,
            "actor": self.actor,
            "summary": self.summary,
            "before": self.before,
            "after": self.after,
            "evidence_refs": self.evidence_refs,
            "authority_ref": self.authority_ref,
            "source_digest": self.source_digest,
            "read_only_projection": self.read_only_projection,
        }
