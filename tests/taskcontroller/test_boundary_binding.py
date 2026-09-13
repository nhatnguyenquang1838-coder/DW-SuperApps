"""TC-MBX-307: bind ExecutionBoundary digests across v2 records."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.controlplane.execution_boundary import ExecutionBoundary
from taskcontroller.controlplane.request_compiler import BoundedMailboxRequest, compile_bounded_mailbox_request
from taskcontroller.interaction.mailbox_v2 import (
    MailboxV2ValidationError,
    V2MailboxEnvelope,
    canonical_digest,
)


_REPLAN_TRIGGERS = (
    "action_not_allowed",
    "authority_expansion",
    "new_source_required",
    "scope_expansion",
)
_FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"


def _boundary(**changes: object) -> ExecutionBoundary:
    values: dict[str, object] = {
        "allowed_actions": ("analyze", "read_repo", "run_tests"),
        "denied_actions": ("deploy", "merge"),
        "writable_targets": ("taskcontroller",),
        "source_roots": ("taskcontroller", "tests/taskcontroller"),
        "max_children": 4,
        "max_parallel": 2,
        "max_depth": 1,
        "replan_required_when": _REPLAN_TRIGGERS,
    }
    values.update(changes)
    return ExecutionBoundary(**values)


def _scope(boundary: ExecutionBoundary) -> dict[str, Any]:
    payload = boundary.to_dict()
    payload.pop("scope_digest")
    return payload


def _bound_request(boundary: ExecutionBoundary) -> BoundedMailboxRequest:
    return BoundedMailboxRequest(
        message_id="message-307",
        run_id="run-307",
        node_id="node-307",
        seq=0,
        correlation_id="correlation-307",
        contract_id="contract-307",
        plan_version="plan-307",
        contract_digest="sha256:" + "1" * 64,
        boundary_digest=boundary.digest(),
        source_digest="sha256:" + "2" * 64,
        source_manifest_ref="source-manifest-307",
        objective="Bind one execution boundary without widening authority.",
        scope=_scope(boundary),
        authority_constraints={},
        acceptance_criteria=("The boundary digest is present in every bound record.",),
        source_refs=(
            {
                "repository": "owner/repo",
                "commit_sha": "a" * 40,
                "path": "taskcontroller/controlplane/execution_boundary.py",
                "blob_digest": "sha256:" + "3" * 64,
            },
        ),
        standards_profile={
            "profile_id": "standards.default",
            "version": "1",
            "digest": "sha256:" + "4" * 64,
        },
        standards_profile_ref="standards.default/v1",
        recipient_capability="taskcontroller.executor",
        agent_instance="hermes-mac",
        environment_requirements={"os": "darwin", "runtime": "python3.11", "arch": "arm64"},
        attempt_id="attempt-307",
        attempt_number=1,
        lease_generation=1,
        fencing_token="fence-307",
        lease_expires_at="2026-09-11T08:00:00+07:00",
        idempotency_key="idem-307",
        producer_namespace="controller",
        producer_actor_id="controller-307",
        execution_id="execution-307",
        execution_boundary=boundary,  # type: ignore[call-arg]
    )


def _fixture(name: str) -> dict[str, Any]:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["cases"][name]
    return copy.deepcopy(payload)


def _bind_fixture_sections(payload: dict[str, Any]) -> dict[str, Any]:
    digest = payload["logical_contract"]["boundary_digest"]
    payload["attempt"]["boundary_digest"] = digest
    if payload.get("result") is not None:
        payload["result"]["boundary_digest"] = digest
    payload["digest"] = canonical_digest(payload)
    return payload


def test_compiler_binds_boundary_digest_into_request_attempt() -> None:
    from taskcontroller.controlplane.boundary_binding import BoundaryBinding

    boundary = _boundary()
    envelope = compile_bounded_mailbox_request(_bound_request(boundary))
    bound = BoundaryBinding(boundary).bind_request(envelope)
    payload = bound.to_dict()

    assert payload["logical_contract"]["boundary_digest"] == boundary.digest()
    assert payload["execution_identity"]["boundary_digest"] == boundary.digest()
    assert payload["attempt"]["boundary_digest"] == boundary.digest()
    assert bound.digest() == canonical_digest(payload)


def test_compiler_rejects_scope_expansion_and_digest_mismatch() -> None:
    from dataclasses import replace

    boundary = _boundary()
    expanded_scope = _scope(boundary)
    expanded_scope["allowed_actions"] = list(boundary.allowed_actions) + ["write_repo"]
    with pytest.raises(MailboxV2ValidationError) as scope_error:
        compile_bounded_mailbox_request(replace(_bound_request(boundary), scope=expanded_scope))
    assert scope_error.value.code == "REPLAN_REQUIRED"

    with pytest.raises(MailboxV2ValidationError) as digest_error:
        compile_bounded_mailbox_request(
            replace(_bound_request(boundary), boundary_digest="sha256:" + "0" * 64)
        )
    assert digest_error.value.code == "BOUNDARY_MISMATCH"


def test_child_contract_carries_child_and_parent_boundary_digests_with_proof() -> None:
    from taskcontroller.controlplane.boundary_binding import BoundaryBinding

    parent = _boundary()
    child = _boundary(
        allowed_actions=("analyze", "read_repo"),
        writable_targets=("taskcontroller/controlplane",),
        source_roots=("taskcontroller/controlplane",),
        max_children=1,
        max_parallel=1,
        max_depth=0,
    )
    original = {"child_id": "child-307", "scope": _scope(child)}

    bound = BoundaryBinding.for_child(parent, child).bind_child_contract(original)

    assert original == {"child_id": "child-307", "scope": _scope(child)}
    assert bound["boundary_digest"] == child.digest()
    assert bound["parent_boundary_digest"] == parent.digest()
    assert bound["boundary_subset_proof"]["valid"] is True
    assert bound["boundary_subset_proof"]["child_scope_digest"] == child.digest()


def test_child_scope_or_action_expansion_is_replan_required() -> None:
    from taskcontroller.controlplane.boundary_binding import BoundaryBinding
    from taskcontroller.controlplane.execution_boundary import REPLAN_REQUIRED, ExecutionBoundaryValidationError

    parent = _boundary()
    expanded = _boundary(allowed_actions=parent.allowed_actions + ("write_repo",))

    with pytest.raises(ExecutionBoundaryValidationError) as caught:
        BoundaryBinding.for_child(parent, expanded)

    assert caught.value.code == REPLAN_REQUIRED
    assert "allowed_actions_subset" in caught.value.failed_checks


def test_attempt_and_terminal_result_binding_is_copying_and_conflict_safe() -> None:
    from taskcontroller.controlplane.boundary_binding import BoundaryBinding

    binding = BoundaryBinding(_boundary())
    attempt = {"attempt_id": "attempt-307", "attempt_number": 1}
    result = {"status": "SUCCEEDED", "result_digest": "sha256:" + "5" * 64}

    bound_attempt = binding.bind_attempt(attempt)
    bound_result = binding.bind_terminal_result(result)

    assert "boundary_digest" not in attempt
    assert "boundary_digest" not in result
    assert bound_attempt["boundary_digest"] == binding.digest
    assert bound_result["boundary_digest"] == binding.digest

    conflicting = dict(attempt, boundary_digest="sha256:" + "0" * 64)
    with pytest.raises(MailboxV2ValidationError) as caught:
        binding.bind_attempt(conflicting)
    assert caught.value.code == "BOUNDARY_MISMATCH"


def test_v2_attempt_and_terminal_result_boundary_mismatch_fails_closed() -> None:
    valid_attempt = V2MailboxEnvelope.from_dict(_bind_fixture_sections(_fixture("execution_request")))
    assert valid_attempt.attempt["boundary_digest"] == valid_attempt.logical_contract["boundary_digest"]

    tampered_attempt = valid_attempt.to_dict()
    tampered_attempt["attempt"]["boundary_digest"] = "sha256:" + "0" * 64
    tampered_attempt["digest"] = canonical_digest(tampered_attempt)
    with pytest.raises(MailboxV2ValidationError) as caught_attempt:
        V2MailboxEnvelope.from_dict(tampered_attempt)
    assert caught_attempt.value.code == "BOUNDARY_MISMATCH"

    valid_terminal = V2MailboxEnvelope.from_dict(_bind_fixture_sections(_fixture("terminal_result")))
    tampered_result = valid_terminal.to_dict()
    tampered_result["result"]["boundary_digest"] = "sha256:" + "0" * 64
    tampered_result["digest"] = canonical_digest(tampered_result)
    with pytest.raises(MailboxV2ValidationError) as caught_result:
        V2MailboxEnvelope.from_dict(tampered_result)
    assert caught_result.value.code == "BOUNDARY_MISMATCH"


def test_boundary_binding_has_no_provider_or_transport_execution_path() -> None:
    from pathlib import Path

    from taskcontroller.controlplane import boundary_binding

    source = Path(boundary_binding.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "import requests" not in source
    assert "hermes-cloud" not in source
    assert "socket" not in source
    assert "urllib" not in source
