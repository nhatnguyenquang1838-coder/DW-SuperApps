from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.errors import TaskControllerValidationError


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
V1_PROTOCOL = "dw.taskcontroller.a2a/v1"
V2_PROTOCOL = "dw.taskcontroller.mailbox/v2"


def _api():
    """Load the wished-for additive v2 API so a missing module is a real RED."""
    try:
        from taskcontroller.interaction.mailbox_v2 import (
            MailboxV2Cursor,
            V2MailboxEnvelope,
            canonical_bytes,
            canonical_digest,
            get_v2_schema,
            negotiate_protocol,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"v2 contract module is missing: {exc}")
    return (
        MailboxV2Cursor,
        V2MailboxEnvelope,
        canonical_bytes,
        canonical_digest,
        get_v2_schema,
        negotiate_protocol,
    )


def _digest(value: dict[str, Any]) -> dict[str, Any]:
    *_, canonical_digest, _, _ = _api()
    value = copy.deepcopy(value)
    value["digest"] = canonical_digest(value)
    return value


def _source_manifest() -> dict[str, Any]:
    return {
        "manifest_version": "dw-source-manifest-json/v1",
        "digest": "sha256:" + "4" * 64,
        "sources": [
            {
                "repository": "owner/repo",
                "commit_sha": "a" * 40,
                "path": "taskcontroller/interaction/envelope.py",
                "blob_digest": "sha256:" + "5" * 64,
            }
        ],
    }


def _logical_contract() -> dict[str, Any]:
    return {
        "contract_id": "contract-1",
        "plan_version": "plan-1",
        "contract_digest": "sha256:" + "1" * 64,
        "boundary_digest": "sha256:" + "2" * 64,
        "source_digest": "sha256:" + "4" * 64,
        "objective": "Run one bounded mailbox v2 contract check.",
        "scope": {
            "allowed_actions": ["read_repo"],
            "denied_actions": ["merge", "deploy"],
            "writable_targets": [],
            "source_roots": ["taskcontroller"],
            "max_children": 6,
            "max_parallel": 4,
            "max_depth": 1,
        },
        "acceptance_criteria": [
            "The result contains deterministic evidence.",
        ],
        "standards_profile_ref": "standards.default/v1",
        "source_manifest_ref": "source-manifest-1",
    }


def _attempt(attempt_id: str = "attempt-1", generation: int = 1) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "boundary_digest": "sha256:" + "2" * 64,
        "attempt_number": 1,
        "lease_generation": generation,
        "fencing_token": f"fence-{generation}",
        "agent_instance": "hermes-mac",
        "lease_expires_at": "2026-09-11T00:30:00+07:00",
    }


def _base_payload(
    *, message_type: str = "execution_request", attempt_id: str = "attempt-1", generation: int = 1
) -> dict[str, Any]:
    logical = _logical_contract()
    attempt = _attempt(attempt_id, generation)
    return {
        "protocol": V2_PROTOCOL,
        "message_id": "message-1",
        "run_id": "run-1",
        "node_id": "node-1",
        "seq": 0,
        "correlation_id": "correlation-1",
        "direction": "controller_to_executor",
        "message_type": message_type,
        "producer": {
            "namespace": "controller",
            "actor_id": "controller-1",
            "role": "controller",
        },
        "recipient": {
            "capability": "taskcontroller.executor",
            "agent_instance": "hermes-mac",
        },
        "logical_contract": logical,
        "attempt": attempt,
        "execution_identity": {
            "run_id": "run-1",
            "node_id": "node-1",
            "plan_version": logical["plan_version"],
            "contract_digest": logical["contract_digest"],
            "boundary_digest": logical["boundary_digest"],
            "source_digest": logical["source_digest"],
            "attempt_id": attempt["attempt_id"],
            "lease_generation": attempt["lease_generation"],
            "fencing_token": attempt["fencing_token"],
        },
        "source_manifest": _source_manifest(),
        "standards_profile": {
            "profile_id": "standards.default",
            "version": "1",
            "digest": "sha256:" + "6" * 64,
        },
        "payload": {
            "objective": logical["objective"],
        },
        "provenance": {
            "origin": "controller",
            "parent_message_id": None,
            "child_id": None,
            "lens": None,
            "agent_instance": "hermes-mac",
            "status": "REQUESTED",
            "source_refs": ["owner/repo@" + "a" * 40 + ":taskcontroller/interaction/envelope.py"],
            "evidence_refs": [],
            "result_digest": None,
        },
        "idempotency_key": "idem-1",
    }


def _valid_message(message_type: str) -> dict[str, Any]:
    payload = _base_payload(message_type=message_type)
    if message_type == "child_result":
        payload["direction"] = "executor_to_controller"
        payload["provenance"].update(
            {"origin": "child", "child_id": "child-1", "lens": "implementation", "status": "SUCCEEDED"}
        )
        payload["payload"] = {
            "status": "SUCCEEDED",
            "result_digest": "sha256:" + "7" * 64,
        }
    elif message_type == "review_finding":
        payload["direction"] = "executor_to_controller"
        payload["provenance"].update(
            {"origin": "child", "child_id": "child-review-1", "lens": "reliability", "status": "SUCCEEDED"}
        )
        payload["payload"] = {
            "finding": {
                "finding_id": "finding-1",
                "severity": "major",
                "category": "reliability",
                "lens": "reliability",
                "claim": "A stale event must not advance the current state.",
                "evidence_refs": ["artifact://evidence-1"],
                "recommendation": "Reject stale generation before mutation.",
                "reviewer": "reviewer-1",
                "confidence": 0.95,
                "disposition": "OPEN",
                "conflict_group": None,
            }
        }
    elif message_type == "mixer_result":
        payload["direction"] = "executor_to_controller"
        payload["provenance"].update({"origin": "mixer", "lens": "adjudication", "status": "SUCCEEDED"})
        payload["payload"] = {
            "status": "NEEDS_CLARIFICATION",
            "findings": [],
            "result_digest": "sha256:" + "8" * 64,
        }
    elif message_type == "terminal_result":
        payload["direction"] = "executor_to_controller"
        payload["provenance"].update({"origin": "executor", "status": "SUCCEEDED"})
        payload["payload"] = {
            "status": "SUCCEEDED",
            "result_digest": "sha256:" + "9" * 64,
        }
    if message_type == "execution_request":
        payload["result"] = None
    elif message_type == "review_finding":
        payload["result"] = {
            "status": "SUCCEEDED",
            "boundary_digest": payload["logical_contract"]["boundary_digest"],
            "result_digest": "sha256:" + "a" * 64,
            "artifact_refs": [],
            "findings": [payload["payload"]["finding"]],
        }
    elif message_type == "child_result":
        payload["result"] = {
            "status": "SUCCEEDED",
            "boundary_digest": payload["logical_contract"]["boundary_digest"],
            "result_digest": payload["payload"]["result_digest"],
            "artifact_refs": [],
            "findings": [],
        }
    elif message_type == "mixer_result":
        payload["result"] = {
            "status": "NEEDS_CLARIFICATION",
            "boundary_digest": payload["logical_contract"]["boundary_digest"],
            "result_digest": payload["payload"]["result_digest"],
            "artifact_refs": [],
            "findings": [],
        }
    elif message_type == "terminal_result":
        payload["result"] = {
            "status": "SUCCEEDED",
            "boundary_digest": payload["logical_contract"]["boundary_digest"],
            "result_digest": payload["payload"]["result_digest"],
            "artifact_refs": [],
            "findings": [],
        }
    return _digest(payload)


def _assert_code(operation, expected: str) -> None:
    with pytest.raises(TaskControllerValidationError) as caught:
        operation()
    assert getattr(caught.value, "code", None) == expected


def test_v2_schema_is_strict_and_machine_identified() -> None:
    *_, get_v2_schema, _ = _api()
    schema = get_v2_schema()
    assert schema["$id"].endswith("mailbox_v2.schema.json")
    assert schema["additionalProperties"] is False
    assert {
        "protocol",
        "message_id",
        "run_id",
        "node_id",
        "seq",
        "correlation_id",
        "direction",
        "message_type",
        "producer",
        "recipient",
        "logical_contract",
        "attempt",
        "execution_identity",
        "source_manifest",
        "standards_profile",
        "payload",
        "provenance",
        "idempotency_key",
        "digest",
    }.issubset(set(schema["required"]))


def test_v2_atomic_envelope_round_trips_with_canonical_digest() -> None:
    *_, V2MailboxEnvelope, canonical_bytes, canonical_digest, _, _ = _api()
    payload = _valid_message("execution_request")
    envelope = V2MailboxEnvelope.from_dict(payload)
    assert envelope.to_dict() == payload
    assert envelope.canonical_bytes() == canonical_bytes(payload)
    assert envelope.digest() == canonical_digest(payload)
    assert envelope.digest().startswith("sha256:")


@pytest.mark.parametrize(
    "message_type",
    ["review_finding", "child_result", "mixer_result", "terminal_result"],
)
def test_v2_review_child_mixer_and_terminal_cases_are_machine_valid(message_type: str) -> None:
    *_, V2MailboxEnvelope, _, _, _, _ = _api()
    envelope = V2MailboxEnvelope.from_dict(_valid_message(message_type))
    assert envelope.to_dict()["message_type"] == message_type
    assert envelope.to_dict()["provenance"]["agent_instance"] == "hermes-mac"


@pytest.mark.parametrize(
    "path",
    [
        ("execution_identity", "attempt_id"),
        ("logical_contract", "scope"),
        (None, "digest"),
    ],
)
def test_v2_missing_identity_scope_or_digest_fails_with_stable_code(path: tuple[str | None, str]) -> None:
    *_, V2MailboxEnvelope, _, _, _, _ = _api()
    payload = _digest(_base_payload())
    if path[0] is None:
        payload.pop(path[1])
    else:
        payload[path[0]].pop(path[1])
    _assert_code(lambda: V2MailboxEnvelope.from_dict(payload), "SCHEMA_INVALID")


def test_v2_unsupported_protocol_fails_closed() -> None:
    *_, V2MailboxEnvelope, _, _, _, _ = _api()
    payload = _base_payload()
    payload["protocol"] = V1_PROTOCOL
    _assert_code(lambda: V2MailboxEnvelope.from_dict(payload), "UNSUPPORTED_PROTOCOL")


def test_v2_manifest_version_mismatch_is_not_generic_schema_text() -> None:
    *_, V2MailboxEnvelope, _, canonical_digest, _, _ = _api()
    payload = _base_payload()
    payload["source_manifest"]["manifest_version"] = "dw-source-manifest-json/v0"
    payload["digest"] = canonical_digest(payload)
    _assert_code(lambda: V2MailboxEnvelope.from_dict(payload), "MANIFEST_VERSION_MISMATCH")


def test_v2_tampered_payload_fails_digest_check() -> None:
    *_, V2MailboxEnvelope, _, _, _, _ = _api()
    payload = _valid_message("execution_request")
    payload["logical_contract"]["objective"] = "tampered"
    _assert_code(lambda: V2MailboxEnvelope.from_dict(payload), "DIGEST_MISMATCH")


def test_v2_canonical_bytes_are_utf8_sorted_compact_and_digest_excludes_self() -> None:
    *_, _, canonical_bytes, canonical_digest, _, _ = _api()
    original = _valid_message("execution_request")
    without_digest = dict(original)
    without_digest.pop("digest")
    reordered = json.loads(
        json.dumps(without_digest, ensure_ascii=False, indent=2, sort_keys=False)
    )
    reordered["digest"] = "sha256:" + "0" * 64
    assert canonical_bytes(without_digest) == canonical_bytes(reordered)
    assert canonical_digest(without_digest) == canonical_digest(reordered)
    assert b"  " not in canonical_bytes(without_digest)
    assert canonical_bytes(without_digest).decode("utf-8")
    assert "digest" not in json.loads(canonical_bytes(without_digest))


def test_v2_cursor_allows_exact_duplicate_noop_but_rejects_stale_sequence() -> None:
    MailboxV2Cursor, V2MailboxEnvelope, _, _, _, _ = _api()
    envelope = V2MailboxEnvelope.from_dict(_valid_message("execution_request"))
    cursor = MailboxV2Cursor(actor_namespace="controller", last_seq=-1)
    observed = cursor.observe(envelope)
    assert observed.last_seq == 0
    assert observed.observe(envelope) == observed
    stale = copy.deepcopy(_valid_message("execution_request"))
    stale["message_id"] = "message-stale"
    stale["idempotency_key"] = "idem-stale"
    stale = _digest(stale)
    _assert_code(
        lambda: observed.observe(V2MailboxEnvelope.from_dict(stale)),
        "INVALID_SEQUENCE",
    )


def test_v2_identity_validation_rejects_stale_generation_contract_and_boundary() -> None:
    *_, V2MailboxEnvelope, _, _, _, _ = _api()
    envelope = V2MailboxEnvelope.from_dict(_valid_message("execution_request"))
    _assert_code(lambda: envelope.validate_current_generation(2), "STALE_GENERATION")
    _assert_code(
        lambda: envelope.validate_current_identity({"contract_digest": "sha256:" + "a" * 64}),
        "CONTRACT_MISMATCH",
    )
    _assert_code(
        lambda: envelope.validate_current_identity({"boundary_digest": "sha256:" + "b" * 64}),
        "BOUNDARY_MISMATCH",
    )


def test_v2_logical_contract_is_reusable_across_distinct_attempts() -> None:
    *_, V2MailboxEnvelope, _, _, _, _ = _api()
    first = V2MailboxEnvelope.from_dict(_digest(_base_payload(attempt_id="attempt-1")))
    second_payload = _base_payload(attempt_id="attempt-2")
    second_payload["message_id"] = "message-2"
    second_payload["seq"] = 1
    second_payload["idempotency_key"] = "idem-2"
    second = V2MailboxEnvelope.from_dict(_digest(second_payload))
    assert first.to_dict()["logical_contract"] == second.to_dict()["logical_contract"]
    assert first.to_dict()["attempt"]["attempt_id"] != second.to_dict()["attempt"]["attempt_id"]
    assert first.to_dict()["execution_identity"]["attempt_id"] != second.to_dict()["execution_identity"]["attempt_id"]


def test_v2_protocol_negotiation_is_explicit_and_never_infers_missing_semantics() -> None:
    *_, _, _, _, _, negotiate_protocol = _api()
    assert negotiate_protocol(V1_PROTOCOL, V1_PROTOCOL).outcome == "SUPPORTED"
    assert negotiate_protocol(V2_PROTOCOL, V2_PROTOCOL).outcome == "SUPPORTED"
    assert negotiate_protocol(V1_PROTOCOL, V2_PROTOCOL).outcome == "LOSSLESS_ADAPTER"
    assert (
        negotiate_protocol(V1_PROTOCOL, V2_PROTOCOL, requires_v2_semantics=True).outcome
        == "REPLAN_REQUIRED"
    )
    assert (
        negotiate_protocol(V2_PROTOCOL, V1_PROTOCOL, requires_v2_semantics=True).outcome
        == "DOWNGRADE_UNSUPPORTED"
    )


def test_v1_to_v2_adapter_requires_explicit_controller_bound_fields() -> None:
    from taskcontroller.interaction.mailbox_v2 import adapt_v1_to_v2

    v1 = {"protocol": V1_PROTOCOL, "message": "legacy task"}
    _assert_code(
        lambda: adapt_v1_to_v2(v1),
        "PROTOCOL_DOWNGRADE_UNSUPPORTED",
    )
    incomplete = _valid_message("execution_request")
    incomplete.pop("execution_identity")
    _assert_code(
        lambda: adapt_v1_to_v2(v1, bound_v2_fields=incomplete),
        "PROTOCOL_DOWNGRADE_UNSUPPORTED",
    )
    adapted = adapt_v1_to_v2(v1, bound_v2_fields=_valid_message("execution_request"))
    assert adapted.protocol == V2_PROTOCOL
    assert adapted.to_dict()["payload"]["legacy_v1"] == v1


def test_v2_error_code_registry_is_stable() -> None:
    from taskcontroller.interaction.mailbox_v2 import MailboxV2ErrorCode

    assert {
        MailboxV2ErrorCode.SCHEMA_INVALID,
        MailboxV2ErrorCode.UNSUPPORTED_PROTOCOL,
        MailboxV2ErrorCode.PROTOCOL_DOWNGRADE_UNSUPPORTED,
        MailboxV2ErrorCode.INVALID_SEQUENCE,
        MailboxV2ErrorCode.STALE_GENERATION,
        MailboxV2ErrorCode.CONTRACT_MISMATCH,
        MailboxV2ErrorCode.BOUNDARY_MISMATCH,
        MailboxV2ErrorCode.MANIFEST_VERSION_MISMATCH,
        MailboxV2ErrorCode.DIGEST_MISMATCH,
    } == {
        "SCHEMA_INVALID",
        "UNSUPPORTED_PROTOCOL",
        "PROTOCOL_DOWNGRADE_UNSUPPORTED",
        "INVALID_SEQUENCE",
        "STALE_GENERATION",
        "CONTRACT_MISMATCH",
        "BOUNDARY_MISMATCH",
        "MANIFEST_VERSION_MISMATCH",
        "DIGEST_MISMATCH",
    }


def test_v2_checked_fixtures_are_immutable_regression_inputs() -> None:
    *_, V2MailboxEnvelope, _, _, _, _ = _api()
    assert FIXTURE_PATH.is_file(), f"missing v2 fixture: {FIXTURE_PATH}"
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert data["fixture_kind"] == "dw.taskcontroller.mailbox/v2-regression"
    assert data["captured_from_protocol"] == V2_PROTOCOL
    for case in data["cases"].values():
        envelope = V2MailboxEnvelope.from_dict(case)
        assert envelope.to_dict() == case
