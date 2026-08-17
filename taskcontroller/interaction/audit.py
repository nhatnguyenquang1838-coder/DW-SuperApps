"""Audit bridge for reference-based TaskController Agent interaction.

The bridge records semantic envelope metadata and durable references only. It
never persists chain-of-thought or requires a transport SDK.
"""

from __future__ import annotations

from typing import Protocol

from taskcontroller.audit.event import AuditEvent
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2A_PROTOCOL, A2AEnvelope


class AuditRecorder(Protocol):
    def record(self, run_id: str, event: AuditEvent) -> int: ...


def _stable_evidence_refs(envelope: A2AEnvelope) -> tuple[str, ...]:
    refs: list[str] = []
    for ref in [*(item.source_ref for item in envelope.inputs), *envelope.artifact_refs]:
        if ref not in refs:
            refs.append(ref)
    return tuple(refs)


def _summary(envelope: A2AEnvelope) -> str:
    value = (envelope.request or "").strip()
    if not value:
        value = f"{envelope.sender} {envelope.kind} seq={envelope.seq}"
    if len(value) > 300:
        value = value[:297] + "..."
    return value


def audit_event_from_envelope(
    envelope: A2AEnvelope,
    *,
    event_id: str,
    raw_payload_ref: str = "",
    authority_ref: str = "",
) -> AuditEvent:
    """Translate one semantic A2A envelope into deterministic audit evidence."""

    if not isinstance(envelope, A2AEnvelope):
        raise TaskControllerValidationError("audit bridge requires A2AEnvelope")
    if not isinstance(event_id, str) or not event_id:
        raise TaskControllerValidationError("audit event_id must be non-empty")
    if not isinstance(raw_payload_ref, str):
        raise TaskControllerValidationError("audit raw_payload_ref must be a string")
    if not isinstance(authority_ref, str):
        raise TaskControllerValidationError("audit authority_ref must be a string")

    status = envelope.state.get("status")
    after = {
        "recipient": envelope.recipient,
        "kind": envelope.kind,
    }
    if isinstance(status, str) and status:
        after["status"] = status

    return AuditEvent(
        event_id=event_id,
        timestamp=envelope.updated_at,
        run_id=envelope.run_id,
        source="taskcontroller.interaction",
        decision_kind=f"A2A_{envelope.kind}",
        node_id=envelope.node_id,
        actor=envelope.sender,
        authority_ref=authority_ref,
        payload_summary=_summary(envelope),
        raw_payload_ref=raw_payload_ref,
        sequence=envelope.seq,
        after=after,
        evidence_refs=_stable_evidence_refs(envelope),
        annotations={"protocol": A2A_PROTOCOL},
        version=1,
    )


def record_envelope_event(
    audit: AuditRecorder,
    envelope: A2AEnvelope,
    *,
    event_id: str,
    raw_payload_ref: str = "",
    authority_ref: str = "",
) -> int:
    """Record one envelope through the configured TaskController audit facade."""

    if audit is None or not callable(getattr(audit, "record", None)):
        raise TaskControllerValidationError("audit recorder must provide record(run_id, event)")
    event = audit_event_from_envelope(
        envelope,
        event_id=event_id,
        raw_payload_ref=raw_payload_ref,
        authority_ref=authority_ref,
    )
    return audit.record(envelope.run_id, event)
