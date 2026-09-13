"""TC-MBX-301: deterministic Controller-side v2 request compilation."""

from __future__ import annotations

from typing import Any, Mapping, cast

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.controlplane.execution_boundary import (
    ExecutionBoundary,
    MAX_TIME_BUDGET_SECONDS,
    MAX_TOKEN_BUDGET,
)
from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)


_SOURCE_A = {
    "repository": "owner/repo",
    "commit_sha": "a" * 40,
    "path": "taskcontroller/domain/models.py",
    "blob_digest": "sha256:" + "1" * 64,
}
_SOURCE_B = {
    "repository": "owner/repo",
    "commit_sha": "b" * 40,
    "path": "taskcontroller/interaction/mailbox_v2.py",
    "blob_digest": "sha256:" + "2" * 64,
}


def _bound_request(**changes: Any) -> BoundedMailboxRequest:
    values: dict[str, Any] = {
        "message_id": "message-301",
        "run_id": "run-301",
        "node_id": "node-301",
        "seq": 0,
        "correlation_id": "correlation-301",
        "contract_id": "contract-301",
        "plan_version": "plan-301",
        "contract_digest": "sha256:" + "3" * 64,
        "boundary_digest": "sha256:" + "4" * 64,
        "source_digest": "sha256:" + "5" * 64,
        "source_manifest_ref": "source-manifest-301",
        "objective": "Compile one bounded request without transport payload leakage.",
        "scope": {
            "allowed_actions": ["read_repo", "run_tests"],
            "denied_actions": ["merge", "deploy"],
            "writable_targets": ["taskcontroller"],
            "source_roots": ["taskcontroller", "tests/taskcontroller"],
            "max_children": 0,
            "max_parallel": 1,
            "max_depth": 0,
        },
        "authority_constraints": {
            "denied_actions": ["merge", "deploy"],
            "writable_targets": ["taskcontroller"],
        },
        "acceptance_criteria": (
            "The envelope validates as mailbox/v2.",
            "The same bound state produces the same digest.",
        ),
        "source_refs": (_SOURCE_B, _SOURCE_A),
        "evidence_refs": ("evidence://tests/301", "evidence://contract/301"),
        "standards_profile": {
            "profile_id": "standards.default",
            "version": "1",
            "digest": "sha256:" + "6" * 64,
        },
        "standards_profile_ref": "standards.default/v1",
        "recipient_capability": "taskcontroller.executor",
        "agent_instance": "hermes-mac",
        "environment_requirements": {
            "os": "darwin",
            "runtime": "python3.11",
            "arch": "arm64",
            "capabilities": ["git", "pytest"],
        },
        "attempt_id": "attempt-301",
        "attempt_number": 1,
        "lease_generation": 7,
        "fencing_token": "fence-301",
        "lease_expires_at": "2026-09-11T05:00:00+07:00",
        "idempotency_key": "idem-301",
        "producer_namespace": "controller",
        "producer_actor_id": "controller-301",
        "execution_id": "execution-301",
    }
    values.update(changes)
    return BoundedMailboxRequest(**values)


def test_compiler_emits_valid_v2_request_with_bound_semantics() -> None:
    envelope = compile_bounded_mailbox_request(_bound_request())

    assert isinstance(envelope, V2MailboxEnvelope)
    payload = envelope.to_dict()
    assert payload["protocol"] == "dw.taskcontroller.mailbox/v2"
    assert payload["message_type"] == "execution_request"
    assert payload["direction"] == "controller_to_executor"
    assert payload["run_id"] == "run-301"
    assert payload["node_id"] == "node-301"
    assert payload["recipient"] == {
        "capability": "taskcontroller.executor",
        "agent_instance": "hermes-mac",
    }
    assert payload["logical_contract"]["objective"] == _bound_request().objective
    assert payload["logical_contract"]["acceptance_criteria"] == list(
        _bound_request().acceptance_criteria
    )
    assert payload["logical_contract"]["scope"]["denied_actions"] == ["deploy", "merge"]
    assert payload["logical_contract"]["source_digest"] == _bound_request().source_digest
    assert payload["source_manifest"]["digest"] == _bound_request().source_digest
    assert payload["standards_profile"] == _bound_request().standards_profile
    assert payload["execution_identity"] == {
        "run_id": "run-301",
        "node_id": "node-301",
        "plan_version": "plan-301",
        "contract_digest": "sha256:" + "3" * 64,
        "boundary_digest": "sha256:" + "4" * 64,
        "source_digest": "sha256:" + "5" * 64,
        "attempt_id": "attempt-301",
        "lease_generation": 7,
        "fencing_token": "fence-301",
    }
    assert payload["attempt"]["agent_instance"] == "hermes-mac"
    assert payload["payload"]["environment_requirements"] == _bound_request().environment_requirements
    assert payload["payload"]["evidence_refs"] == sorted(_bound_request().evidence_refs)
    assert payload["payload"]["execution_id"] == "execution-301"
    assert payload["provenance"]["source_refs"] == [
        "owner/repo@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:taskcontroller/domain/models.py",
        "owner/repo@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb:taskcontroller/interaction/mailbox_v2.py",
    ]
    assert envelope.digest() == canonical_digest(payload)


def test_same_bound_run_state_is_byte_and_digest_deterministic() -> None:
    first = compile_bounded_mailbox_request(_bound_request())
    second = compile_bounded_mailbox_request(
        _bound_request(
            scope={
                "max_depth": 0,
                "source_roots": ["taskcontroller", "tests/taskcontroller"],
                "writable_targets": ["taskcontroller"],
                "max_parallel": 1,
                "denied_actions": ["merge", "deploy"],
                "max_children": 0,
                "allowed_actions": ["read_repo", "run_tests"],
            },
            authority_constraints={
                "writable_targets": ["taskcontroller"],
                "denied_actions": ["merge", "deploy"],
            },
            source_refs=(_SOURCE_A, _SOURCE_B),
            evidence_refs=("evidence://contract/301", "evidence://tests/301"),
            standards_profile={
                "digest": "sha256:" + "6" * 64,
                "version": "1",
                "profile_id": "standards.default",
            },
        )
    )

    assert first.to_dict() == second.to_dict()
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.digest() == second.digest()


def test_scope_and_authority_conflict_fails_closed_without_widening() -> None:
    request = _bound_request(
        scope={
            "allowed_actions": ["read_repo"],
            "denied_actions": ["merge"],
            "writable_targets": [],
            "source_roots": ["taskcontroller"],
            "max_children": 0,
            "max_parallel": 1,
            "max_depth": 0,
        },
        authority_constraints={"allowed_actions": ["read_repo", "write_repo"]},
    )

    with pytest.raises(TaskControllerValidationError) as caught:
        compile_bounded_mailbox_request(request)

    assert getattr(caught.value, "code", None) == "BOUNDARY_MISMATCH"


def test_missing_bound_authority_is_not_filled_with_unsafe_defaults() -> None:
    request = _bound_request(
        scope={
            "allowed_actions": ["read_repo"],
            "denied_actions": [],
            "writable_targets": [],
            "source_roots": ["taskcontroller"],
        },
        authority_constraints={},
    )

    with pytest.raises(TaskControllerValidationError) as caught:
        compile_bounded_mailbox_request(request)

    assert getattr(caught.value, "code", None) == "SCHEMA_INVALID"
    assert "max_children" in str(caught.value)


def test_stale_identity_or_missing_source_reference_cannot_compile() -> None:
    stale = _bound_request(fencing_token="")
    with pytest.raises(TaskControllerValidationError) as caught:
        compile_bounded_mailbox_request(stale)
    assert getattr(caught.value, "code", None) == "SCHEMA_INVALID"

    missing_source = _bound_request(source_refs=())
    with pytest.raises(TaskControllerValidationError) as caught:
        compile_bounded_mailbox_request(missing_source)
    assert getattr(caught.value, "code", None) == "SCHEMA_INVALID"


def test_mapping_input_is_supported_without_changing_compiler_semantics() -> None:
    request = _bound_request()
    envelope = compile_bounded_mailbox_request(request.__dict__)
    assert envelope.to_dict()["idempotency_key"] == request.idempotency_key
    assert envelope.to_dict()["digest"] == envelope.digest()


def test_execution_boundary_budgets_round_trip_through_compiler() -> None:
    boundary = ExecutionBoundary(
        allowed_actions=("read_repo", "run_tests"),
        denied_actions=("deploy", "merge"),
        writable_targets=("taskcontroller",),
        source_roots=("taskcontroller", "tests/taskcontroller"),
        max_children=0,
        max_parallel=1,
        max_depth=0,
        replan_required_when=("scope_expansion",),
        time_budget_seconds=120,
        token_budget=5000,
    )
    scope = boundary.to_dict()
    scope.pop("scope_digest")
    request = _bound_request(
        boundary_digest=boundary.digest(),
        scope=scope,
        authority_constraints={
            "denied_actions": ["merge", "deploy"],
            "writable_targets": ["taskcontroller"],
        },
        execution_boundary=boundary,
    )

    envelope = compile_bounded_mailbox_request(request)
    compiled_scope = envelope.to_dict()["logical_contract"]["scope"]
    assert compiled_scope["time_budget_seconds"] == 120
    assert compiled_scope["token_budget"] == 5000
    assert envelope.digest() == canonical_digest(envelope.to_dict())


def test_unbounded_budget_scope_omission_and_null_are_valid() -> None:
    omitted = compile_bounded_mailbox_request(_bound_request())
    omitted_scope = omitted.to_dict()["logical_contract"]["scope"]
    assert omitted_scope["time_budget_seconds"] is None
    assert omitted_scope["token_budget"] is None

    scope = dict(cast(Mapping[str, Any], _bound_request().scope))
    scope.update({"time_budget_seconds": None, "token_budget": None})
    explicit_null = compile_bounded_mailbox_request(_bound_request(scope=scope))
    explicit_scope = explicit_null.to_dict()["logical_contract"]["scope"]
    assert explicit_scope["time_budget_seconds"] is None
    assert explicit_scope["token_budget"] is None


def test_budget_scope_and_authority_conflict_fails_closed() -> None:
    request = _bound_request(
        scope={**dict(cast(Mapping[str, Any], _bound_request().scope)), "time_budget_seconds": 60},
        authority_constraints={"time_budget_seconds": 61},
    )

    with pytest.raises(TaskControllerValidationError) as caught:
        compile_bounded_mailbox_request(request)

    assert getattr(caught.value, "code", None) == "BOUNDARY_MISMATCH"


def test_budget_scope_out_of_range_fails_closed() -> None:
    for field, value in (
        ("time_budget_seconds", 0),
        ("time_budget_seconds", -1),
        ("time_budget_seconds", True),
        ("time_budget_seconds", MAX_TIME_BUDGET_SECONDS + 1),
        ("token_budget", 0),
        ("token_budget", -1),
        ("token_budget", False),
        ("token_budget", MAX_TOKEN_BUDGET + 1),
    ):
        request = _bound_request(
            scope={**dict(cast(Mapping[str, Any], _bound_request().scope)), field: value}
        )
        with pytest.raises(TaskControllerValidationError) as caught:
            compile_bounded_mailbox_request(request)
        assert getattr(caught.value, "code", None) == "SCHEMA_INVALID"
