from __future__ import annotations

from dataclasses import replace

import pytest

from taskcontroller.controlplane.execution_boundary import ExecutionBoundary
from taskcontroller.interaction.mailbox_v2 import SOURCE_MANIFEST_VERSION
from taskcontroller.execution.child_contract import (
    ChildContractInput,
    ParentContract,
    generate_child_contracts,
)
from taskcontroller.execution.fanout import (
    ChildLifecycle,
    ChildLifecycleState,
    CompletionStatus,
    FanoutCoordinator,
    FanoutCoordinatorError,
    FanoutMode,
    JoinSemantics,
    JoinStatus,
    NormalizedJoinInput,
    child_completion,
    transition_child_lifecycle,
)
from taskcontroller.execution.manifest import (
    DEFAULT_CHILD_TIMEOUT_SECONDS,
    FanoutManifest,
    FanoutManifestError,
)


_PARENT_DIGEST = "sha256:" + "1" * 64
_SOURCE_DIGEST = "sha256:" + "2" * 64
_STANDARDS_DIGEST = "sha256:" + "3" * 64
_SOURCE = {
    "repository": "owner/repo",
    "commit_sha": "1" * 40,
    "path": "AGENTS.md",
    "blob_digest": "sha256:" + "4" * 64,
}


def _boundary(*, max_parallel: int = 2, max_children: int = 6) -> ExecutionBoundary:
    return ExecutionBoundary(
        allowed_actions=("read_repo", "write_artifact"),
        denied_actions=("deploy", "merge"),
        writable_targets=("artifacts/**",),
        source_roots=("src",),
        max_children=max_children,
        max_parallel=max_parallel,
        max_depth=1,
        replan_required_when=("scope_expansion", "budget_exceeded"),
    )


def _parent() -> ParentContract:
    boundary = _boundary()
    return ParentContract(
        run_id="run-504",
        node_id="node-504",
        contract_id="contract-504",
        contract_digest=_PARENT_DIGEST,
        plan_version="plan-504",
        boundary=boundary,
        source_digest=_SOURCE_DIGEST,
        source_manifest_ref="manifest-504",
        source_manifest={
            "manifest_version": SOURCE_MANIFEST_VERSION,
            "digest": _SOURCE_DIGEST,
            "sources": [_SOURCE],
        },
        standards_profile_ref="standards.default/v1",
        standards_profile={
            "profile_id": "standards.default",
            "version": "v1",
            "digest": _STANDARDS_DIGEST,
        },
        objective="Coordinate bounded child execution.",
        acceptance_criteria=(
            "Every required child completion is represented.",
            "The normalized join is deterministic.",
        ),
        agent_instance="hermes-mac",
    )


def _children(count: int = 3, *, parent: ParentContract | None = None):
    parent = parent or _parent()
    child_boundary = ExecutionBoundary(
        allowed_actions=("read_repo",),
        denied_actions=("deploy", "merge"),
        writable_targets=("artifacts/review/**",),
        source_roots=("src",),
        max_children=1,
        max_parallel=1,
        max_depth=0,
        replan_required_when=("budget_exceeded", "scope_expansion"),
    )
    return generate_child_contracts(
        parent,
        [
            ChildContractInput(
                child_id=f"child-{index}",
                lens=f"lens-{index}",
                boundary=child_boundary,
                objective=f"Inspect child {index}.",
                acceptance_criteria=(parent.acceptance_criteria[0],),
            )
            for index in range(1, count + 1)
        ],
    )


def _completion(child, *, status: str = "SUCCEEDED", suffix: str = "result"):
    return child_completion(
        child_id=child.child_id,
        child_contract_digest=child.contract_digest,
        status=status,
        result_ref=f"github://result/{child.child_id}/{suffix}",
        result_digest="sha256:" + (str(ord(child.child_id[-1]))[-1] * 64),
    )


def test_parallel_completion_order_does_not_change_normalized_join_input_set() -> None:
    children = _children()
    first = FanoutCoordinator.from_children(children, parent=_parent(), mode=FanoutMode.PARALLEL, max_parallel=2)
    second = FanoutCoordinator.from_children(children, parent=_parent(), mode=FanoutMode.PARALLEL, max_parallel=2)

    assert first.dispatch_window() == ("child-1", "child-2")
    first = first.complete(_completion(children[1]))
    assert first.join().status is JoinStatus.NOT_READY
    first = first.complete(_completion(children[0]))
    first = first.complete(_completion(children[2]))

    second = second.complete(_completion(children[0]))
    second = second.complete(_completion(children[1]))
    second = second.complete(_completion(children[2]))

    first_join = first.join()
    second_join = second.join()
    assert first_join.status is JoinStatus.READY
    assert second_join.status is JoinStatus.READY
    assert isinstance(first_join.normalized_input, NormalizedJoinInput)
    assert first_join.normalized_input == second_join.normalized_input
    assert first_join.normalized_input.child_ids == ("child-1", "child-2", "child-3")
    assert first_join.normalized_input.digest == second_join.normalized_input.digest


def test_parallel_windows_are_bounded_and_join_is_an_explicit_barrier() -> None:
    children = _children(5)
    coordinator = FanoutCoordinator.from_children(children, parent=_parent(), mode="PARALLEL", max_parallel=2)

    assert coordinator.dispatch_window() == ("child-1", "child-2")
    coordinator = coordinator.complete(_completion(children[0]))
    assert coordinator.dispatch_window() == ("child-2",)
    assert coordinator.join().status is JoinStatus.NOT_READY

    coordinator = coordinator.complete(_completion(children[1]))
    assert coordinator.dispatch_window() == ("child-3", "child-4")
    assert len(coordinator.dispatch_window()) <= 2


def test_staged_execution_waits_for_current_stage_before_opening_next_stage() -> None:
    children = _children()
    coordinator = FanoutCoordinator.from_children(
        children,
        parent=_parent(),
        mode=FanoutMode.STAGED,
        max_parallel=2,
        stages=(("child-1", "child-3"), ("child-2",)),
    )

    assert coordinator.dispatch_window() == ("child-1", "child-3")
    coordinator = coordinator.complete(_completion(children[2]))
    assert coordinator.dispatch_window() == ("child-1",)
    coordinator = coordinator.complete(_completion(children[0]))
    assert coordinator.dispatch_window() == ("child-2",)
    assert coordinator.join().status is JoinStatus.NOT_READY

    coordinator = coordinator.complete(_completion(children[1]))
    assert coordinator.join().status is JoinStatus.READY


def test_duplicate_same_completion_is_idempotent_but_conflicting_completion_fails_closed() -> None:
    child = _children(1)[0]
    coordinator = FanoutCoordinator.from_children(
        (child,),
        parent=_parent(),
        mode="PARALLEL",
        max_parallel=1,
    )
    completion = _completion(child)

    once = coordinator.complete(completion)
    twice = once.complete(completion)
    assert twice.join().normalized_input == once.join().normalized_input

    with pytest.raises(ValueError, match="conflicting completion"):
        once.complete(_completion(child, suffix="different"))


def test_completion_must_bind_known_current_child_and_cannot_bypass_stage() -> None:
    children = _children()
    coordinator = FanoutCoordinator.from_children(
        children,
        parent=_parent(),
        mode="STAGED",
        max_parallel=2,
        stages=(("child-1",), ("child-2", "child-3")),
    )

    with pytest.raises(ValueError, match="current dispatch window"):
        coordinator.complete(_completion(children[1]))

    foreign = replace(_completion(children[0]), child_id="foreign-child")
    with pytest.raises(ValueError, match="unknown child"):
        coordinator.complete(foreign)


def test_failed_required_child_blocks_join_and_does_not_open_next_stage() -> None:
    children = _children(2)
    coordinator = FanoutCoordinator.from_children(
        children,
        parent=_parent(),
        mode="STAGED",
        max_parallel=2,
        stages=(("child-1",), ("child-2",)),
    )
    coordinator = coordinator.complete(_completion(children[0], status=CompletionStatus.FAILED))
    decision = coordinator.join()

    assert decision.status is JoinStatus.BLOCKED
    assert decision.failed_child_ids == ("child-1",)
    assert decision.normalized_input.child_ids == ("child-1",)
    assert coordinator.dispatch_window() == ()


def test_plan_rejects_invalid_stages_and_parent_budget_overrides() -> None:
    children = _children(3)
    with pytest.raises(ValueError, match="max_parallel"):
        FanoutCoordinator.from_children(children, parent=_parent(), mode="PARALLEL", max_parallel=3)

    with pytest.raises(ValueError, match="exactly once"):
        FanoutCoordinator.from_children(
            children,
            parent=_parent(),
            mode="STAGED",
            max_parallel=2,
            stages=(("child-1", "child-1"), ("child-2", "child-3")),
        )


def test_completion_requires_bound_result_reference_and_digest() -> None:
    child = _children(1)[0]
    with pytest.raises(ValueError, match="result_ref"):
        child_completion(
            child_id=child.child_id,
            child_contract_digest=child.contract_digest,
            status="SUCCEEDED",
            result_ref="",
            result_digest="sha256:" + "5" * 64,
        )
    with pytest.raises(ValueError, match="result_digest"):
        child_completion(
            child_id=child.child_id,
            child_contract_digest=child.contract_digest,
            status="SUCCEEDED",
            result_ref="github://result/child-1",
            result_digest="not-a-digest",
        )


def test_child_lifecycle_vocabulary_is_normative_and_terminal_states_are_explicit() -> None:
    assert tuple(state.value for state in ChildLifecycle) == (
        "PLANNED",
        "DISPATCHED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "TIMED_OUT",
        "CANCELLED",
        "STALE",
    )
    assert ChildLifecycle.non_terminal_states() == (
        ChildLifecycle.PLANNED,
        ChildLifecycle.DISPATCHED,
        ChildLifecycle.RUNNING,
    )
    assert ChildLifecycle.terminal_states() == (
        ChildLifecycle.SUCCEEDED,
        ChildLifecycle.FAILED,
        ChildLifecycle.TIMED_OUT,
        ChildLifecycle.CANCELLED,
        ChildLifecycle.STALE,
    )
    assert not ChildLifecycle.RUNNING.is_terminal
    assert ChildLifecycle.STALE.is_terminal


def test_child_lifecycle_transition_table_is_fail_closed_and_replay_idempotent() -> None:
    state = ChildLifecycleState(child_id="child-1")
    for target in (
        ChildLifecycle.DISPATCHED,
        ChildLifecycle.RUNNING,
        ChildLifecycle.SUCCEEDED,
    ):
        state = state.transition(target)
    assert state.state is ChildLifecycle.SUCCEEDED
    assert state.transition(ChildLifecycle.SUCCEEDED) is state

    valid_paths = (
        (ChildLifecycle.PLANNED, ChildLifecycle.CANCELLED),
        (ChildLifecycle.PLANNED, ChildLifecycle.STALE),
        (ChildLifecycle.DISPATCHED, ChildLifecycle.TIMED_OUT),
        (ChildLifecycle.RUNNING, ChildLifecycle.FAILED),
        (ChildLifecycle.RUNNING, ChildLifecycle.CANCELLED),
        (ChildLifecycle.RUNNING, ChildLifecycle.STALE),
    )
    for current, target in valid_paths:
        assert transition_child_lifecycle(current, target) is target

    invalid_paths = (
        (ChildLifecycle.PLANNED, ChildLifecycle.RUNNING),
        (ChildLifecycle.PLANNED, ChildLifecycle.SUCCEEDED),
        (ChildLifecycle.DISPATCHED, ChildLifecycle.SUCCEEDED),
        (ChildLifecycle.SUCCEEDED, ChildLifecycle.FAILED),
        (ChildLifecycle.FAILED, ChildLifecycle.RUNNING),
        (ChildLifecycle.STALE, ChildLifecycle.RUNNING),
    )
    for current, target in invalid_paths:
        with pytest.raises(FanoutCoordinatorError, match="INVALID_LIFECYCLE_TRANSITION"):
            transition_child_lifecycle(current, target)


def test_all_required_join_semantics_explicitly_reject_partial_and_non_success_terminal_states() -> None:
    semantics = JoinSemantics.for_policy("ALL_REQUIRED")

    assert semantics.policy.value == "ALL_REQUIRED"
    assert semantics.acceptable_terminal_states == (CompletionStatus.SUCCEEDED,)
    assert semantics.allow_partial is False
    assert semantics.partial_result_policy == "NOT_READY"
    assert semantics.failure_policy == "BLOCK_PARENT"
    assert semantics.timeout_policy == "BLOCK_PARENT"
    assert semantics.cancellation_policy == "BLOCK_PARENT"
    assert semantics.stale_policy == "BLOCK_PARENT"
    assert semantics.to_dict() == {
        "policy": "ALL_REQUIRED",
        "acceptable_terminal_states": ["SUCCEEDED"],
        "allow_partial": False,
        "partial_result_policy": "NOT_READY",
        "failure_policy": "BLOCK_PARENT",
        "timeout_policy": "BLOCK_PARENT",
        "cancellation_policy": "BLOCK_PARENT",
        "stale_policy": "BLOCK_PARENT",
    }
    with pytest.raises(FanoutCoordinatorError, match="SCHEMA_INVALID"):
        JoinSemantics(
            policy="ALL_REQUIRED",
            acceptable_terminal_states=(CompletionStatus.FAILED,),
        )
    with pytest.raises(FanoutCoordinatorError, match="SCHEMA_INVALID"):
        JoinSemantics(
            policy="ALL_REQUIRED",
            acceptable_terminal_states=(CompletionStatus.SUCCEEDED,),
            partial_result_policy="ACCEPT_PARTIAL",
        )

    children = _children(2)
    for status in (
        CompletionStatus.FAILED,
        CompletionStatus.TIMED_OUT,
        CompletionStatus.CANCELLED,
        CompletionStatus.STALE,
    ):
        coordinator = FanoutCoordinator.from_children(
            children,
            parent=_parent(),
            mode="PARALLEL",
            max_parallel=2,
        ).complete(_completion(children[0], status=status))
        decision = coordinator.join()
        assert decision.status is JoinStatus.BLOCKED
        assert decision.join_semantics == semantics
        assert decision.failed_child_ids == ("child-1",)

    partial = FanoutCoordinator.from_children(
        children,
        parent=_parent(),
        mode="PARALLEL",
        max_parallel=2,
    ).complete(_completion(children[0]))
    partial_decision = partial.join()
    assert partial_decision.status is JoinStatus.NOT_READY
    assert partial_decision.missing_child_ids == ("child-2",)
    assert partial_decision.join_semantics.partial_result_policy == "NOT_READY"


def test_coordinator_exposes_planned_dispatched_and_terminal_child_lifecycle() -> None:
    children = _children(2)
    coordinator = FanoutCoordinator.from_children(
        children,
        parent=_parent(),
        mode="STAGED",
        max_parallel=1,
        stages=(("child-1",), ("child-2",)),
    )

    assert coordinator.lifecycle_state("child-1") is ChildLifecycle.DISPATCHED
    assert coordinator.lifecycle_state("child-2") is ChildLifecycle.PLANNED

    coordinator = coordinator.complete(_completion(children[0]))
    assert coordinator.lifecycle_state("child-1") is ChildLifecycle.SUCCEEDED
    assert coordinator.lifecycle_state("child-2") is ChildLifecycle.DISPATCHED

    with pytest.raises(FanoutCoordinatorError, match="unknown child"):
        coordinator.lifecycle_state("unknown-child")


def test_manifest_materializes_parent_identity_and_exact_child_evidence_refs() -> None:
    plan = FanoutCoordinator.from_children(
        _children(2),
        parent=_parent(),
        mode="PARALLEL",
        max_parallel=2,
    ).plan
    manifest = FanoutManifest.from_plan(plan, attempt_id="attempt-506")

    payload = manifest.to_dict()
    assert payload["protocol"] == "dw.taskcontroller.fanout-manifest/v1"
    assert payload["manifest_version"] == 1
    assert payload["manifest_digest"] == manifest.manifest_digest
    assert payload["parent"] == {
        "run_id": "run-504",
        "node_id": "node-504",
        "plan_version": "plan-504",
        "contract_id": "contract-504",
        "contract_digest": _PARENT_DIGEST,
        "boundary_digest": _parent().boundary.digest(),
        "source_manifest_ref": "manifest-504",
        "source_digest": _SOURCE_DIGEST,
        "standards_profile_ref": "standards.default/v1",
        "standards_profile_digest": _STANDARDS_DIGEST,
        "attempt_id": "attempt-506",
        "lease_generation": None,
    }
    assert [item["child_id"] for item in payload["children"]] == ["child-1", "child-2"]
    assert payload["children"][0]["lens"] == "lens-1"
    assert payload["children"][0]["agent_instance"] == "hermes-mac"
    assert payload["children"][0]["attempt_id"] == "attempt-506:child-1"
    assert payload["children"][0]["status"] == "PLANNED"
    assert payload["children"][0]["timeout_seconds"] == DEFAULT_CHILD_TIMEOUT_SECONDS
    assert payload["children"][0]["result_ref"] is None
    assert payload["children"][0]["result_digest"] is None
    assert "transcript" not in str(payload)
    assert FanoutManifest.from_dict(payload) == manifest


def test_manifest_transition_is_immutable_versioned_and_idempotent() -> None:
    child = _children(1)[0]
    plan = FanoutCoordinator.from_children(
        (child,),
        parent=_parent(),
        mode="PARALLEL",
        max_parallel=1,
    ).plan
    initial = FanoutManifest.from_plan(plan, attempt_id="attempt-506")
    dispatched = initial.record_transition("child-1", ChildLifecycle.DISPATCHED)
    running = dispatched.record_transition("child-1", ChildLifecycle.RUNNING)
    succeeded = running.record_transition(
        "child-1",
        ChildLifecycle.SUCCEEDED,
        result_ref="github://result/child-1/attempt-506",
        result_digest="sha256:" + "9" * 64,
    )

    assert initial.manifest_version == 1
    assert dispatched.manifest_version == 2
    assert running.manifest_version == 3
    assert succeeded.manifest_version == 4
    assert initial.children[0].status is ChildLifecycle.PLANNED
    assert succeeded.children[0].status is ChildLifecycle.SUCCEEDED
    assert succeeded.record_transition(
        "child-1",
        ChildLifecycle.SUCCEEDED,
        result_ref="github://result/child-1/attempt-506",
        result_digest="sha256:" + "9" * 64,
    ) is succeeded
    with pytest.raises(FanoutManifestError, match="IDEMPOTENCY_CONFLICT"):
        succeeded.record_transition(
            "child-1",
            ChildLifecycle.SUCCEEDED,
            result_ref="github://result/child-1/other",
            result_digest="sha256:" + "8" * 64,
        )


def test_manifest_rejects_illegal_skip_transition_and_terminal_without_evidence() -> None:
    plan = FanoutCoordinator.from_children(
        (_children(1)[0],),
        parent=_parent(),
        mode="PARALLEL",
        max_parallel=1,
    ).plan
    manifest = FanoutManifest.from_plan(plan, attempt_id="attempt-506")

    with pytest.raises(FanoutManifestError, match="INVALID_LIFECYCLE_TRANSITION"):
        manifest.record_transition("child-1", ChildLifecycle.SUCCEEDED)
    dispatched = manifest.record_transition("child-1", ChildLifecycle.DISPATCHED)
    running = dispatched.record_transition("child-1", ChildLifecycle.RUNNING)
    with pytest.raises(FanoutManifestError, match="result_ref"):
        running.record_transition("child-1", ChildLifecycle.FAILED)


def test_manifest_join_and_parent_result_binding_require_current_complete_evidence() -> None:
    children = _children(2)
    coordinator = FanoutCoordinator.from_children(
        children,
        parent=_parent(),
        mode="PARALLEL",
        max_parallel=2,
    )
    not_ready = FanoutManifest.from_coordinator(coordinator, attempt_id="attempt-506")
    assert not_ready.join_decision().status is JoinStatus.NOT_READY
    with pytest.raises(FanoutManifestError, match="JOIN_NOT_READY"):
        not_ready.parent_result_binding()

    coordinator = coordinator.complete(_completion(children[0]))
    coordinator = coordinator.complete(_completion(children[1]))
    ready = FanoutManifest.from_coordinator(coordinator, attempt_id="attempt-506")
    decision = ready.join_decision()
    assert decision.status is JoinStatus.READY
    binding = ready.parent_result_binding()
    assert binding["manifest_id"] == ready.manifest_id
    assert binding["manifest_version"] == ready.manifest_version
    assert binding["manifest_digest"] == ready.manifest_digest
    assert binding["input_manifest_digest"] == ready.manifest_digest
    assert binding["consumed_child_ids"] == ["child-1", "child-2"]
    assert len(binding["consumed_evidence"]) == 2
    assert binding["consumed_evidence_digest"].startswith("sha256:")
    assert binding == ready.parent_result_binding()


def test_manifest_preserves_failure_as_blocking_evidence_and_rejects_tampered_digest() -> None:
    children = _children(1)
    coordinator = FanoutCoordinator.from_children(
        children,
        parent=_parent(),
        mode="PARALLEL",
        max_parallel=1,
    ).complete(_completion(children[0], status=CompletionStatus.FAILED))
    blocked = FanoutManifest.from_coordinator(coordinator, attempt_id="attempt-506")
    assert blocked.join_decision().status is JoinStatus.BLOCKED
    assert blocked.join_decision().failed_child_ids == ("child-1",)
    with pytest.raises(FanoutManifestError, match="JOIN_BLOCKED"):
        blocked.parent_result_binding()

    tampered = blocked.to_dict()
    tampered["manifest_digest"] = "sha256:" + "0" * 64
    with pytest.raises(FanoutManifestError, match="DIGEST_MISMATCH"):
        FanoutManifest.from_dict(tampered)
