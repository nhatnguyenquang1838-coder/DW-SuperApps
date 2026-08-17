from __future__ import annotations

from taskcontroller.interaction import A2AEnvelope, EnvelopeKind, project_envelope_for_human


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
