"""RunProjectionEvent v1 — the canonical event record projected by dw-observation.

Read-only model. No Slack parsing, no governance mutation. Validated by
pydantic-style dataclasses (stdlib only to avoid dependency surface).

Event kinds (closed set for v1):
  - run_started
  - gate_approved        (g0..g4, human-issued)
  - gate_released        (controller release, e.g. G2 -> M0)
  - node_progress        (DAG node state change)
  - projection_snapshot  (periodic/terminal capture)
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


VALID_KINDS = frozenset(
    {
        "run_started",
        "gate_approved",
        "gate_released",
        "node_progress",
        "projection_snapshot",
    }
)


def _parse_ts(value: Any) -> str:
    """Normalize an ISO-8601 timestamp to UTC 'Z' form.

    Accepts: ISO string, epoch seconds (int/float), or datetime. Returns a
    canonical UTC string. This is the *only* time normalization in the reducer
    path; emitted timestamps are otherwise passed through verbatim.
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


@dataclass(frozen=True)
class RunProjectionEvent:
    """A single immutable projection event (v1).

    `seq` provides a deterministic tie-breaker independent of wall-clock; the
    reducer orders by (ts, seq). `data` is an opaque, schema-loose payload so
    the event model never has to evolve for every new governance field.
    """

    kind: str
    ts: str
    seq: int = 0
    run_id: Optional[str] = None
    node: Optional[str] = None
    gate: Optional[str] = None
    actor: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in VALID_KINDS:
            raise ValueError(
                f"invalid event kind {self.kind!r}; allowed: {sorted(VALID_KINDS)}"
            )
        object.__setattr__(self, "ts", _parse_ts(self.ts))
        if self.seq < 0:
            raise ValueError("seq must be >= 0")
        if not isinstance(self.data, dict):
            raise TypeError("data must be a dict")

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "RunProjectionEvent":
        known = {
            "kind",
            "ts",
            "seq",
            "run_id",
            "node",
            "gate",
            "actor",
            "data",
        }
        extra = set(raw.keys()) - known
        if extra:
            raise ValueError(f"unknown event fields: {sorted(extra)}")
        return cls(
            kind=raw["kind"],
            ts=raw["ts"],
            seq=raw.get("seq", 0),
            run_id=raw.get("run_id"),
            node=raw.get("node"),
            gate=raw.get("gate"),
            actor=raw.get("actor"),
            data=raw.get("data", {}) or {},
        )
