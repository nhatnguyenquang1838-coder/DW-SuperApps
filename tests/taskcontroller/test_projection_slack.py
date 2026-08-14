"""WP6 S2 focused tests: Slack live-root renderer (NO GWC, NO transport)."""

from __future__ import annotations

from taskcontroller.controlplane.projection import RunProjection
from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.domain.models import TeamRunState
from taskcontroller.domain.values import NodeState
from taskcontroller.projections.binding import Binding, BindingRegistry
from taskcontroller.projections.domain import build_view
from taskcontroller.projections.slack_renderer import (
    render_root_blocks,
    render_root_op,
    render_thread_op,
)
from taskcontroller.projections.types import TaskStatus
from taskcontroller.runtime.runtime_state import (
    RuntimeLeaseState,
    RuntimeSnapshotMeta,
    VersionedRunState,
)
from taskcontroller.runtime.store import InMemoryStateStore


def _projection(status=RunStatus.RUNNING.value, nodes=None, version=4):
    nodes = nodes or {
        "n1": NodeState(status=NodeStatus.RUNNING.value, contract_ref="c1", current_attempt=1, lease_ref="l1", artifact_refs=[]),
        "n2": NodeState(status=NodeStatus.DONE.value, contract_ref="c2", current_attempt=1, lease_ref=None, artifact_refs=[]),
        "n3": NodeState(status=NodeStatus.PENDING.value, contract_ref="c3", current_attempt=1, lease_ref=None, artifact_refs=[]),
    }
    state = TeamRunState(
        run_id="run.1", status=status, nodes=nodes,
        active_attempts=["att.1"], active_leases=["l1"], plan_version="p1",
    )
    meta = RuntimeSnapshotMeta(
        attempt_registry={}, leases=RuntimeLeaseState(leases={}),
        stream_watermarks={}, event_cursor=None, dedupe_fingerprints={}, journal_position=2,
    )
    return RunProjection.from_versioned(VersionedRunState(state=state, version=version, meta=meta))


class TestRenderRoot:
    def test_update_root_for_existing_binding(self):
        proj = _projection()
        view = build_view(proj, session_id="s1", model="gpt", executor="e1", token_usage=120)
        binding = Binding(binding_key="run.1#slack", channel="slack", root="root.1")
        op = render_root_op(view, "run.1#slack", "slack", binding)
        assert op.op == "UPDATE_ROOT"
        assert op.root == "root.1"
        # payload contains header + task cards
        blocks = op.payload["blocks"]
        assert blocks[0]["type"] == "header"
        # DONE node maps to complete, RUNNING to in_progress
        texts = " ".join(str(b) for b in blocks)
        assert "complete" in texts and "in_progress" in texts

    def test_create_root_only_when_no_binding(self):
        proj = _projection()
        view = build_view(proj)
        op = render_root_op(view, "run.1#slack", "slack", None)
        assert op.op == "CREATE_ROOT"

    def test_root_blocks_includes_supplied_metadata_only(self):
        proj = _projection()
        # no metadata supplied => no session/model/token lines invented
        view = build_view(proj)
        blocks = render_root_blocks(view, None)
        joined = " ".join(str(b) for b in blocks["blocks"])
        assert "session" not in joined
        assert "model" not in joined
        assert "tokens" not in joined
        # with metadata => present
        view2 = build_view(proj, session_id="s9", model="gpt-x", token_usage=7)
        blocks2 = render_root_blocks(view2, None)
        joined2 = " ".join(str(b) for b in blocks2["blocks"])
        assert "s9" in joined2 and "gpt-x" in joined2 and "7" in joined2

    def test_rotation_renders_update_not_create(self):
        proj = _projection()
        view = build_view(proj, session_id="s2", executor="e2")
        binding = Binding(binding_key="run.1#slack", channel="slack", root="root.1",
                          session_id="s1", executor="e1")
        op = render_root_op(view, "run.1#slack", "slack", binding)
        # session rotation updates the SAME root; never a new root
        assert op.op == "UPDATE_ROOT"
        assert op.root == "root.1"


class TestRenderThread:
    def test_thread_reply_is_reply_not_root(self):
        binding = Binding(binding_key="run.1#slack", channel="slack", root="root.1")
        op = render_thread_op("run.1#slack", "slack", binding, "SESSION_ROTATED",
                              "session rotated s1 -> s2")
        assert op.op == "REPLY_THREAD"
        assert op.root == "root.1"

    def test_thread_authority_action_marker(self):
        binding = Binding(binding_key="run.1#slack", channel="slack", root="root.1")
        op = render_thread_op("run.1#slack", "slack", binding, "AUTHORITY_REQUIRED",
                              "APPROVE needs external authority", authority_required=True)
        assert op.op == "REPLY_THREAD"
        assert op.authority_required is True
