"""RunProjectionEvent v1 — the canonical normalized event envelope for dw-observation.

Immutable, read-only model (frozen dataclass). No Slack parsing, no governance
mutation. Validated with stdlib dataclasses only (no external deps) so the
contract stays reviewable.

Hardening (Controller G2R1 semantic correction + final hardening):
  - The envelope is FROZEN: a valid event cannot be mutated after construction
    (no tampering with read_only_projection, identity, timestamp, evidence).
  - Direct construction REQUIRES canonical identity (source_event_id, run_id),
    occurred_at, and a canonical source_system (one of {taskcontroller, gwc}).
    There is no epoch/empty default that could masquerade as source evidence.
  - source_digest is REQUIRED (non-empty) for canonical v1 events: both adapters
    always compute a deterministic digest, so a direct event must carry provenance.
  - from_dict rejects missing/empty identity, unknown fields, and off-vocabulary
    source_system / missing digest.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1"
PROJECTION_TYPE = "run_observatory"

# Canonical source systems (per Controller exact-source contract).
KNOWN_SOURCE_SYSTEMS = ("taskcontroller", "gwc")

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _normalize_ts(value) -> str:
    """Return an ISO-8601 UTC 'Z' string.

    Accepts an ISO string (with explicit offset or trailing 'Z') or a numeric
    Unix epoch (seconds). Rejects timezone-NAIVE ISO strings (no offset and not
    'Z') — assuming UTC for a naive time would fabricate timezone provenance,
    which violates the exact-source contract. Raises ValueError otherwise.
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
        # Naive ISO string: explicit timezone is required; never assume UTC.
        raise ValueError(
            f"occurred_at must be timezone-aware (offset or 'Z') or a numeric "
            f"epoch; got naive timestamp {value!r}"
        )
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class RunProjectionEvent:
    # ---- REQUIRED canonical identity + timestamp (no fabrication defaults) ----
    occurred_at: str                 # exact source timestamp (no epoch default)
    run_id: str                      # exact source run id
    source_event_id: str             # EXACT source record id (no tc:{run}:{i})
    # ---- REQUIRED canonical source + provenance ----
    source_system: str               # one of KNOWN_SOURCE_SYSTEMS
    source_digest: str               # non-empty deterministic digest of source
    # ---- envelope constants (locked) ----
    schema_version: str = SCHEMA_VERSION
    projection_type: str = PROJECTION_TYPE
    sequence: int = 0
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
        if self.source_system not in KNOWN_SOURCE_SYSTEMS:
            raise ValueError(
                f"source_system must be one of {KNOWN_SOURCE_SYSTEMS!r}, got {self.source_system!r}"
            )
        if not self.source_digest or not str(self.source_digest).strip():
            raise ValueError("source_digest is required (canonical v1 provenance)")
        if not isinstance(self.read_only_projection, bool) or self.read_only_projection is not True:
            raise ValueError("read_only_projection must be True")
        # Normalize timestamp in place (frozen dataclasses allow __post_init__ writes).
        object.__setattr__(self, "occurred_at", _normalize_ts(self.occurred_at))
        # Deep immutability: isolate nested mutable fields from the caller's
        # source objects so later mutation of the source cannot alter this
        # frozen event, and so structured actor copies are independent.
        object.__setattr__(self, "actor", copy.deepcopy(self.actor))
        object.__setattr__(self, "before", copy.deepcopy(self.before))
        object.__setattr__(self, "after", copy.deepcopy(self.after))
        object.__setattr__(self, "evidence_refs", copy.deepcopy(self.evidence_refs))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunProjectionEvent":
        allowed = set(cls.__dataclass_fields__.keys())
        # Required canonical fields must be present and non-empty.
        for req in ("occurred_at", "run_id", "source_event_id", "event_type",
                    "source_system", "source_digest"):
            if req not in data or not str(data.get(req, "")).strip():
                raise ValueError(f"missing or empty required field: {req}")
        unknown = set(data.keys()) - allowed
        if unknown:
            raise ValueError(f"unknown envelope fields: {sorted(unknown)}")
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        # Return DEEP copies of nested mutable fields so callers cannot mutate
        # this frozen event through the returned mapping (deep immutability).
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
            "actor": copy.deepcopy(self.actor),
            "summary": self.summary,
            "before": copy.deepcopy(self.before),
            "after": copy.deepcopy(self.after),
            "evidence_refs": copy.deepcopy(self.evidence_refs),
            "authority_ref": self.authority_ref,
            "source_digest": self.source_digest,
            "read_only_projection": self.read_only_projection,
        }
