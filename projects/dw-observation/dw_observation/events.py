"""RunProjectionEvent v1 — the canonical normalized event envelope for dw-observation.

Read-only model. No Slack parsing, no governance mutation. Validated with
stdlib dataclasses only (no external dependency surface).

M0 / SCRUM-555 (#71) requires the *explicit* normalized v1 envelope so that
replay/reviewer traceability can rely on exact source identity, evidence,
authority, before/after state, and outcome. A generic opaque ``data`` payload
is intentionally NOT part of the contract — every traceability field is a
first-class attribute.

Field contract (all v1 events, frozen):
  schema_version      str   — envelope schema, always "1"
  projection_type    str   — always "run_observatory"
  run_id             str   — governing run id (e.g. DW-OBS-M0-20260821-R2)
  sequence           int   — deterministic ordering key within the run
  source_system      str   — provenance system ("taskcontroller" | "gwc" | ...)
  source_event_id    str   — exact id of the originating record in source_system
  occurred_at        str   — canonical UTC 'Z' timestamp the event occurred
  gate               str?  — governance gate id (nullable; never invented)
  node_id            str?  — DAG/exec node id (nullable)
  parent_event_id    str?  — event this descended from (nullable)
  event_type         str    — closed vocabulary (see EVENT_TYPES)
  outcome            str?   — outcome vocabulary (see OUTCOME_TYPES) or None
  actor              str?   — actor/human/system that caused the event
  summary            str    — human-readable one-line description
  before             dict?  — state snapshot before the event (nullable)
  after              dict?  — state snapshot after the event (nullable)
  evidence_refs      list   — source artifact references (paths/urls/ids)
  authority_ref      str?   — governance authority reference (approval id, ...)
  source_digest      str?   — deterministic digest of the source record
  read_only_projection bool — always True for this app (projection only)

``read_only_projection`` is enforced to True on construction and cannot be
set False by any adapter path.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1"
PROJECTION_TYPE = "run_observatory"

EVENT_TYPES = frozenset(
    {
        "run_started",
        "gate_approved",
        "gate_released",
        "node_progress",
        "projection_snapshot",
    }
)

OUTCOME_TYPES = frozenset(
    {
        "approved",
        "released",
        "active",
        "done",
        "blocked",
        "started",
        "captured",
        None,  # outcome may be unknown/nullable
    }
)

# Closed set of known gate ids. The envelope never *invents* a TC gate; gates
# come from source artifacts. None is allowed for non-gate events.
KNOWN_GATES = frozenset(
    {
        "G0",
        "G1",
        "G2",
        "G3",
        "G4",
        "G5",
        "G6",
        None,
    }
)


def _parse_ts(value: Any) -> str:
    """Normalize an ISO-8601 timestamp to canonical UTC 'Z' form.

    Accepts ISO string, epoch seconds (int/float), or datetime. The *only*
    time normalization used; emitted timestamps are otherwise verbatim.
    """
    if isinstance(value, (int, float)):
        dt = _dt.datetime.fromtimestamp(value, tz=_dt.timezone.utc)
    elif isinstance(value, _dt.datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
    elif isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = _dt.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
    else:
        raise TypeError(f"unsupported timestamp type: {type(value)!r}")
    dt = dt.astimezone(_dt.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_digest(raw: Dict[str, Any]) -> str:
    """Deterministic SHA-256 of a source record (canonical JSON)."""
    canonical = _canonical_json(raw)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class RunProjectionEvent:
    """A single immutable v1 projection event (explicit envelope)."""

    schema_version: str = SCHEMA_VERSION
    projection_type: str = PROJECTION_TYPE
    run_id: Optional[str] = None
    sequence: int = 0
    source_system: str = "taskcontroller"
    source_event_id: Optional[str] = None
    occurred_at: str = "1970-01-01T00:00:00Z"
    gate: Optional[str] = None
    node_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    event_type: str = "projection_snapshot"
    outcome: Optional[str] = None
    actor: Optional[str] = None
    summary: str = ""
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    evidence_refs: List[str] = None  # type: ignore[assignment]
    authority_ref: Optional[str] = None
    source_digest: Optional[str] = None
    read_only_projection: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        if self.projection_type != PROJECTION_TYPE:
            raise ValueError(
                f"projection_type must be {PROJECTION_TYPE!r}, got {self.projection_type!r}"
            )
        # Read-only invariant is non-negotiable for this projection app.
        if self.read_only_projection is not True:
            raise ValueError("read_only_projection must be True")
        object.__setattr__(self, "occurred_at", _parse_ts(self.occurred_at))
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.event_type not in EVENT_TYPES:
            raise ValueError(
                f"invalid event_type {self.event_type!r}; allowed: {sorted(EVENT_TYPES)}"
            )
        if self.outcome not in OUTCOME_TYPES:
            raise ValueError(
                f"invalid outcome {self.outcome!r}; allowed: {sorted([o for o in OUTCOME_TYPES if o is not None])} or None"
            )
        # Never invent a TC gate. Allow only known gate prefixes or None.
        if self.gate is not None and not _is_known_gate(self.gate):
            raise ValueError(
                f"unknown/forbidden gate {self.gate!r}; gates must come from source artifacts"
            )
        if self.evidence_refs is None:
            object.__setattr__(self, "evidence_refs", [])
        if not isinstance(self.evidence_refs, list):
            raise TypeError("evidence_refs must be a list")
        if self.before is not None and not isinstance(self.before, dict):
            raise TypeError("before must be a dict or None")
        if self.after is not None and not isinstance(self.after, dict):
            raise TypeError("after must be a dict or None")

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "RunProjectionEvent":
        known = {
            "schema_version",
            "projection_type",
            "run_id",
            "sequence",
            "source_system",
            "source_event_id",
            "occurred_at",
            "gate",
            "node_id",
            "parent_event_id",
            "event_type",
            "outcome",
            "actor",
            "summary",
            "before",
            "after",
            "evidence_refs",
            "authority_ref",
            "source_digest",
            "read_only_projection",
        }
        extra = set(raw.keys()) - known
        if extra:
            raise ValueError(f"unknown event fields: {sorted(extra)}")
        if "occurred_at" not in raw:
            raise ValueError("occurred_at is required")
        return cls(
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
            projection_type=raw.get("projection_type", PROJECTION_TYPE),
            run_id=raw.get("run_id"),
            sequence=raw.get("sequence", 0),
            source_system=raw.get("source_system", "taskcontroller"),
            source_event_id=raw.get("source_event_id"),
            occurred_at=raw["occurred_at"],
            gate=raw.get("gate"),
            node_id=raw.get("node_id"),
            parent_event_id=raw.get("parent_event_id"),
            event_type=raw.get("event_type", "projection_snapshot"),
            outcome=raw.get("outcome"),
            actor=raw.get("actor"),
            summary=raw.get("summary", ""),
            before=raw.get("before"),
            after=raw.get("after"),
            evidence_refs=raw.get("evidence_refs", []),
            authority_ref=raw.get("authority_ref"),
            source_digest=raw.get("source_digest"),
            read_only_projection=raw.get("read_only_projection", True),
        )


def _is_known_gate(gate: str) -> bool:
    """Gates must be explicit source artifacts, not invented TC gates.

    Accepts the canonical G0..G6 labels and any ``G<n>-<opaque>`` lane id
    (as found in governance artifacts, e.g. ``G2-DW-OBS-M0-20260821-R2``).
    Rejects anything that does not look like a governance gate reference.
    """
    gate = gate.strip()
    if gate in KNOWN_GATES:
        return True
    # Lane-style ids: G<digits>-<rest> (e.g. G2-DW-OBS-M0-20260821-R2)
    import re

    return bool(re.match(r"^G[0-9]+(-[A-Za-z0-9_.]+)+$", gate))
