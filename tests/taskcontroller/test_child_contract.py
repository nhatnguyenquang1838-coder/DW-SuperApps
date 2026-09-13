"""TC-MBX-503: bounded child-contract generation and subset proof."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from taskcontroller.controlplane.execution_boundary import (
    ExecutionBoundary,
    ExecutionBoundaryValidationError,
    REPLAN_REQUIRED,
)
from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)
from taskcontroller.interaction.mailbox_v2 import SOURCE_MANIFEST_VERSION
from taskcontroller.execution.child_contract import (
    CHILD_CONTRACT_PROTOCOL,
    ChildContract,
    ChildContractError,
    ChildContractInput,
    generate_child_contract,
    generate_child_contracts,
)


_PARENT_SOURCE = {
    "repository": "owner/repo",
    "commit_sha": "a" * 40,
    "path": "taskcontroller/execution/classifier.py",
    "blob_digest": "sha256:" + "1" * 64,
}
_SECOND_SOURCE = {
    "repository": "owner/repo",
    "commit_sha": "b" * 40,
    "path": "taskcontroller/controlplane/execution_boundary.py",
    "blob_digest": "sha256:" + "2" * 64,
}
_SOURCE_DIGEST = "sha256:" + "3" * 64
_STANDARDS_DIGEST = "sha256:" + "4" * 64
_PARENT_CONTRACT_DIGEST = "sha256:" + "5" * 64


_REPLAN_TRIGGERS = (
    "action_not_allowed",
    "authority_expansion",
    "new_source_required",
    "scope_expansion",
)


def _boundary(**changes: Any) -> ExecutionBoundary:
    values: dict[str, Any] = {
        "allowed_actions": ("analyze", "read_repo", "run_tests", "review"),
        "denied_actions": ("deploy", "merge", "mutate_production"),
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
    result = boundary.to_dict()
    result.pop("scope_digest")
    return result


def _parent(**changes: Any) -> dict[str, Any]:
    parent_boundary = _boundary()
    values: dict[str, Any] = {
        "run_id": "run-503",
        "node_id": "node-503",
        "contract_id": "contract-503",
        "contract_digest": _PARENT_CONTRACT_DIGEST,
        "plan_version": "plan-503",
        "boundary": parent_boundary.to_dict(),
        "source_digest": _SOURCE_DIGEST,
        "source_manifest_ref": "source-manifest-503",
        "source_manifest": {
            "manifest_version": SOURCE_MANIFEST_VERSION,
            "digest": _SOURCE_DIGEST,
            "sources": [_SECOND_SOURCE, _PARENT_SOURCE],
        },
        "standards_profile_ref": "standards.default/v1",
        "standards_profile": {
            "profile_id": "standards.default",
            "version": "v1",
            "digest": _STANDARDS_DIGEST,
        },
        "objective": "Review one bounded TaskController execution seam.",
        "acceptance_criteria": (
            "The child contract remains inside the parent authority.",
            "The child records exact source and standards identities.",
        ),
        "agent_instance": "hermes-mac",
    }
    values.update(changes)
    return values


def _child_boundary(**changes: Any) -> ExecutionBoundary:
    values: dict[str, Any] = {
        "allowed_actions": ("analyze", "read_repo"),
        "denied_actions": ("deploy", "merge", "mutate_production", "write_unrelated"),
        "writable_targets": ("taskcontroller/execution",),
        "source_roots": ("taskcontroller/execution",),
        "max_children": 1,
        "max_parallel": 1,
        "max_depth": 0,
        "replan_required_when": _REPLAN_TRIGGERS + ("child_output_invalid",),
    }
    values.update(changes)
    return ExecutionBoundary(**values)


def _proposal(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "child_id": "child-503-implementation",
        "lens": "implementation",
        "boundary": _child_boundary(),
        "objective": "Inspect the bounded implementation seam only.",
        "acceptance_criteria": (
            "The child contract remains inside the parent authority.",
        ),
        "agent_instance": "hermes-mac",
    }
    values.update(changes)
    return values


def test_generate_child_contract_rejects_optional_budget_expansion() -> None:
    with pytest.raises(ExecutionBoundaryValidationError) as caught:
        parent = _parent(boundary=_boundary(time_budget_seconds=60, token_budget=1000))
        generate_child_contract(
            parent,
            _proposal(
                boundary=_child_boundary(time_budget_seconds=61, token_budget=1001),
            ),
        )
    assert caught.value.code == REPLAN_REQUIRED
    assert "child_budgets_within_parent" in caught.value.failed_checks


def test_generate_child_contract_proves_subset_and_inherits_exact_bindings() -> None:
    parent = _parent()
    child = generate_child_contract(parent, _proposal())

    assert isinstance(child, ChildContract)
    payload = child.to_dict()
    assert payload["protocol"] == CHILD_CONTRACT_PROTOCOL
    assert payload["child_id"] == "child-503-implementation"
    assert payload["parent_contract_id"] == parent["contract_id"]
    assert payload["parent_contract_digest"] == parent["contract_digest"]
    assert payload["run_id"] == parent["run_id"]
    assert payload["node_id"] == parent["node_id"]
    assert payload["plan_version"] == parent["plan_version"]
    assert payload["lens"] == "implementation"
    assert payload["scope"] == _scope(_child_boundary())
    assert payload["boundary_digest"] == _child_boundary().digest()
    assert payload["parent_boundary_digest"] == _boundary().digest()
    assert payload["boundary_subset_proof"] == {
        "valid": True,
        "parent_scope_digest": _boundary().digest(),
        "child_scope_digest": _child_boundary().digest(),
        "checks": [
            "allowed_actions_subset",
            "denied_actions_preserved",
            "writable_targets_subset",
            "source_roots_subset",
            "child_budgets_within_parent",
            "replan_triggers_preserved",
        ],
    }
    assert payload["standards_profile"] == parent["standards_profile"]
    assert payload["standards_profile_ref"] == parent["standards_profile_ref"]
    assert payload["source_manifest"] == {
        "manifest_version": SOURCE_MANIFEST_VERSION,
        "digest": _SOURCE_DIGEST,
        "sources": [_PARENT_SOURCE, _SECOND_SOURCE],
    }
    assert payload["source_manifest_ref"] == parent["source_manifest_ref"]
    assert payload["source_digest"] == _SOURCE_DIGEST
    assert payload["agent_instance"] == "hermes-mac"
    assert payload["digest"] == child.digest()
    assert child.contract_digest == child.digest()
    assert child.boundary_subset_proof.valid is True
    assert child.boundary_subset_proof.child_scope_digest == child.boundary_digest
    assert child.boundary.is_subset_of(_boundary())


def test_child_contract_is_immutable_and_does_not_mutate_parent_or_proposal() -> None:
    parent = _parent()
    proposal = _proposal()
    parent_before = repr(parent)
    proposal_before = repr(proposal)

    child = generate_child_contract(parent, proposal)

    assert repr(parent) == parent_before
    assert repr(proposal) == proposal_before
    with pytest.raises(FrozenInstanceError):
        child.child_id = "tampered"  # type: ignore[misc]

    returned = child.to_dict()
    returned["scope"]["allowed_actions"].append("write_repo")
    returned["standards_profile"]["digest"] = "sha256:" + "0" * 64
    assert child.to_dict()["scope"]["allowed_actions"] == ["analyze", "read_repo"]
    assert child.to_dict()["standards_profile"]["digest"] == _STANDARDS_DIGEST


def test_same_bound_parent_and_proposal_produce_same_bytes_and_digest() -> None:
    first = generate_child_contract(_parent(), _proposal())
    second = generate_child_contract(
        _parent(
            source_manifest={
                "sources": [_PARENT_SOURCE, _SECOND_SOURCE],
                "digest": _SOURCE_DIGEST,
                "manifest_version": SOURCE_MANIFEST_VERSION,
            }
        ),
        _proposal(),
    )

    assert first.to_dict() == second.to_dict()
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.digest() == second.digest()


def test_child_contract_input_accepts_only_bounded_explicit_fields() -> None:
    descriptor = ChildContractInput.from_mapping(_proposal())
    assert descriptor.child_id == "child-503-implementation"
    assert descriptor.lens == "implementation"
    assert descriptor.boundary == _child_boundary()
    assert descriptor.to_dict()["boundary"]["scope_digest"] == _child_boundary().digest()

    for forbidden in ("prompt", "messages", "reasoning", "transcript"):
        with pytest.raises(ChildContractError) as caught:
            ChildContractInput.from_mapping(_proposal(**{forbidden: "must not persist"}))
        assert caught.value.code == "SCHEMA_INVALID"


def test_child_scope_expansion_is_replan_required_without_silent_truncation() -> None:
    parent = _parent()
    expansion_cases = (
        ("allowed_actions", ("analyze", "read_repo", "write_repo"), "allowed_actions_subset"),
        ("writable_targets", ("taskcontroller", "outside"), "writable_targets_subset"),
        ("source_roots", ("taskcontroller", "outside"), "source_roots_subset"),
        ("max_children", 5, "child_budgets_within_parent"),
        ("max_parallel", 3, "child_budgets_within_parent"),
        ("max_depth", 2, "child_budgets_within_parent"),
        (
            "replan_required_when",
            ("action_not_allowed",),
            "replan_triggers_preserved",
        ),
    )

    for field, value, failed_check in expansion_cases:
        expanded = _child_boundary(**{field: value})
        with pytest.raises(ExecutionBoundaryValidationError) as caught:
            generate_child_contract(parent, _proposal(boundary=expanded))
        assert caught.value.code == REPLAN_REQUIRED
        assert failed_check in caught.value.failed_checks


def test_child_proposal_cannot_replace_parent_standards_or_source_identity() -> None:
    for field, value in (
        (
            "standards_profile",
            {
                "profile_id": "standards.other",
                "version": "v9",
                "digest": "sha256:" + "9" * 64,
            },
        ),
        (
            "source_manifest",
            {
                "manifest_version": SOURCE_MANIFEST_VERSION,
                "digest": "sha256:" + "9" * 64,
                "sources": [_PARENT_SOURCE],
            },
        ),
    ):
        with pytest.raises(ChildContractError) as caught:
            generate_child_contract(_parent(), _proposal(**{field: value}))
        assert caught.value.code == "CONTRACT_MISMATCH"


def test_missing_or_tampered_parent_binding_fails_closed() -> None:
    with pytest.raises(ChildContractError) as missing_boundary:
        generate_child_contract(
            _parent(boundary=None, execution_boundary=None),
            _proposal(),
        )
    assert missing_boundary.value.code == "SCHEMA_INVALID"

    child = generate_child_contract(_parent(), _proposal())
    tampered = child.to_dict()
    tampered["boundary_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ChildContractError) as digest_error:
        ChildContract.from_dict(tampered)
    assert digest_error.value.code == "DIGEST_MISMATCH"


def test_generate_child_contracts_rejects_duplicate_ids_and_oversubscription() -> None:
    parent = _parent()
    proposals = [
        _proposal(child_id="child-1", lens="architecture"),
        _proposal(child_id="child-2", lens="testing"),
    ]
    contracts = generate_child_contracts(parent, proposals)
    assert tuple(item.child_id for item in contracts) == ("child-1", "child-2")
    assert all(item.boundary_subset_proof.valid for item in contracts)

    with pytest.raises(ChildContractError) as duplicate:
        generate_child_contracts(parent, [_proposal(child_id="child-1"), _proposal(child_id="child-1")])
    assert duplicate.value.code == "SCHEMA_INVALID"

    too_many = [
        _proposal(child_id=f"child-{index}", lens="implementation")
        for index in range(5)
    ]
    with pytest.raises(ChildContractError) as oversubscribed:
        generate_child_contracts(parent, too_many)
    assert oversubscribed.value.code == REPLAN_REQUIRED


def test_child_contract_digest_changes_when_bound_scope_changes() -> None:
    first = generate_child_contract(_parent(), _proposal())
    narrower = generate_child_contract(
        _parent(),
        _proposal(
            child_id="child-503-narrower",
            boundary=_child_boundary(allowed_actions=("read_repo",)),
        ),
    )

    assert first.digest() != narrower.digest()
    assert narrower.boundary.is_subset_of(_boundary())


def test_child_contract_does_not_contain_transport_or_hidden_reasoning_fields() -> None:
    payload = generate_child_contract(_parent(), _proposal()).to_dict()
    forbidden = {"prompt", "message", "messages", "reasoning", "transcript", "provider_state"}
    assert forbidden.isdisjoint(payload)
    assert forbidden.isdisjoint(payload["scope"])
    assert forbidden.isdisjoint(payload["standards_profile"])
    assert forbidden.isdisjoint(payload["source_manifest"])


def test_compiled_v2_parent_supplies_canonical_identity_without_payload_authority() -> None:
    parent_boundary = _boundary()
    request = BoundedMailboxRequest(
        message_id="message-503",
        run_id="run-503",
        node_id="node-503",
        seq=0,
        correlation_id="correlation-503",
        contract_id="contract-503",
        plan_version="plan-503",
        contract_digest=_PARENT_CONTRACT_DIGEST,
        boundary_digest=parent_boundary.digest(),
        source_digest=_SOURCE_DIGEST,
        source_manifest_ref="source-manifest-503",
        objective="Review one bounded TaskController execution seam.",
        scope=_scope(parent_boundary),
        authority_constraints={
            "denied_actions": list(parent_boundary.denied_actions),
            "writable_targets": list(parent_boundary.writable_targets),
        },
        acceptance_criteria=(
            "The child contract remains inside the parent authority.",
            "The child records exact source and standards identities.",
        ),
        source_refs=(_SECOND_SOURCE, _PARENT_SOURCE),
        evidence_refs=("evidence://contract/503",),
        standards_profile={
            "profile_id": "standards.default",
            "version": "v1",
            "digest": _STANDARDS_DIGEST,
        },
        standards_profile_ref="standards.default/v1",
        recipient_capability="taskcontroller.executor",
        agent_instance="hermes-mac",
        attempt_id="attempt-503",
        attempt_number=1,
        lease_generation=1,
        fencing_token="fence-503",
        lease_expires_at="2026-09-11T05:00:00+07:00",
        idempotency_key="idem-503",
        payload={"safe_observation": "not an authority source"},
        execution_boundary=parent_boundary,
    )
    envelope = compile_bounded_mailbox_request(request)

    child = generate_child_contract(
        envelope,
        _proposal(agent_instance=None),
    )

    assert child.parent_contract_id == "contract-503"
    assert child.parent_contract_digest == _PARENT_CONTRACT_DIGEST
    assert child.agent_instance == "hermes-mac"
    assert child.standards_profile == request.standards_profile
    assert child.source_digest == _SOURCE_DIGEST
    assert child.source_manifest["digest"] == _SOURCE_DIGEST
