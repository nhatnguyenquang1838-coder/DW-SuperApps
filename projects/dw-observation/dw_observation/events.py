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
  run_id             str?  — governing run id (e.g. DW-OBS-M0-20260821-R2)
  sequence           int   — deterministic ordering key from the SOURCE ledger
  source_system      str   — provenance system ("taskcontroller" | "gwc" | ...)
  source_event_id    str?  — EXACT id of the originating record in source_system
  occurred_at        str   — canonical UTC 'Z' timestamp the event occurred
  gate               str?  — governance gate id (NULLABLE; never invented)
  node_id            str?  — DAG/exec node id (nullable)
  parent_event_id    str?  — event this descended from (nullable)
  event_type         str    — OPEN vocabulary (verbatim source decision/event kind)
  outcome            str?   — OPEN vocabulary, nullable (never guessed)
  actor              Any?   — exact source actor (string OR structured object)
  summary            str    — human-readable one-line description
  before             dict?  — state snapshot before the event (nullable)
  after              dict?  — state snapshot after the event (nullable)
  evidence_refs      list   — source artifact references (paths/urls/ids)
  authority_ref      str?   — governance authority reference (nullable)
  source_digest      str?   — deterministic digest of the source record
  read_only_projection bool — always True for this app (projection only)

Vocabulary discipline (source-compatible, NOT envelope-restricted):
  ``event_type``, ``outcome``, and ``gate`` are OPEN vocabularies. The envelope
  carries whatever the canonical source record declares verbatim — it does NOT
  restrict to a closed synthetic set, so it can never reject canonical source
  truth (GWC DurableEvent event_types/gates/outcomes, TC AuditEvent
  decision_kind, etc.). The "never invent a gate/outcome" discipline lives in
  the *adapters*, which only copy gate/outcome from the source record and leave
  them NULL when the source does not provide them.

``actor`` is preserved EXACTLY, including a structured object such as the GWC
DurableEvent actor ``{kind, id, execution_mode?}``. The projection must never
coerce an exact source actor into an invented string.

``read_only_projection`` is enforced to True on construction and cannot be
set False by any adapter path.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1"
PROJECTION_TYPE = "run_observatory"


def _parse_ts(value: Any) -> str:
    """Normalize an ISO-8601 timestamp to canonical UTC 'Z' form.

    Accepts ISO string, epoch seconds (int/float), or datetime. Only the
    timezone *representation* is normalized; the instant is never changed. The
    *only* time normalization used; emitted timestamps are otherwise verbatim.
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
    return "sha256:" + hashlib.sha256(_canonical_json(raw).encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and len(value) > 0


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
    actor: Optional[Any] = None
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
        if not _is_nonempty_str(self.event_type):
            raise ValueError(f"event_type must be a non-empty string, got {self.event_type!r}")
        # event_type / outcome / gate are OPEN (source-compatible) vocabularies.
        # The envelope carries source truth verbatim; it must not reject
        # canonical source values. Only basic type/shape is enforced here.
        if self.outcome is not None and not _is_nonempty_str(self.outcome):
            raise ValueError(f"outcome must be a non-empty string or None, got {self.outcome!r}")
        if self.gate is not None and not _is_nonempty_str(self.gate):
            raise ValueError(f"gate must be a non-empty string or None, got {self.gate!r}")
        if self.evidence_refs is None:
            object.__setattr__(self, "evidence_refs", [])
        if not isinstance(self.evidence_refs, list):
            raise TypeError("evidence_refs must be a list")
        if self.before is not None and not isinstance(self.before, dict):
            raise TypeError("before must be a dict or None")
        if self.after is not None and not isinstance(self.after, dict):
            raise TypeError("after must be a dict or None")
        # actor may be a string OR a structured object (e.g. GWC
        # {kind,id,execution_mode?}); preserve it exactly, never coerce.

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
