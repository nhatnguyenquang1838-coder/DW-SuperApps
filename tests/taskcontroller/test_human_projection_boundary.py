from __future__ import annotations

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction import (
    A2AEnvelope,
    EnvelopeKind,
    HumanEventKind,
    project_envelope_for_human,
)


def _command(*, state: dict | None = None) -> A2AEnvelope:
    return A2AEnvelope(
        run_id="run.boundary",
        node_id="node.secret",
        sender="controller",
        recipient="hermes-cloud",
        seq=1,
        kind=EnvelopeKind.COMMAND.value,
        request="PRIVATE_MACHINE_COMMAND_PAYLOAD do many low-level steps",
        state=state or {"status": "RUNNING"},
        updated_at="2026-08-16T17:10:00+00:00",
    )


def test_human_projection_never_copies_raw_machine_request() -> None:
    event = project_envelope_for_human(_command())

    assert event is not None
    assert "PRIVATE_MACHINE_COMMAND_PAYLOAD" not in event.detail
    assert "low-level steps" not in event.detail


def test_human_projection_uses_explicit_human_summary_when_present() -> None:
    event = project_envelope_for_human(
        _command(state={"status": "RUNNING", "human_summary": "Executor started bounded S1."})
    )

    assert event is not None
    assert event.detail == "Executor started bounded S1."
    assert "PRIVATE_MACHINE_COMMAND_PAYLOAD" not in event.detail


def test_typed_authority_required_state_projects_actionable_human_event_without_machine_request():
    envelope = A2AEnvelope(
        run_id="run.boundary",
        node_id="gate.human-approval",
        sender="executor",
        recipient="controller",
        seq=2,
        kind=EnvelopeKind.REPORT.value,
        request="PRIVATE_MACHINE_COMMAND_PAYLOAD do not expose",
        state={
            "status": "WAIT_CONTROLLER",
            "authority_required": True,
            "human_summary": "G4 approval is required for this exact scope.",
        },
        updated_at="2026-08-16T17:10:01+00:00",
    )

    event = project_envelope_for_human(envelope)

    assert event is not None
    assert event.kind == HumanEventKind.AUTHORITY_REQUIRED.value
    assert event.title == "External authority required"
    assert event.detail.startswith("G4 approval is required for this exact scope.")
    assert "Runtime unchanged; not approved or merged." in event.detail
    assert "PRIVATE_MACHINE_COMMAND_PAYLOAD" not in event.detail


def test_wait_controller_without_typed_authority_signal_is_not_authority_request():
    envelope = A2AEnvelope(
        run_id="run.boundary",
        node_id="executor.wait",
        sender="executor",
        recipient="controller",
        seq=3,
        kind=EnvelopeKind.REPORT.value,
        request="PRIVATE_MACHINE_COMMAND_PAYLOAD do not expose",
        state={"status": "WAIT_CONTROLLER", "human_summary": "Review the report."},
        updated_at="2026-08-16T17:10:02+00:00",
    )

    event = project_envelope_for_human(envelope)

    assert event is not None
    assert event.kind != HumanEventKind.AUTHORITY_REQUIRED.value
    assert "PRIVATE_MACHINE_COMMAND_PAYLOAD" not in event.detail


def test_authority_required_must_be_typed_boolean():
    with pytest.raises(
        TaskControllerValidationError,
        match="a2a_envelope.state.authority_required must be a bool",
    ):
        project_envelope_for_human(
            _command(state={"status": "RUNNING", "authority_required": "true"})
        )
