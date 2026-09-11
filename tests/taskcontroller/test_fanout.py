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
    CompletionStatus,
    FanoutCoordinator,
    FanoutMode,
    JoinStatus,
    NormalizedJoinInput,
    child_completion,
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
