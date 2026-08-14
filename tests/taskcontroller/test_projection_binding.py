"""WP6 S1 focused tests: generic projection port + binding registry (NO GWC)."""

from __future__ import annotations

import copy

import pytest

from taskcontroller.projections.binding import (
    Binding,
    BindingRegistry,
    DuplicateRootError,
)
from taskcontroller.projections.types import (
    ProjectionNode,
    ProjectionOp,
    RunProjectionView,
    TaskStatus,
)


class TestBindingRegistry:
    def test_first_bind_creates(self):
        reg = BindingRegistry()
        b = reg.bind("run.1#slack", "slack", "root.1")
        assert isinstance(b, Binding)
        assert reg.has("run.1#slack")
        assert reg.lookup("run.1#slack").root == "root.1"

    def test_identical_rebind_idempotent(self):
        reg = BindingRegistry()
        b1 = reg.bind("run.1#slack", "slack", "root.1")
        b2 = reg.bind("run.1#slack", "slack", "root.1")
        assert b1 is b2
        assert len(reg.snapshot()) == 1

    def test_different_root_fails_closed_zero_mutation(self):
        reg = BindingRegistry()
        reg.bind("run.1#slack", "slack", "root.1")
        with pytest.raises(DuplicateRootError):
            reg.bind("run.1#slack", "slack", "root.2")
        # no mutation: still exactly one binding, still root.1
        assert reg.lookup("run.1#slack").root == "root.1"
        assert len(reg.snapshot()) == 1

    def test_lookup_is_pure_no_side_effect(self):
        reg = BindingRegistry()
        reg.bind("run.1#slack", "slack", "root.1")
        before = reg.snapshot()
        b = reg.lookup("run.1#slack")
        # the returned binding is an immutable copy; registry unaffected
        assert b is not None
        assert reg.lookup("run.1#slack").root == "root.1"
        assert reg.snapshot() == before

    def test_metadata_update_does_not_change_identity(self):
        reg = BindingRegistry()
        reg.bind("run.1#slack", "slack", "root.1", session_id="s1")
        reg.update_metadata("run.1#slack", model="gpt", executor="exec.a")
        b = reg.lookup("run.1#slack")
        assert b.root == "root.1"  # identity unchanged
        assert b.model == "gpt" and b.session_id == "s1"

    def test_snapshot_deterministic_ordering(self):
        reg = BindingRegistry()
        reg.bind("run.2#slack", "slack", "root.2")
        reg.bind("run.1#slack", "slack", "root.1")
        keys = list(reg.snapshot().keys())
        assert keys == ["run.1#slack", "run.2#slack"]


class TestProjectionTypes:
    def test_task_status_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETE.value == "complete"
        assert TaskStatus.ERROR.value == "error"

    def test_run_projection_view_immutable(self):
        view = RunProjectionView(
            run_id="run.1", run_status="RUNNING", version=3, plan_version="p1",
            journal_position=0, is_terminal=False, legal_affordances=("PAUSE",),
            nodes=(ProjectionNode("n1", TaskStatus.IN_PROGRESS, "node1"),),
        )
        d = view.to_dict()
        d["run_status"] = "HACKED"
        assert view.run_status == "RUNNING"
        # copy does not leak
        assert view.to_dict()["run_status"] == "RUNNING"

    def test_projection_op_no_authority_by_default(self):
        op = ProjectionOp("UPDATE_ROOT", "run.1#slack", "slack", root="root.1")
        assert op.authority_required is False
