"""M2: W2 dispatch() fail-closed plan binding + durable plan store.

Fixes the W1-W7 review BLOCKER: ``ExecutionFabric.dispatch()`` accepted
``context=None`` and would route a semantic command to the adapter without
any RuntimePlan binding — the invariant "no semantic action without
runtime_plan_ref / runtime_plan_digest / step_id" was bypassed at the public
entrypoint. M2 makes semantic dispatch fail-closed and wires a durable plan
store (FilePlanStore) instead of only the in-memory store.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.execution.fabric import ExecutionFabric
from taskcontroller.execution.registry import AdapterRegistry
from taskcontroller.runtime.lease import LeaseManager
from taskcontroller.runtime.materializer import StepMaterializer
from taskcontroller.domain.runtime_plan import (
    FilePlanStore,
    PlanEdge,
    RuntimePlan,
    RuntimePlanStep,
)
from taskcontroller.execution.ports import DispatchAck


def _make_plan() -> RuntimePlan:
    return RuntimePlan(
        runtime_plan_ref="plan.m2/r1",
        revision="rev-1",
        steps={
            "inspect": RuntimePlanStep(
                step_id="inspect",
                semantic_action="read",
                allowed_inputs=("target",),
                allowed_actions=("read", "search"),
                evidence_refs=("inspect.evidence",),
                edges={"found": PlanEdge(outcome="found", target="report", kind="continue")},
            ),
            "report": RuntimePlanStep(
                step_id="report",
                semantic_action="write",
                allowed_inputs=("report",),
                allowed_actions=("write",),
                evidence_refs=("report.evidence",),
                edges={"done": PlanEdge(outcome="done", target="terminal", kind="terminal")},
            ),
        },
    )


def _cursor():
    from taskcontroller.domain.runtime_plan import RunCursor

    plan = _make_plan()
    return RunCursor(
        run_id="run-m2",
        runtime_plan_ref=plan.runtime_plan_ref,
        runtime_plan_digest=plan.runtime_plan_digest,
        plan_revision=plan.revision,
        current_step_id="inspect",
    )


@pytest.fixture
def fabric():
    from taskcontroller.execution.registry import build_registry
    from taskcontroller.runtime.runtime_state import RuntimeLeaseState, RuntimeSnapshotMeta, VersionedRunState
    from taskcontroller.domain.enums import LeaseStatus, NodeStatus, RunStatus
    from taskcontroller.domain.models import TeamRunState
    from taskcontroller.domain.values import NodeState
    from taskcontroller.runtime.store import InMemoryStateStore

    run = TeamRunState(
        run_id="run-m2",
        status=RunStatus.RUNNING.value,
        nodes={"node-1": NodeState(status=NodeStatus.RUNNING.value, contract_ref="ctr.1", current_attempt=1, lease_ref=None, artifact_refs=[])},
        active_attempts=[],
        active_leases=[],
    )
    meta = RuntimeSnapshotMeta(attempt_registry={}, leases=RuntimeLeaseState(leases={}), stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=0)
    store = InMemoryStateStore()
    store.put_run(VersionedRunState(state=run, version=1, meta=meta), -1)
    return ExecutionFabric(build_registry([]), LeaseManager(store))


def test_public_dispatch_requires_semantic_binding_when_requested(fabric):
    """dispatch() must fail-closed BEFORE provider dispatch when semantic
    binding is required but context is None (the W2 bypass)."""
    with pytest.raises(TaskControllerValidationError, match="runtime plan binding"):
        fabric.dispatch(
            request=None,  # noqa: not reached — binding check happens first
            receipt=None,
            provider=None,
            run_id="run-m2",
            node_id="node-1",
            command_id="cmd-m2",
            now="2026-09-01T00:00:00+00:00",
            require_plan_binding=True,
        )


def test_public_dispatch_rejects_context_without_plan_identity(fabric):
    """Even a supplied context is only accepted when it carries the exact
    runtime_plan_ref/digest/step_id identity (StepContext type)."""
    with pytest.raises(TaskControllerValidationError, match="runtime plan binding"):
        fabric.dispatch(
            request=None,
            receipt=None,
            provider=None,
            run_id="run-m2",
            node_id="node-1",
            command_id="cmd-m2b",
            now="2026-09-01T00:00:00+00:00",
            context={"not": "a StepContext"},  # type: ignore[arg-type]
        )


def test_materializer_reads_plan_from_durable_file_store(tmp_path: Path):
    """The W2 durable-plan gap: StepMaterializer must reconstruct the exact
    current step from a FilePlanStore (survives process restart), not only an
    in-memory store."""
    plan = _make_plan()
    store = FilePlanStore(tmp_path)
    store.put(plan)

    materializer = StepMaterializer(store)
    ctx = materializer.materialize(_cursor(), evidence_refs=("inspect.evidence",))

    assert ctx.runtime_plan_ref == plan.runtime_plan_ref
    assert ctx.runtime_plan_digest == plan.runtime_plan_digest
    assert ctx.step_id == "inspect"
    assert ctx.semantic_action == "read"
    assert ctx.allowed_actions == ("read", "search")
    assert ctx.evidence_refs == ("inspect.evidence",)

    # durability: a NEW store instance over the same root still reads it
    store2 = FilePlanStore(tmp_path)
    ctx2 = StepMaterializer(store2).materialize(_cursor(), evidence_refs=("inspect.evidence",))
    assert ctx2.runtime_plan_digest == plan.runtime_plan_digest
    assert ctx2.step_id == "inspect"


def test_durable_store_rejects_digest_drift(tmp_path: Path):
    """FilePlanStore must reject a plan whose content drifted from the stored
    one under the same ref (plan immutability across restart)."""
    store = FilePlanStore(tmp_path)
    store.put(_make_plan())
    drifted = RuntimePlan(
        runtime_plan_ref="plan.m2/r1",
        revision="rev-drifted",
        steps={
            "inspect": RuntimePlanStep(
                step_id="inspect",
                semantic_action="read",
                allowed_inputs=("target",),
                allowed_actions=("read", "search"),
                evidence_refs=("inspect.evidence",),
                edges={"found": PlanEdge(outcome="found", target="report", kind="continue")},
            ),
            "report": RuntimePlanStep(
                step_id="report",
                semantic_action="write",
                allowed_inputs=("report",),
                allowed_actions=("write",),
                evidence_refs=("report.evidence",),
                edges={"done": PlanEdge(outcome="done", target="terminal", kind="terminal")},
            ),
        },
    )
    with pytest.raises(TaskControllerValidationError, match="already exists"):
        store.put(drifted)
