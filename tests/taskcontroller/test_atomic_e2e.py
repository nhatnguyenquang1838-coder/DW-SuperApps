"""TC-MBX-1001: deterministic atomic mailbox-first E2E contract."""

from __future__ import annotations

from dataclasses import dataclass, field
import json

import pytest

from taskcontroller.domain.values import InputRef
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import (
    A2AEnvelope,
    A2A_PROTOCOL,
    EnvelopeKind,
    MailboxCursor,
)
from taskcontroller.interaction.executor_entrypoint import (
    ExecutorValidationPolicy,
    MailboxFirstExecutorEntrypoint,
    MailboxReader,
)
from taskcontroller.interaction.github_mailbox import (
    parse_mailbox_comment,
    render_mailbox_comment,
)
from taskcontroller.interaction.human_projection import (
    HumanEventKind,
    project_envelope_for_human,
)
from taskcontroller.interaction.wakeup import WAKEUP_PROTOCOL, WakeupSignal
from taskcontroller.mvp.protocol_bridge import (
    TERMINAL,
    ContractedSubtask,
    ExecutorReport,
    classify_report,
)


_HEAD = "24bc30ad43c722a066e1f37cdcb01af735c327b1"
_RUN_ID = "run-tc-1001"
_NODE_ID = "node-atomic-1001"
_CONTROLLER = "controller"
_EXECUTOR = "hermes-cloud"
_CONTROLLER_MAILBOX = "github://mailbox/controller/run-tc-1001"
_EXECUTOR_MAILBOX = "github://mailbox/hermes/run-tc-1001"
_REQUEST_BODY = "Execute the bounded atomic task from the exact source references."


@dataclass
class _InMemoryMailbox(MailboxReader):
    bodies: dict[str, str] = field(default_factory=dict)
    reads: list[str] = field(default_factory=list)

    def read_mailbox(self, mailbox_ref: str) -> str:
        self.reads.append(mailbox_ref)
        return self.bodies[mailbox_ref]


def _executor_binding() -> dict[str, object]:
    return {
        "protocol": A2A_PROTOCOL,
        "capability_id": "capability.hermes.mailbox-v1",
        "instance_id": "hermes-cloud-instance-1001",
        "attempt_id": "attempt-1001-1",
        "lease_generation": 1,
        "fencing_token": "fence-1001-1",
        "lease_status": "ACTIVE",
        "status": "DISPATCHED",
    }


def _controller_command() -> A2AEnvelope:
    return A2AEnvelope(
        run_id=_RUN_ID,
        node_id=_NODE_ID,
        sender=_CONTROLLER,
        recipient=_EXECUTOR,
        seq=1,
        kind=EnvelopeKind.COMMAND.value,
        inputs=(InputRef("source", f"repo://DW-SuperApps@{_HEAD}/taskcontroller"),),
        artifact_refs=("artifact://tc-1001/acceptance",),
        request=_REQUEST_BODY,
        state={
            "status": "DISPATCHED",
            "head_sha": _HEAD,
            "executor_binding": _executor_binding(),
        },
        updated_at="2026-09-12T19:40:00+00:00",
    )


def _wakeup() -> WakeupSignal:
    return WakeupSignal(
        run_id=_RUN_ID,
        sender=_CONTROLLER,
        recipient=_EXECUTOR,
        mailbox_ref=_CONTROLLER_MAILBOX,
        seq=1,
        updated_at="2026-09-12T19:40:01+00:00",
    )


def _executor_policy() -> ExecutorValidationPolicy:
    return ExecutorValidationPolicy(
        capability_id="capability.hermes.mailbox-v1",
        instance_id="hermes-cloud-instance-1001",
        attempt_id="attempt-1001-1",
        lease_generation=1,
        fencing_token="fence-1001-1",
        last_seen_seq=0,
    )


def _terminal_result() -> A2AEnvelope:
    return A2AEnvelope(
        run_id=_RUN_ID,
        node_id=_NODE_ID,
        sender=_EXECUTOR,
        recipient=_CONTROLLER,
        seq=1,
        kind=EnvelopeKind.REPORT.value,
        inputs=(InputRef("source", f"repo://DW-SuperApps@{_HEAD}/taskcontroller"),),
        artifact_refs=("artifact://tc-1001/result",),
        state={
            "status": "DONE",
            "head_sha": _HEAD,
            "human_summary": "Atomic task completed with canonical evidence.",
        },
        updated_at="2026-09-12T19:41:00+00:00",
    )


def test_atomic_e2e_controller_mailbox_pointer_hermes_result_controller() -> None:
    """The complete atomic path uses mailbox state, not Slack/body replay."""
    command = _controller_command()
    controller_body = render_mailbox_comment(command)
    controller_round_trip = parse_mailbox_comment(controller_body)
    assert controller_round_trip == command

    pointer = _wakeup()
    pointer_payload = pointer.to_dict()
    assert set(pointer_payload) == {
        "protocol",
        "run_id",
        "sender",
        "recipient",
        "mailbox_ref",
        "seq",
        "updated_at",
    }
    pointer_text = json.dumps(pointer_payload, sort_keys=True)
    assert pointer_payload["protocol"] == WAKEUP_PROTOCOL
    assert _REQUEST_BODY not in pointer_text
    assert "inputs" not in pointer_payload
    assert "artifact_refs" not in pointer_payload
    assert "state" not in pointer_payload
    assert "request" not in pointer_payload

    mailboxes = _InMemoryMailbox({_CONTROLLER_MAILBOX: controller_body})
    entrypoint = MailboxFirstExecutorEntrypoint(
        mailboxes,
        executor_actor=_EXECUTOR,
        validation_policy=_executor_policy(),
    )
    request = entrypoint.bootstrap(
        pointer,
        projection={"request": "tampered Slack command must be ignored"},
    )
    assert request.envelope == command
    assert request.envelope.request == _REQUEST_BODY
    assert mailboxes.reads == [_CONTROLLER_MAILBOX]

    result = _terminal_result()
    mailboxes.bodies[_EXECUTOR_MAILBOX] = render_mailbox_comment(result)
    result_round_trip = parse_mailbox_comment(mailboxes.read_mailbox(_EXECUTOR_MAILBOX))
    assert result_round_trip == result

    controller_cursor = MailboxCursor(
        actor=_EXECUTOR,
        mailbox_ref=_EXECUTOR_MAILBOX,
        last_seen_seq=0,
    )
    accepted_cursor = controller_cursor.observe(result_round_trip)
    assert accepted_cursor.last_seen_seq == 1
    assert accepted_cursor.mailbox_ref == _EXECUTOR_MAILBOX

    contract = ContractedSubtask(
        subtask_id=_NODE_ID,
        objective="Complete the bounded atomic task.",
        allowed_work=("read_bound_sources", "write_evidence"),
        expected_output=("terminal_result",),
        report_requirement=("exact_result_ref",),
        after_report=TERMINAL,
    )
    report = ExecutorReport(
        subtask_id=_NODE_ID,
        status="DONE",
        completed=("canonical result written",),
        evidence=("artifact://tc-1001/result",),
        next_action="NONE",
        after=TERMINAL,
    )
    verdict = classify_report(contract, report)
    assert verdict.verdict == TERMINAL
    assert verdict.runtime_mutated is False

    human_event = project_envelope_for_human(result_round_trip)
    assert human_event is not None
    assert human_event.kind == HumanEventKind.MILESTONE_REACHED.value
    assert human_event.detail == "Atomic task completed with canonical evidence."
    assert _REQUEST_BODY not in json.dumps(human_event.__dict__, sort_keys=True)


def test_atomic_e2e_rejects_command_bearing_wakeup() -> None:
    payload = _wakeup().to_dict()
    payload["request"] = _REQUEST_BODY

    with pytest.raises(TaskControllerValidationError, match="non-pointer"):
        WakeupSignal.from_dict(payload)


def test_atomic_e2e_rejects_pointer_body_in_human_projection() -> None:
    result = _terminal_result()
    event = project_envelope_for_human(result)

    assert event is not None
    assert event.kind == HumanEventKind.MILESTONE_REACHED.value
    assert _REQUEST_BODY not in event.detail
    assert "request" not in event.__dict__


def test_atomic_e2e_mailbox_round_trip_preserves_exact_result_bytes() -> None:
    result = _terminal_result()
    body = render_mailbox_comment(result)
    parsed = parse_mailbox_comment(body)

    assert render_mailbox_comment(parsed) == body
    assert parsed.to_dict() == result.to_dict()
