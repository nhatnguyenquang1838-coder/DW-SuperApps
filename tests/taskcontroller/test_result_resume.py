"""TC-MBX-703: Controller v2 terminal-result poll/resume boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.execution.terminal_result import build_terminal_parent_result
from taskcontroller.interaction.mailbox_repository import (
    InMemoryMailboxRepository,
    MailboxActorCursor,
)
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.controlplane.result_resume import (
    POLL_NO_NEW_RESULT,
    POLL_RESULT_AVAILABLE,
    ControllerResultResumeError,
    poll_controller_terminal_result,
)


_FIXTURE = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
_MAILBOX = "github://owner/repo/issues/703#controller"
_STANDARDS_DIGEST = "sha256:" + "6" * 64
_SOURCE_DIGEST = "sha256:" + "4" * 64


def _request(
    *,
    correlation_id: str = "correlation-1",
    message_id: str = "request-703",
    idempotency_key: str = "request-idem-703",
    run_id: str = "run-1",
    attempt_id: str = "attempt-1",
    fencing_token: str = "fence-1",
) -> V2MailboxEnvelope:
    payload = copy.deepcopy(
        json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]["execution_request"]
    )
    payload["message_id"] = message_id
    payload["idempotency_key"] = idempotency_key
    payload["correlation_id"] = correlation_id
    payload["run_id"] = run_id
    payload["attempt"]["attempt_id"] = attempt_id
    payload["attempt"]["fencing_token"] = fencing_token
    payload["execution_identity"]["run_id"] = run_id
    payload["execution_identity"]["attempt_id"] = attempt_id
    payload["execution_identity"]["fencing_token"] = fencing_token
    payload["payload"]["result_resume_test_message"] = message_id
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def _normalized() -> dict[str, Any]:
    return {
        "protocol": "dw.taskcontroller.parent-synthesis/v1",
        "proposed_verdict": "PASS",
        "final_verdict": "PASS",
        "verdict": "PASS",
        "status": "PASS",
        "findings": [],
        "child_refs": [
            {
                "child_id": "child-703",
                "status": "SUCCEEDED",
                "result_digest": "sha256:" + "a" * 64,
                "normalization_digest": "sha256:" + "a" * 64,
                "raw_output_digest": "sha256:" + "b" * 64,
                "child_contract_digest": "sha256:" + "c" * 64,
                "source_digest": _SOURCE_DIGEST,
                "lens": "implementation",
                "reviewer": "reviewer-703",
            }
        ],
        "child_result_digests": ["sha256:" + "a" * 64],
        "residual_risks": [],
        "unresolved_questions": [],
        "conflicts": [],
        "controller_decision": {
            "decision_id": "decision-703",
            "run_ref": "run-1",
            "decision_type": "COMPLETE",
            "rationale": "The result is bound to the current execution evidence.",
            "evidence_refs": ["artifact://evidence-703"],
        },
    }


def _terminal(
    request: V2MailboxEnvelope,
    *,
    message_id: str,
    idempotency_key: str,
    seq: int,
):
    return build_terminal_parent_result(
        request,
        _normalized(),
        message_id=message_id,
        seq=seq,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key=idempotency_key,
    )


def _cursor() -> MailboxActorCursor:
    return MailboxActorCursor.initial(
        _MAILBOX,
        run_id="run-1",
        node_id="node-1",
        actor_namespace="hermes-executor",
    )


def _poll(repository: InMemoryMailboxRepository, cursor: MailboxActorCursor, terminal):
    return poll_controller_terminal_result(
        repository,
        cursor,
        correlation_id=terminal.envelope.to_dict()["correlation_id"],
        expected_identity=terminal.envelope.execution_identity,
        expected_source_digest=_SOURCE_DIGEST,
        expected_standards_digest=_STANDARDS_DIGEST,
    )


def test_poll_resumes_new_matching_terminal_and_persists_cursor() -> None:
    repository = InMemoryMailboxRepository()
    terminal = _terminal(
        _request(),
        message_id="terminal-703-current",
        idempotency_key="terminal-idem-703-current",
        seq=1,
    )
    repository.write(_MAILBOX, -1, terminal.envelope)

    outcome = _poll(repository, _cursor(), terminal)

    assert outcome.status == POLL_RESULT_AVAILABLE
    assert outcome.terminal_result == terminal
    assert outcome.cursor.last_event_seq == 0
    assert outcome.cursor.last_logical_seq == 1
    assert outcome.observed_event_ids == (f"{_MAILBOX}:event-0",)
    assert repository.read_cursor("github://owner/repo/issues/703#controller", "run-1", "node-1", "hermes-executor") == outcome.cursor

    replay = _poll(repository, outcome.cursor, terminal)
    assert replay.status == POLL_NO_NEW_RESULT
    assert replay.terminal_result is None
    assert replay.cursor == outcome.cursor


def test_old_terminal_result_is_not_replayed_after_cursor_ack() -> None:
    repository = InMemoryMailboxRepository()
    terminal = _terminal(
        _request(),
        message_id="terminal-703-old",
        idempotency_key="terminal-idem-703-old",
        seq=1,
    )
    repository.write(_MAILBOX, -1, terminal.envelope)
    cursor = _cursor()
    event = repository.read(_MAILBOX).events[0]
    acknowledged = repository.acknowledge_cursor(cursor.observe(event))

    outcome = _poll(repository, acknowledged, terminal)

    assert outcome.status == POLL_NO_NEW_RESULT
    assert outcome.terminal_result is None
    assert outcome.cursor == acknowledged
    assert outcome.observed_event_ids == ()


def test_foreign_correlation_and_attempt_are_ignored_but_observed() -> None:
    repository = InMemoryMailboxRepository()
    current = _terminal(
        _request(),
        message_id="terminal-703-current-after-foreign",
        idempotency_key="terminal-idem-703-current-after-foreign",
        seq=2,
    )
    foreign_correlation = _terminal(
        _request(
            correlation_id="correlation-foreign",
            message_id="request-703-foreign-correlation",
            idempotency_key="request-idem-703-foreign-correlation",
        ),
        message_id="terminal-703-foreign-correlation",
        idempotency_key="terminal-idem-703-foreign-correlation",
        seq=1,
    )
    repository.write(_MAILBOX, -1, foreign_correlation.envelope)
    repository.write(_MAILBOX, 0, current.envelope)

    outcome = _poll(repository, _cursor(), current)

    assert outcome.status == POLL_RESULT_AVAILABLE
    assert outcome.terminal_result == current
    assert outcome.cursor.last_event_seq == 1
    assert len(outcome.ignored_event_ids) == 1
    assert outcome.ignored_event_ids[0].endswith("event-0")
    assert outcome.ignored_reasons == ("CORRELATION_MISMATCH",)

    repository = InMemoryMailboxRepository()
    foreign_attempt = _terminal(
        _request(
            message_id="request-703-foreign-attempt",
            idempotency_key="request-idem-703-foreign-attempt",
            attempt_id="attempt-foreign",
            fencing_token="fence-foreign",
        ),
        message_id="terminal-703-foreign-attempt",
        idempotency_key="terminal-idem-703-foreign-attempt",
        seq=1,
    )
    repository.write(_MAILBOX, -1, foreign_attempt.envelope)
    outcome = _poll(repository, _cursor(), current)

    assert outcome.status == POLL_NO_NEW_RESULT
    assert outcome.terminal_result is None
    assert outcome.cursor.last_event_seq == 0
    assert outcome.ignored_reasons == ("EXECUTION_IDENTITY_MISMATCH",)


def test_tampered_result_digest_is_evidence_only_and_never_resumed() -> None:
    repository = InMemoryMailboxRepository()
    terminal = _terminal(
        _request(),
        message_id="terminal-703-tampered",
        idempotency_key="terminal-idem-703-tampered",
        seq=1,
    )
    payload = terminal.envelope.to_dict()
    payload["result"]["result_digest"] = "sha256:" + "e" * 64
    payload["digest"] = canonical_digest(payload)
    tampered = V2MailboxEnvelope.from_dict(payload)
    repository.write(_MAILBOX, -1, tampered)

    outcome = _poll(repository, _cursor(), terminal)

    assert outcome.status == POLL_NO_NEW_RESULT
    assert outcome.terminal_result is None
    assert outcome.cursor.last_event_seq == 0
    assert outcome.ignored_reasons == ("INVALID_TERMINAL_RESULT",)


def test_poll_rejects_cursor_bound_to_a_different_execution() -> None:
    repository = InMemoryMailboxRepository()
    terminal = _terminal(
        _request(),
        message_id="terminal-703-binding",
        idempotency_key="terminal-idem-703-binding",
        seq=1,
    )

    wrong_cursor = MailboxActorCursor.initial(
        _MAILBOX,
        run_id="other-run",
        node_id="node-1",
        actor_namespace="hermes-executor",
    )
    with pytest.raises(ControllerResultResumeError) as error:
        _poll(repository, wrong_cursor, terminal)
    assert error.value.code == "RESUME_CURSOR_MISMATCH"
