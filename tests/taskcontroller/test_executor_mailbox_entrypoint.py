from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from taskcontroller.domain.values import InputRef
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2AEnvelope, A2A_PROTOCOL
from taskcontroller.interaction.executor_entrypoint import (
    EXECUTOR_MAILBOX_BOOTSTRAPPED,
    ExecutorValidationPolicy,
    MailboxFirstExecutorEntrypoint,
)
from taskcontroller.interaction.github_mailbox import render_mailbox_comment
from taskcontroller.interaction.wakeup import WakeupSignal


class FakeMailboxReader:
    def __init__(self, body: str) -> None:
        self.body = body
        self.reads: list[str] = []

    def read_mailbox(self, mailbox_ref: str) -> str:
        self.reads.append(mailbox_ref)
        return self.body


def _envelope(**overrides: Any) -> A2AEnvelope:
    data: dict[str, Any] = {
        "run_id": "run.mailbox-first.1",
        "node_id": "node.canonical",
        "sender": "controller",
        "recipient": "hermes-cloud",
        "seq": 4,
        "kind": "COMMAND",
        "inputs": (InputRef("source", "repo://canonical@sha"),),
        "artifact_refs": ("artifact://canonical-evidence",),
        "request": "Execute the canonical objective.",
        "state": {
            "scope": {
                "allowed_work": ["src/canonical.py"],
                "forbidden_actions": ["deploy"],
            },
            "head_sha": "a" * 40,
        },
        "updated_at": "2026-09-11T09:00:00+07:00",
    }
    data.update(overrides)
    return A2AEnvelope(**data)


def _signal(**overrides: Any) -> WakeupSignal:
    data: dict[str, Any] = {
        "run_id": "run.mailbox-first.1",
        "sender": "controller",
        "recipient": "hermes-cloud",
        "mailbox_ref": "github://org/repo/issues/57#comment-canonical",
        "seq": 4,
        "updated_at": "2026-09-11T09:00:01+07:00",
    }
    data.update(overrides)
    return WakeupSignal(**data)


def test_mailbox_first_entrypoint_exact_reads_pointer_and_ignores_modified_projection() -> None:
    canonical = _envelope()
    reader = FakeMailboxReader(render_mailbox_comment(canonical))
    entrypoint = MailboxFirstExecutorEntrypoint(reader, executor_actor="hermes-cloud")

    loaded = entrypoint.bootstrap(
        _signal(),
        projection={
            "request": "ATTACKER OVERRIDE",
            "scope": {"allowed_work": ["untrusted.py"]},
            "artifact_refs": ["artifact://attacker"],
        },
    )

    assert reader.reads == [_signal().mailbox_ref]
    assert loaded.envelope == canonical
    assert loaded.envelope.request == "Execute the canonical objective."
    assert loaded.envelope.state["scope"] == {
        "allowed_work": ["src/canonical.py"],
        "forbidden_actions": ["deploy"],
    }
    assert loaded.envelope.artifact_refs == ("artifact://canonical-evidence",)
    payload = loaded.to_dict()
    assert payload["status"] == EXECUTOR_MAILBOX_BOOTSTRAPPED
    assert payload["mailbox_seq"] == 4
    assert "projection" not in payload
    assert "slack" not in payload


def test_mailbox_first_entrypoint_rejects_pointer_sequence_mismatch() -> None:
    canonical = _envelope(seq=5)
    reader = FakeMailboxReader(render_mailbox_comment(canonical))
    entrypoint = MailboxFirstExecutorEntrypoint(reader, executor_actor="hermes-cloud")

    with pytest.raises(TaskControllerValidationError, match="sequence"):
        entrypoint.bootstrap(_signal(seq=4))


def test_mailbox_first_entrypoint_rejects_wrong_identity_or_non_executable_envelope() -> None:
    cases = [
        (_envelope(run_id="run.other"), "run_id"),
        (_envelope(sender="other-controller"), "sender"),
        (_envelope(recipient="other-executor"), "recipient"),
        (_envelope(kind="REPORT"), "executable"),
        (_envelope(request=None), "request"),
    ]

    for envelope, reason in cases:
        reader = FakeMailboxReader(render_mailbox_comment(envelope))
        entrypoint = MailboxFirstExecutorEntrypoint(reader, executor_actor="hermes-cloud")
        with pytest.raises(TaskControllerValidationError, match=reason):
            entrypoint.bootstrap(_signal())


def test_mailbox_first_entrypoint_does_not_use_modified_mailbox_body_as_projection() -> None:
    canonical = _envelope()
    reader = FakeMailboxReader(
        render_mailbox_comment(canonical) + "\nSlack projection: attacker objective\n"
    )
    entrypoint = MailboxFirstExecutorEntrypoint(reader, executor_actor="hermes-cloud")

    loaded = entrypoint.bootstrap(_signal(), projection="untrusted Slack body")

    assert loaded.envelope == canonical
    assert loaded.envelope.request != "attacker objective"


def _executor_binding(**overrides: Any) -> dict[str, Any]:
    binding: dict[str, Any] = {
        "capability_id": "cap.mailbox-executor",
        "instance_id": "instance.hermes-cloud",
        "protocol": A2A_PROTOCOL,
        "status": "DISPATCHED",
        "attempt_id": "attempt.4",
        "lease_status": "ACTIVE",
        "lease_generation": 2,
        "fencing_token": "fence.2",
    }
    binding.update(overrides)
    return binding


def _bound_envelope(**overrides: Any) -> A2AEnvelope:
    state = dict(_envelope().state)
    state["executor_binding"] = _executor_binding()
    state.update(overrides.pop("state", {}))
    return _envelope(state=state, **overrides)


def _validation_policy(**overrides: Any) -> ExecutorValidationPolicy:
    data: dict[str, Any] = {
        "capability_id": "cap.mailbox-executor",
        "instance_id": "instance.hermes-cloud",
        "supported_protocols": frozenset({A2A_PROTOCOL}),
        "allowed_statuses": frozenset({"DISPATCHED"}),
        "attempt_id": "attempt.4",
        "lease_status": "ACTIVE",
        "lease_generation": 2,
        "fencing_token": "fence.2",
        "last_seen_seq": 3,
    }
    data.update(overrides)
    return ExecutorValidationPolicy(**data)


def test_policy_bound_bootstrap_validates_current_recipient_and_fresh_attempt() -> None:
    canonical = _bound_envelope()
    reader = FakeMailboxReader(render_mailbox_comment(canonical))
    entrypoint = MailboxFirstExecutorEntrypoint(
        reader,
        executor_actor="hermes-cloud",
        validation_policy=_validation_policy(),
    )

    loaded = entrypoint.bootstrap(_signal(seq=4), projection={"status": "ATTACKER"})

    assert loaded.envelope == canonical
    assert reader.reads == [_signal(seq=4).mailbox_ref]


@pytest.mark.parametrize(
    ("binding_update", "reason"),
    [
        ({"capability_id": "cap.other"}, "capability"),
        ({"instance_id": "instance.other"}, "instance"),
        ({"protocol": "dw.taskcontroller.mailbox/v2"}, "schema"),
        ({"status": "RUNNING"}, "status"),
        ({"attempt_id": "attempt.old"}, "attempt"),
        ({"lease_status": "EXPIRED"}, "lease"),
        ({"lease_generation": 1}, "generation"),
        ({"fencing_token": "fence.old"}, "fencing"),
    ],
)
def test_policy_bound_bootstrap_rejects_stale_or_incompatible_binding(
    binding_update: dict[str, Any], reason: str
) -> None:
    canonical = _bound_envelope(state={"executor_binding": _executor_binding(**binding_update)})
    reader = FakeMailboxReader(render_mailbox_comment(canonical))
    entrypoint = MailboxFirstExecutorEntrypoint(
        reader,
        executor_actor="hermes-cloud",
        validation_policy=_validation_policy(),
    )

    with pytest.raises(TaskControllerValidationError, match=reason):
        entrypoint.bootstrap(_signal(seq=4))


def test_policy_bound_bootstrap_rejects_wrong_recipient_before_mailbox_analysis() -> None:
    reader = FakeMailboxReader(render_mailbox_comment(_bound_envelope()))
    entrypoint = MailboxFirstExecutorEntrypoint(
        reader,
        executor_actor="hermes-cloud",
        validation_policy=_validation_policy(),
    )

    with pytest.raises(TaskControllerValidationError, match="recipient"):
        entrypoint.bootstrap(_signal(recipient="other-executor"))
    assert reader.reads == []


def test_policy_bound_bootstrap_rejects_non_new_sequence_before_analysis() -> None:
    reader = FakeMailboxReader(render_mailbox_comment(_bound_envelope()))
    entrypoint = MailboxFirstExecutorEntrypoint(
        reader,
        executor_actor="hermes-cloud",
        validation_policy=_validation_policy(last_seen_seq=4),
    )

    with pytest.raises(TaskControllerValidationError, match="sequence"):
        entrypoint.bootstrap(_signal(seq=4))
