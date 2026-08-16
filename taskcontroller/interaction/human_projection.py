"""Pure projection from machine A2A envelopes to bounded human events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2AEnvelope, EnvelopeKind


class HumanEventKind(str, Enum):
    RUN_STARTED = "RUN_STARTED"
    SUBTASK_STARTED = "SUBTASK_STARTED"
    MILESTONE_REACHED = "MILESTONE_REACHED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    BLOCKED = "BLOCKED"
    AUTHORITY_REQUIRED = "AUTHORITY_REQUIRED"
    CONTROLLER_RECOVERED = "CONTROLLER_RECOVERED"
    TERMINAL = "TERMINAL"


@dataclass(frozen=True)
class HumanEvent:
    kind: str
    title: str
    status: str
    detail: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            HumanEventKind(self.kind)
        except (TypeError, ValueError) as exc:
            raise TaskControllerValidationError(
                f"human_event.kind unsupported: {self.kind!r}"
            ) from exc
        for name in ("title", "status", "detail"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise TaskControllerValidationError(
                    f"human_event.{name} must be non-empty"
                )
        if any(not isinstance(ref, str) or not ref for ref in self.evidence_refs):
            raise TaskControllerValidationError(
                "human_event.evidence_refs must contain non-empty strings"
            )


def _human_detail(envelope: A2AEnvelope, fallback: str) -> str:
    """Return an explicit human-safe summary, never the machine request body."""

    value = envelope.state.get("human_summary")
    if value is None:
        return fallback
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(
            "a2a_envelope.state.human_summary must be non-empty when supplied"
        )
    return value.strip()


def _status(envelope: A2AEnvelope, fallback: str) -> str:
    value = envelope.state.get("status")
    return value if isinstance(value, str) and value else fallback


def project_envelope_for_human(envelope: A2AEnvelope) -> HumanEvent | None:
    if not isinstance(envelope, A2AEnvelope):
        raise TaskControllerValidationError("human projection requires A2AEnvelope")

    kind = EnvelopeKind(envelope.kind)
    if kind is EnvelopeKind.HEALTH:
        return None

    status = _status(envelope, kind.value)
    evidence = tuple(envelope.artifact_refs)

    if status.upper() == "BLOCKED":
        return HumanEvent(
            kind=HumanEventKind.BLOCKED.value,
            title=f"{envelope.sender} blocked",
            status=status,
            detail=_human_detail(envelope, "Executor requires intervention."),
            evidence_refs=evidence,
        )

    if kind is EnvelopeKind.COMMAND:
        return HumanEvent(
            kind=HumanEventKind.SUBTASK_STARTED.value,
            title=f"Started {envelope.node_id}",
            status=status,
            detail=_human_detail(envelope, "A bounded subtask started."),
            evidence_refs=evidence,
        )
    if kind is EnvelopeKind.REPORT:
        return HumanEvent(
            kind=HumanEventKind.MILESTONE_REACHED.value,
            title=f"{envelope.sender} reached a milestone",
            status=status,
            detail=_human_detail(envelope, "A contracted milestone was reported."),
            evidence_refs=evidence,
        )
    if kind is EnvelopeKind.REVIEW_REQUEST:
        return HumanEvent(
            kind=HumanEventKind.REVIEW_REQUIRED.value,
            title="Controller review required",
            status=status,
            detail=_human_detail(envelope, "Executor reached a review boundary."),
            evidence_refs=evidence,
        )
    if kind is EnvelopeKind.CORRECTION:
        return HumanEvent(
            kind=HumanEventKind.CORRECTION_REQUIRED.value,
            title="Correction required",
            status=status,
            detail=_human_detail(envelope, "Controller issued a bounded correction."),
            evidence_refs=evidence,
        )
    if kind is EnvelopeKind.TERMINAL:
        return HumanEvent(
            kind=HumanEventKind.TERMINAL.value,
            title=f"{envelope.sender} terminal update",
            status=status,
            detail=_human_detail(envelope, "The delegated segment reached a terminal boundary."),
            evidence_refs=evidence,
        )

    raise TaskControllerValidationError(f"unhandled envelope kind: {kind.value}")
