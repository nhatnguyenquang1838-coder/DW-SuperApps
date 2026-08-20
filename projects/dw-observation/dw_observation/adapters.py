"""Read-only adapters for dw-observation.

These adapters only *read* external state and emit RunProjectionEvent (v1)
records. They never mutate TaskController, GWC, governance, Slack, or any repo.

Adapter contract (v1 envelope):
  - Preserve the EXACT source identity: ``source_system`` + ``source_event_id``
    are copied verbatim from the canonical source record (AuditEvent.event_id,
    DurableEvent.event_id). No synthesized ``tc:{run_id}:{index}`` ids.
  - Preserve the deterministic ``sequence`` from the SOURCE ledger. No invented
    index, no epoch fallback.
  - Preserve ``occurred_at`` exactly (only timezone representation is
    canonicalized to 'Z'). Never fabricate a timestamp.
  - Preserve ``actor`` EXACTLY, including a structured object such as the GWC
    DurableEvent actor ``{kind, id, execution_mode?}``. Never coerce the exact
    source actor into an invented string.
  - ``gate`` / ``outcome`` are copied verbatim from the source record and left
    NULL when the source does not provide them. The adapter never invents a
    gate or outcome.
  - ``source_digest`` is a deterministic digest of the complete source record
    when the source does not already provide one.

Source bindings (per Controller exact-source contract):
  - TaskController: canonical AuditEvent
    (DW-SuperApps/main@945223f.../taskcontroller/audit/event.py).
  - GWC: canonical DurableEvent
    (gwc/pre-prod@10deaa4d.../schemas/runtime/durable-event.schema.json).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .events import RunProjectionEvent, compute_digest


# ---------------------------------------------------------------------------
# TaskController adapter — binds to the canonical AuditEvent record.
# ---------------------------------------------------------------------------
class TaskControllerAdapter:
    """Reads canonical TaskController AuditEvent records (no legacy fabrication).

    Input contract: each record is a TC AuditEvent dict with at least
    ``event_id``, ``run_id``, ``sequence``, ``decision_kind``, ``timestamp``.
    Legacy short-form / ``tc:{run_id}:{index}`` fabrication has been removed.
    """

    source_system = "taskcontroller"

    def from_audit_event(self, record: Dict[str, Any]) -> RunProjectionEvent:
        # Required source identity — never fabricated.
        event_id = record.get("event_id")
        run_id = record.get("run_id")
        sequence = record.get("sequence")
        decision_kind = record.get("decision_kind")
        timestamp = record.get("timestamp")

        if not event_id:
            raise ValueError("AuditEvent.event_id is required (cannot fabricate source identity)")
        if run_id is None:
            raise ValueError("AuditEvent.run_id is required")
        if sequence is None:
            raise ValueError("AuditEvent.sequence is required (a real ledger sequence; not synthesized)")
        if not decision_kind:
            raise ValueError("AuditEvent.decision_kind is required (maps to event_type)")
        if timestamp is None:
            raise ValueError("AuditEvent.timestamp is required (cannot fabricate occurred_at)")

        # Preserve exact source evidence; gate/outcome only when the source
        # record explicitly carries them. Never guess from decision_kind.
        gate = record.get("gate")  # None unless explicitly present
        outcome = record.get("outcome")  # None unless explicitly present
        actor = record.get("actor")  # exact (string OR structured object)
        authority_ref = record.get("authority_ref")

        summary = record.get("payload_summary") or ""
        before = record.get("before")
        after = record.get("after")
        evidence_refs: List[str] = list(record.get("evidence_refs") or [])

        # Deterministic digest of the complete source record when absent.
        source_digest = record.get("source_digest") or compute_digest(record)

        return RunProjectionEvent(
            run_id=str(run_id),
            sequence=int(sequence),
            source_system=self.source_system,
            source_event_id=str(event_id),
            occurred_at=timestamp,
            gate=gate,
            node_id=record.get("node_id"),
            parent_event_id=record.get("parent_event_id"),
            event_type=str(decision_kind),
            outcome=outcome,
            actor=actor,
            summary=summary,
            before=before,
            after=after,
            evidence_refs=evidence_refs,
            authority_ref=authority_ref,
            source_digest=source_digest,
        )

    def from_audit_events(self, records: Iterable[Dict[str, Any]]) -> List[RunProjectionEvent]:
        return [self.from_audit_event(r) for r in records]

    def from_json(self, text: str) -> List[RunProjectionEvent]:
        """Parse a JSON list (or single object) of AuditEvent records."""
        data: Any = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        return self.from_audit_events(data)


# ---------------------------------------------------------------------------
# GWC adapter — binds to the canonical DurableEvent record. No .gwc yaml scan.
# ---------------------------------------------------------------------------
class GwcAdapter:
    """Reads canonical GWC DurableEvent records (read-only).

    Does NOT clone, fetch, push, or mutate the gwc repository, and does NOT
    infer approval state by scanning ``.gwc/tasks/*/g4/*.yaml``. It maps the
    canonical DurableEvent schema fields verbatim into the v1 projection
    envelope, preserving exact source identity, structured actor, gate, and
    outcome. It never fabricates occurred_at or actor.

    Optional ``gwc_root`` is retained only for defensive read-only file access;
    mapping itself takes the record directly and does not require any scan.
    """

    source_system = "gwc"

    def __init__(self, gwc_root: Optional[str | Path] = None) -> None:
        self.gwc_root = Path(gwc_root) if gwc_root else None

    def from_durable_event(self, record: Dict[str, Any]) -> RunProjectionEvent:
        # Canonical DurableEvent required fields (per schema).
        event_id = record.get("event_id")
        run_id = record.get("run_id")
        sequence = record.get("sequence")
        event_type = record.get("event_type")
        occurred_at = record.get("occurred_at_utc")
        actor = record.get("actor")
        gate = record.get("gate")
        node_id = record.get("node_id")
        outcome = record.get("outcome")

        if not event_id:
            raise ValueError("DurableEvent.event_id is required (cannot fabricate source identity)")
        if run_id is None:
            raise ValueError("DurableEvent.run_id is required")
        if sequence is None:
            raise ValueError("DurableEvent.sequence is required (real ledger sequence)")
        if not event_type:
            raise ValueError("DurableEvent.event_type is required")
        if occurred_at is None:
            raise ValueError("DurableEvent.occurred_at_utc is required (cannot fabricate timestamp)")
        if actor is None:
            raise ValueError("DurableEvent.actor is required (structured object; never fabricated)")
        if gate is None:
            raise ValueError("DurableEvent.gate is required (canonical G0..G6 label)")
        if node_id is None:
            raise ValueError("DurableEvent.node_id is required")
        if outcome is None:
            raise ValueError("DurableEvent.outcome is required")

        # Preserve exact values. structured actor preserved unmodified.
        payload = record.get("payload") or {}
        evidence_refs: List[str] = list(record.get("evidence_refs") or [])

        summary = record.get("summary") or _durable_summary(event_type, gate, outcome, node_id)

        source_digest = record.get("source_digest") or compute_digest(record)

        return RunProjectionEvent(
            run_id=str(run_id),
            sequence=int(sequence),
            source_system=self.source_system,
            source_event_id=str(event_id),
            occurred_at=occurred_at,
            gate=str(gate),
            node_id=str(node_id),
            parent_event_id=record.get("parent_event_id"),
            event_type=str(event_type),
            outcome=str(outcome),
            actor=actor,  # exact (structured object preserved)
            summary=summary,
            before=None,  # DurableEvent has no before/after fields
            after=payload if payload else None,
            evidence_refs=evidence_refs,
            authority_ref=record.get("authority_ref"),
            source_digest=source_digest,
        )

    def from_durable_events(self, records: Iterable[Dict[str, Any]]) -> List[RunProjectionEvent]:
        return [self.from_durable_event(r) for r in records]

    def from_json(self, text: str) -> List[RunProjectionEvent]:
        """Parse a JSON list (or single object) of DurableEvent records."""
        data: Any = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        return self.from_durable_events(data)


def _durable_summary(event_type: str, gate: Any, outcome: Any, node_id: Any) -> str:
    """Faithful one-line label derived only from source fields (not evidence)."""
    parts = [str(event_type)]
    if gate is not None:
        parts.append(f"gate={gate}")
    if outcome is not None:
        parts.append(f"outcome={outcome}")
    if node_id is not None:
        parts.append(f"node={node_id}")
    return " ".join(parts)
