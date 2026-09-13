"""TC-MBX-803: retry creates a fresh attempt for one logical contract."""

from __future__ import annotations

from typing import Any

import pytest

from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)
from taskcontroller.controlplane.retry import retry_bounded_mailbox_request
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ErrorCode,
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    canonical_digest,
)
from taskcontroller.interaction.state_advancement import (
    StateAdvancingDisposition,
    validate_state_advancing_write,
)


_SOURCE = {
    "repository": "owner/repo",
    "commit_sha": "a" * 40,
    "path": "taskcontroller/controlplane/request_compiler.py",
    "blob_digest": "sha256:" + "1" * 64,
}


def _request(**changes: Any) -> BoundedMailboxRequest:
    values: dict[str, Any] = {
        "message_id": "message-803-1",
        "run_id": "run-803",
        "node_id": "node-803",
        "seq": 10,
        "correlation_id": "correlation-803",
        "contract_id": "contract-803",
        "plan_version": "plan-803",
        "contract_digest": "sha256:" + "2" * 64,
        "boundary_digest": "sha256:" + "3" * 64,
        "source_digest": "sha256:" + "4" * 64,
        "source_manifest_ref": "source-manifest-803",
        "objective": "Retry one bounded TaskContract without widening authority.",
        "scope": {
            "allowed_actions": ["read_repo", "run_tests"],
            "denied_actions": ["merge", "deploy"],
            "writable_targets": ["taskcontroller", "tests/taskcontroller"],
            "source_roots": ["taskcontroller", "tests/taskcontroller"],
            "max_children": 0,
            "max_parallel": 1,
            "max_depth": 0,
        },
        "acceptance_criteria": (
            "The logical contract is reused exactly.",
            "A previous late result is evidence-only.",
        ),
        "source_refs": (_SOURCE,),
        "standards_profile": {
            "profile_id": "standards.default",
            "version": "1",
            "digest": "sha256:" + "5" * 64,
        },
        "standards_profile_ref": "standards.default/v1",
        "recipient_capability": "taskcontroller.executor",
        "agent_instance": "hermes-mac",
        "attempt_id": "attempt-803-1",
        "attempt_number": 1,
        "lease_generation": 4,
        "fencing_token": "fence-803-1",
        "lease_expires_at": "2026-09-12T14:00:00+07:00",
        "idempotency_key": "idem-803-1",
        "producer_namespace": "controller",
        "producer_actor_id": "controller-803",
        "execution_id": "execution-803",
        "evidence_refs": ("evidence://contract/803",),
        "environment_requirements": {"runtime": "python3.11"},
        "authority_constraints": {
            "denied_actions": ["merge", "deploy"],
            "writable_targets": ["taskcontroller", "tests/taskcontroller"],
        },
        "payload": {"bounded": True},
    }
    values.update(changes)
    return BoundedMailboxRequest(**values)


def _retry(previous: BoundedMailboxRequest) -> BoundedMailboxRequest:
    return retry_bounded_mailbox_request(
        previous,
        message_id="message-803-2",
        seq=11,
        attempt_id="attempt-803-2",
        lease_generation=5,
        fencing_token="fence-803-2",
        lease_expires_at="2026-09-12T14:15:00+07:00",
        idempotency_key="idem-803-2",
    )


def _current_identity(envelope: V2MailboxEnvelope) -> dict[str, Any]:
    identity = envelope.execution_identity
    return {
        "run_id": identity["run_id"],
        "node_id": identity["node_id"],
        "plan_version": identity["plan_version"],
        "attempt_id": identity["attempt_id"],
        "lease_generation": identity["lease_generation"],
        "contract_digest": identity["contract_digest"],
        "source_digest": identity["source_digest"],
    }


def _terminal_result(request: BoundedMailboxRequest, *, message_id: str, seq: int) -> V2MailboxEnvelope:
    envelope = compile_bounded_mailbox_request(request)
    payload = envelope.to_dict()
    result_digest = "sha256:" + "6" * 64
    payload.update(
        {
            "message_id": message_id,
            "seq": seq,
            "direction": "executor_to_controller",
            "message_type": "terminal_result",
            "producer": {
                "namespace": "executor",
                "actor_id": "hermes-mac",
                "role": "executor",
            },
            "result": {
                "status": "SUCCEEDED",
                "boundary_digest": request.boundary_digest,
                "result_digest": result_digest,
                "artifact_refs": ["artifact://tc-mbx-803/result"],
                "findings": [],
            },
        }
    )
    payload["provenance"].update(
        {
            "origin": "executor",
            "status": "SUCCEEDED",
            "result_digest": result_digest,
        }
    )
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def test_retry_reuses_logical_contract_and_creates_fresh_identity_scope() -> None:
    previous = _request()
    retried = _retry(previous)
    previous_envelope = compile_bounded_mailbox_request(previous)
    retried_envelope = compile_bounded_mailbox_request(retried)

    assert retried.contract_id == previous.contract_id
    assert retried.contract_digest == previous.contract_digest
    assert retried.boundary_digest == previous.boundary_digest
    assert retried.source_digest == previous.source_digest
    assert retried.objective == previous.objective
    assert retried.scope == previous.scope
    assert retried.acceptance_criteria == previous.acceptance_criteria
    assert retried.authority_constraints == previous.authority_constraints
    assert retried.payload == previous.payload

    assert retried.attempt_id != previous.attempt_id
    assert retried.attempt_number == previous.attempt_number + 1
    assert retried.lease_generation > previous.lease_generation
    assert retried.fencing_token != previous.fencing_token
    assert retried.idempotency_key != previous.idempotency_key
    assert retried.message_id != previous.message_id
    assert retried.seq > previous.seq

    assert retried_envelope.logical_contract == previous_envelope.logical_contract
    assert retried_envelope.attempt == {
        "attempt_id": "attempt-803-2",
        "boundary_digest": previous.boundary_digest,
        "attempt_number": 2,
        "lease_generation": 5,
        "fencing_token": "fence-803-2",
        "agent_instance": previous.agent_instance,
        "lease_expires_at": "2026-09-12T14:15:00+07:00",
    }
    assert retried_envelope.idempotency_key == "idem-803-2"
    assert retried_envelope.digest() != previous_envelope.digest()


@pytest.mark.parametrize(
    ("changes", "code"),
    (
        ({"message_id": "message-803-1"}, MailboxV2ErrorCode.CONTRACT_MISMATCH),
        ({"attempt_id": "attempt-803-1"}, MailboxV2ErrorCode.CONTRACT_MISMATCH),
        ({"fencing_token": "fence-803-1"}, MailboxV2ErrorCode.CONTRACT_MISMATCH),
        ({"idempotency_key": "idem-803-1"}, MailboxV2ErrorCode.CONTRACT_MISMATCH),
        ({"seq": 10}, MailboxV2ErrorCode.INVALID_SEQUENCE),
        ({"lease_generation": 4}, MailboxV2ErrorCode.STALE_GENERATION),
    ),
)
def test_retry_rejects_reused_or_non_monotonic_identity(
    changes: dict[str, Any], code: str
) -> None:
    with pytest.raises(MailboxV2ValidationError) as caught:
        retry_bounded_mailbox_request(
            _request(),
            message_id=changes.get("message_id", "message-803-2"),
            seq=changes.get("seq", 11),
            attempt_id=changes.get("attempt_id", "attempt-803-2"),
            lease_generation=changes.get("lease_generation", 5),
            fencing_token=changes.get("fencing_token", "fence-803-2"),
            lease_expires_at="2026-09-12T14:15:00+07:00",
            idempotency_key=changes.get("idempotency_key", "idem-803-2"),
        )

    assert getattr(caught.value, "code", None) == code


def test_prior_late_result_is_evidence_only_against_current_retry_identity() -> None:
    previous = _request()
    retried = _retry(previous)
    previous_result = _terminal_result(previous, message_id="result-803-1", seq=1)
    retried_result = _terminal_result(retried, message_id="result-803-2", seq=2)
    current = _current_identity(compile_bounded_mailbox_request(retried))

    late_decision = validate_state_advancing_write(
        previous_result,
        current_identity=current,
        expected_source_digest=retried.source_digest,
        actor_cursor=-1,
        write_kind="terminal_result",
    )
    current_decision = validate_state_advancing_write(
        retried_result,
        current_identity=current,
        expected_source_digest=retried.source_digest,
        actor_cursor=-1,
        write_kind="terminal_result",
    )

    assert late_decision.disposition == StateAdvancingDisposition.STALE_RESULT
    assert late_decision.advances_state is False
    assert late_decision.evidence_only is True
    assert late_decision.failed_checks == ("attempt_id", "lease_generation")
    assert current_decision.disposition == StateAdvancingDisposition.ACCEPTED
    assert current_decision.advances_state is True
    assert current_decision.evidence_only is False
