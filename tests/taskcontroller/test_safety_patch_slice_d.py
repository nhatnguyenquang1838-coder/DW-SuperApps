from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from taskcontroller.domain.runtime_plan import FilePlanStore, PlanEdge, RunCursor, RuntimePlan, RuntimePlanStep
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.runtime.closed_loop_runtime_executor import (
    FileRuntimeExecutionStateStore,
    RuntimeExecutionState,
)


def _plan(revision: str) -> RuntimePlan:
    return RuntimePlan(
        runtime_plan_ref="plan-race",
        revision=revision,
        steps={
            "inspect": RuntimePlanStep(
                step_id="inspect",
                semantic_action="read",
                terminal=True,
                allowed_actions=("read",),
                edges={},
            )
        },
    )


def test_file_plan_store_concurrent_revision_put_is_immutable(tmp_path: Path):
    plans = (_plan("rev-a"), _plan("rev-b"))

    def put(plan: RuntimePlan) -> str:
        try:
            FilePlanStore(tmp_path).put(plan)
            return "ok"
        except TaskControllerValidationError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(put, plans))

    assert sorted(results) == ["conflict", "ok"]
    persisted = RuntimePlan.from_dict(json.loads((tmp_path / "plan-race.json").read_text()))
    assert persisted.revision in {"rev-a", "rev-b"}


def test_runtime_state_store_concurrent_same_run_writes_are_atomic(tmp_path: Path):
    plan = _plan("rev-state")
    cursor = RunCursor(
        run_id="run-state",
        runtime_plan_ref=plan.runtime_plan_ref,
        runtime_plan_digest=plan.runtime_plan_digest,
        plan_revision=plan.revision,
        current_step_id="inspect",
    )
    states = tuple(
        RuntimeExecutionState(
            run_id="run-state",
            runtime_plan_ref=plan.runtime_plan_ref,
            runtime_plan_digest=plan.runtime_plan_digest,
            plan_revision=plan.revision,
            cursor=cursor,
            sequence=index,
        )
        for index in range(8)
    )

    def put(state: RuntimeExecutionState) -> None:
        FileRuntimeExecutionStateStore(tmp_path).put(state)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(put, states))

    restored = FileRuntimeExecutionStateStore(tmp_path).load("run-state")
    assert restored is not None
    assert restored.run_id == "run-state"
    assert restored.sequence in range(8)
