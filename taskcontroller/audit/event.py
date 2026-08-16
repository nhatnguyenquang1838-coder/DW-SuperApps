from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any
import json


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    timestamp: str        # ISO 8601 UTC, caller-supplied
    run_id: str
    source: str
    decision_kind: str

    node_id: str = ""
    actor: str = ""
    authority_ref: str = ""
    payload_summary: str = ""
    raw_payload_ref: str = ""

    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    annotations: dict[str, Any] = field(default_factory=dict)
    version: int = 0

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id is required")
        if not self.timestamp:
            raise ValueError("timestamp is required")
        if not self.run_id:
            raise ValueError("run_id is required")
        if not self.source:
            raise ValueError("source is required")
        if not self.decision_kind:
            raise ValueError("decision_kind is required")
        if len(self.payload_summary) > 300:
            raise ValueError("payload_summary exceeds 300 characters")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEvent":
        evidence = data.get("evidence_refs", ())
        if isinstance(evidence, list):
            data["evidence_refs"] = tuple(evidence)
        return cls(**data)

    @classmethod
    def from_json(cls, payload: str) -> "AuditEvent":
        return cls.from_dict(json.loads(payload))
