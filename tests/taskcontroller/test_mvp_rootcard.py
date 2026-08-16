"""WP2 (#49) focused tests — MVP RootCard V1 fidelity + one-root semantics.

Each class maps to a WP2 contract requirement: required visible fields, exact
cost enum, `N/A` token fallback, GWC-gated journey line, an explicit ordered
PlanBlock of 3-5 TaskCards materialized from contracted subtasks, root snapshot
(no thread evidence), CREATE_ROOT/UPDATE_ROOT one-root semantics, the public
contextual action API, and purity (no deferred Full-E2E import, Slack is
projection not authority).
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.mvp import rootcard as rc
from taskcontroller.mvp.protocol_bridge import (
    CONTINUE,
    TERMINAL,
    WAIT_CONTROLLER,
    ContractedSubtask,
)
from taskcontroller.mvp.rootcard import (
    COST_VALUES,
    CREATE_ROOT,
    MAX_TASK_CARDS,
    MIN_TASK_CARDS,
    NON_PUBLIC_ACTIONS,
    PUBLIC_ROOTCARD_ACTIONS,
    ROOT_OPS,
    TOKEN_USAGE_UNKNOWN,
    UPDATE_ROOT,
    PlanBlock,
    RootCard,
    RootOp,
    TaskCard,
    TaskCardStatus,
    render_root_op,
    render_rootcard,
)

ROOTCARD_SOURCE = Path(rc.__file__)


def _contract(subtask_id: str, after_report: str = CONTINUE) -> ContractedSubtask:
    return ContractedSubtask(
        subtask_id=subtask_id,
        objective=f"objective for {subtask_id}",
        allowed_work=(f"work allowed in {subtask_id}",),
        expected_output=(f"artifact of {subtask_id}",),
        report_requirement=("exact evidence in the thread reply",),
        after_report=after_report,
    )


def _contracts(n: int = 4) -> tuple[ContractedSubtask, ...]:
    return tuple(_contract(f"S{i}") for i in range(1, n + 1))


def _plan(n: int = 4, statuses=None) -> PlanBlock:
    return PlanBlock.from_contracts(_contracts(n), statuses=statuses)


def _card(**overrides) -> RootCard:
    base = dict(
        run_id="RUN-47",
        human_owner="Nhat",
        controller="ChatGPT",
        executor="Hermes Cloud",
        plan=_plan(),
        active_subtask_id="S2",
        now="WP2 in_progress",
        next="controller readback",
        last_material_update="WP1 gate validated",
        executor_model="tencent/hy3",
        token_usage=None,
        cost=rc.COST_UNKNOWN,
    )
    base.update(overrides)
    return RootCard(**base)


# ---------------------------------------------------------------- 1
class TestRequiredVisibleFields:
    """WP2-1: every mandated RootCard field is materialized and rendered."""

    REQUIRED = (
        "human_owner",
        "watcher",
        "controller",
        "executor",
        "executor_model",
        "token_usage",
        "cost",
        "active_subtask_id",
        "branch",
        "pr",
        "head_sha",
        "ci_status",
        "risk",
        "now",
        "next",
        "last_material_update",
        "gate_journey",
    )

    def test_all_required_fields_exist_on_the_model(self):
        names = {f.name for f in dataclasses.fields(RootCard)}
        for required in self.REQUIRED:
            assert required in names, required

    def test_rendered_labels_cover_the_human_cockpit(self):
        payload = render_rootcard(
            _card(
                watcher="Controller",
                branch="fix/taskcontroller-mvp-realignment",
                pr="#53",
                head_sha="8638f3cc",
                ci_status="success",
                risk="none",
            )
        )
        labels = [f["label"] for f in payload["fields"]]
        for label in (
            "owner",
            "watcher",
            "controller",
            "executor",
            "model",
            "tokens",
            "cost",
            "active",
            "branch",
            "pr",
            "head",
            "ci",
            "risk",
            "now",
            "next",
            "last material update",
        ):
            assert label in labels, label
        assert payload["kind"] == "ROOTCARD_V1"

    def test_mandatory_text_fields_fail_closed_when_blank(self):
        for name in (
            "run_id",
            "human_owner",
            "controller",
            "executor",
            "now",
            "next",
            "last_material_update",
        ):
            with pytest.raises(TaskControllerValidationError):
                _card(**{name: "  "})

    def test_active_subtask_must_exist_in_the_plan(self):
        with pytest.raises(TaskControllerValidationError):
            _card(active_subtask_id="S99")

    def test_progress_is_derived_from_the_plan(self):
        card = _card(
            plan=_plan(4, statuses={"S1": TaskCardStatus.DONE, "S2": TaskCardStatus.IN_PROGRESS})
        )
        assert card.progress == "1/4"
        active = [f["value"] for f in render_rootcard(card)["fields"] if f["label"] == "active"]
        assert active == ["S2 (1/4)"]


# ---------------------------------------------------------------- 2
class TestCostEnumAndTokenFallback:
    """WP2-2: cost is an exact enum, never inferred; tokens fall back to N/A."""

    def test_cost_enum_is_exactly_three_values(self):
        assert COST_VALUES == ("FREE", "metered", "unknown")

    @pytest.mark.parametrize("cost", COST_VALUES)
    def test_each_legal_cost_is_accepted_and_rendered_verbatim(self, cost):
        payload = render_rootcard(_card(cost=cost))
        assert [f["value"] for f in payload["fields"] if f["label"] == "cost"] == [cost]

    @pytest.mark.parametrize(
        "bad", ("free", "FREE ", "METERED", "Unknown", "paid", "", None, 0)
    )
    def test_inferred_or_aliased_cost_rejected(self, bad):
        with pytest.raises(TaskControllerValidationError):
            _card(cost=bad)

    def test_unknown_token_usage_renders_the_literal_na(self):
        assert TOKEN_USAGE_UNKNOWN == "N/A"
        card = _card(token_usage=None)
        assert card.token_usage_display == "N/A"
        assert [f["value"] for f in render_rootcard(card)["fields"] if f["label"] == "tokens"] == [
            "N/A"
        ]

    def test_exposed_token_usage_renders_the_exact_number(self):
        assert _card(token_usage=0).token_usage_display == "0"
        assert _card(token_usage=12345).token_usage_display == "12345"

    @pytest.mark.parametrize("bad", (-1, "1200", 1.5, True))
    def test_malformed_token_usage_rejected(self, bad):
        with pytest.raises(TaskControllerValidationError):
            _card(token_usage=bad)


# ---------------------------------------------------------------- 3
class TestGwcGatedJourney:
    """WP2-3: journey/gate line appears only when GWC is actually active."""

    def test_no_gate_line_anywhere_when_gwc_inactive(self):
        # neutral caller content so the assertion proves the RENDERER emits no
        # gate/journey line, not merely that the fixture text lacks the word.
        payload = render_rootcard(
            _card(gwc_active=False, last_material_update="WP1 validated")
        )
        labels = [f["label"] for f in payload["fields"]]
        assert "journey" not in labels
        assert "gate" not in labels
        flat = repr(payload).lower()
        assert "journey" not in flat and "gate" not in flat

    def test_gate_journey_rejected_when_gwc_inactive(self):
        with pytest.raises(TaskControllerValidationError):
            _card(gwc_active=False, gate_journey="G0 → G4")

    def test_gate_journey_rendered_only_with_gwc_active(self):
        payload = render_rootcard(_card(gwc_active=True, gate_journey="G0 → G4 (current G2)"))
        assert [f["value"] for f in payload["fields"] if f["label"] == "journey"] == [
            "G0 → G4 (current G2)"
        ]

    def test_gwc_active_without_a_journey_is_still_valid(self):
        payload = render_rootcard(_card(gwc_active=True))
        assert "journey" not in [f["label"] for f in payload["fields"]]


# ---------------------------------------------------------------- 4
class TestExplicitPlanBlockAndTaskCards:
    """WP2-4: a real ordered PlanBlock of 3-5 typed TaskCards, not a label."""

    def test_bounds_are_the_mvp_three_to_five(self):
        assert (MIN_TASK_CARDS, MAX_TASK_CARDS) == (3, 5)

    @pytest.mark.parametrize("n", (3, 4, 5))
    def test_legal_plan_sizes_accepted(self, n):
        assert len(_plan(n).cards) == n

    @pytest.mark.parametrize("n", (0, 1, 2, 6, 7))
    def test_illegal_plan_sizes_rejected(self, n):
        with pytest.raises(TaskControllerValidationError):
            _plan(n)

    def test_cards_are_typed_task_cards_derived_from_contracts(self):
        plan = _plan(3)
        assert all(isinstance(c, TaskCard) for c in plan.cards)
        for contract, card in zip(_contracts(3), plan.cards):
            assert card.subtask_id == contract.subtask_id
            assert card.objective == contract.objective
            assert card.after_report == contract.after_report

    def test_plan_order_is_preserved_exactly(self):
        assert _plan(5).ordered_ids == ("S1", "S2", "S3", "S4", "S5")

    def test_plan_block_payload_is_an_explicit_typed_block(self):
        payload = render_rootcard(_card())["plan_block"]
        assert payload["type"] == "plan_block"
        assert [c["type"] for c in payload["task_cards"]] == ["task_card"] * 4
        assert [c["position"] for c in payload["task_cards"]] == [1, 2, 3, 4]
        assert [c["subtask_id"] for c in payload["task_cards"]] == ["S1", "S2", "S3", "S4"]
        for c in payload["task_cards"]:
            assert c["objective"] and c["status"] in TaskCardStatus.ALL and c["emoji"]

    def test_duplicate_subtask_ids_rejected(self):
        dup = (_contract("S1"), _contract("S1"), _contract("S2"))
        with pytest.raises(TaskControllerValidationError):
            PlanBlock.from_contracts(dup)

    def test_non_taskcard_and_non_sequence_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            PlanBlock(cards=("S1", "S2", "S3"))
        with pytest.raises(TaskControllerValidationError):
            PlanBlock.from_contracts("S1S2S3")
        with pytest.raises(TaskControllerValidationError):
            TaskCard.from_contract({"subtask_id": "S1"})

    def test_card_status_and_after_report_vocabulary_is_closed(self):
        with pytest.raises(TaskControllerValidationError):
            TaskCard.from_contract(_contract("S1"), status="done")
        with pytest.raises(TaskControllerValidationError):
            TaskCard(
                subtask_id="S1",
                objective="o",
                status=TaskCardStatus.DONE,
                after_report="INTERCEPT",
            )

    def test_progress_counts_only_completed_cards(self):
        plan = _plan(
            5,
            statuses={
                "S1": TaskCardStatus.DONE,
                "S2": TaskCardStatus.DONE,
                "S3": TaskCardStatus.IN_PROGRESS,
                "S4": TaskCardStatus.BLOCKED,
                "S5": TaskCardStatus.FAILED,
            },
        )
        assert plan.progress == "2/5" and plan.completed_count == 2

    def test_plan_and_cards_are_frozen(self):
        plan = _plan(3)
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.cards = ()  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.cards[0].status = TaskCardStatus.DONE  # type: ignore[misc]

    def test_terminal_and_wait_boundaries_survive_into_the_cards(self):
        plan = PlanBlock.from_contracts(
            (_contract("S1"), _contract("S2", WAIT_CONTROLLER), _contract("S3", TERMINAL))
        )
        assert [c.after_report for c in plan.cards] == [CONTINUE, WAIT_CONTROLLER, TERMINAL]


# ---------------------------------------------------------------- 5
class TestRootIsSnapshotNotEvidenceLog:
    """WP2-5: detailed milestone evidence stays in the thread, not the root."""

    def test_rootcard_model_carries_no_evidence_field(self):
        names = {f.name for f in dataclasses.fields(RootCard)}
        assert not (names & {"evidence", "completed", "finding_risk", "report", "thread"})

    def test_rendered_payload_has_no_evidence_key(self):
        payload = render_rootcard(_card())
        flat = repr(payload).lower()
        assert "evidence" not in flat
        assert set(payload) == {
            "kind",
            "run_id",
            "header",
            "fields",
            "plan_block",
            "actions",
            "authority_granted",
        }


# ---------------------------------------------------------------- 6
class TestOneRootSemantics:
    """WP2-6: CREATE_ROOT only without a binding; rotation never adds a root."""

    def test_root_ops_are_exactly_two(self):
        assert ROOT_OPS == ("CREATE_ROOT", "UPDATE_ROOT")

    def test_no_binding_creates_the_single_root(self):
        op = render_root_op(_card(), channel="C1", root=None)
        assert op.op == CREATE_ROOT and op.root is None

    def test_existing_binding_always_updates_in_place(self):
        op = render_root_op(_card(), channel="C1", root="R1")
        assert op.op == UPDATE_ROOT and op.root == "R1"

    def test_metadata_rotation_never_creates_a_second_root(self):
        rotations = [
            _card(executor_model="model-a"),
            _card(executor_model="model-b"),
            _card(executor="Hermes Cloud 2", cost="metered"),
            _card(token_usage=999),
            _card(ci_status="failure", risk="excluded lock lane"),
        ]
        ops = [render_root_op(c, channel="C1", root="R1") for c in rotations]
        assert {o.op for o in ops} == {UPDATE_ROOT}
        assert {o.root for o in ops} == {"R1"}
        assert not any(o.op == CREATE_ROOT for o in ops)

    def test_root_op_shape_is_fail_closed(self):
        with pytest.raises(TaskControllerValidationError):
            RootOp(op="REPLY_THREAD", run_id="RUN-47", channel="C1", root="R1")
        with pytest.raises(TaskControllerValidationError):
            RootOp(op=CREATE_ROOT, run_id="RUN-47", channel="C1", root="R1")
        with pytest.raises(TaskControllerValidationError):
            RootOp(op=UPDATE_ROOT, run_id="RUN-47", channel="C1", root=None)
        with pytest.raises(TaskControllerValidationError):
            RootOp(op=UPDATE_ROOT, run_id="RUN-47", channel="", root="R1")

    def test_update_payload_is_the_full_snapshot_each_time(self):
        op = render_root_op(_card(), channel="C1", root="R1")
        assert op.payload["kind"] == "ROOTCARD_V1"
        assert op.payload["plan_block"]["task_cards"]


# ---------------------------------------------------------------- 7
class TestPublicContextualActionApi:
    """WP2-7: only PAUSE/STOP/APPROVE/MERGE; STOP semantics NOT implemented."""

    def test_public_action_api_is_exactly_the_four(self):
        assert PUBLIC_ROOTCARD_ACTIONS == ("PAUSE", "STOP", "APPROVE", "MERGE")

    def test_resume_cancel_replan_never_public(self):
        assert NON_PUBLIC_ACTIONS == ("RESUME", "CANCEL", "REPLAN")
        cards = [
            _card(),
            _card(paused=True),
            _card(authority_boundary=True),
            _card(authority_boundary=True, merge_ready=True, pr="#53", head_sha="8638f3cc"),
        ]
        for card in cards:
            actions = card.contextual_actions()
            assert not (set(actions) & set(NON_PUBLIC_ACTIONS))
            assert set(actions) <= set(PUBLIC_ROOTCARD_ACTIONS)
            assert render_rootcard(card)["actions"] == list(actions)

    def test_default_affordances_are_pause_and_stop_only(self):
        assert _card().contextual_actions() == ("PAUSE", "STOP")

    def test_pause_hidden_when_already_paused_stop_always_present(self):
        assert _card(paused=True).contextual_actions() == ("STOP",)

    def test_approve_only_at_an_authority_boundary(self):
        assert "APPROVE" not in _card().contextual_actions()
        assert "APPROVE" in _card(authority_boundary=True).contextual_actions()

    def test_merge_requires_exact_bound_pr_and_head(self):
        with pytest.raises(TaskControllerValidationError):
            _card(merge_ready=True)
        with pytest.raises(TaskControllerValidationError):
            _card(merge_ready=True, pr="#53")
        card = _card(merge_ready=True, pr="#53", head_sha="8638f3cc")
        assert "MERGE" in card.contextual_actions()

    def test_actions_keep_the_exact_mvp_api_order(self):
        card = _card(
            authority_boundary=True, merge_ready=True, pr="#53", head_sha="8638f3cc"
        )
        assert card.contextual_actions() == ("PAUSE", "STOP", "APPROVE", "MERGE")

    def test_stop_semantics_are_not_implemented_in_wp2(self):
        """WP2 renders the STOP affordance only; #50 owns the semantics."""
        source = ROOTCARD_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        funcs = {
            n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for forbidden in ("stop", "apply_stop", "handle_stop", "do_stop", "stop_run"):
            assert forbidden not in funcs
        assert "STOP" in _card().contextual_actions()


# ---------------------------------------------------------------- 8
class TestProjectionNotAuthorityAndPurity:
    """WP2-8: Slack stays projection; no deferred Full-E2E import; pure."""

    def test_rendering_an_authority_affordance_grants_no_authority(self):
        card = _card(
            authority_boundary=True, merge_ready=True, pr="#53", head_sha="8638f3cc"
        )
        payload = render_rootcard(card)
        assert payload["authority_granted"] is False
        assert "APPROVE" in payload["actions"] and "MERGE" in payload["actions"]

    def test_no_deferred_full_e2e_import(self):
        tree = ast.parse(ROOTCARD_SOURCE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        forbidden = (
            "taskcontroller.runtime",
            "taskcontroller.packs",
            "taskcontroller.projections",
            "taskcontroller.routing",
            "taskcontroller.execution",
            "taskcontroller.controlplane",
            "slack_sdk",
            "requests",
            "httpx",
            "socket",
            "subprocess",
            "time",
            "datetime",
            "random",
        )
        for mod in imported:
            assert not mod.startswith(forbidden), mod

    def test_no_wall_clock_or_polling_loop_in_the_module(self):
        source = ROOTCARD_SOURCE.read_text(encoding="utf-8")
        for banned in ("time.sleep", "datetime.now", "utcnow", "while True", "random."):
            assert banned not in source, banned

    def test_rendering_is_deterministic_and_non_mutating(self):
        card = _card(watcher="Controller", branch="b", pr="#53", head_sha="abc", ci_status="ok")
        before = card.to_dict()
        first = render_rootcard(card)
        renders = [render_rootcard(card) for _ in range(10)]
        assert all(r == first for r in renders)
        assert card.to_dict() == before

    def test_rootcard_is_frozen(self):
        card = _card()
        with pytest.raises(dataclasses.FrozenInstanceError):
            card.cost = "FREE"  # type: ignore[misc]

    def test_renderers_fail_closed_on_wrong_types(self):
        with pytest.raises(TaskControllerValidationError):
            render_rootcard({"run_id": "RUN-47"})
        with pytest.raises(TaskControllerValidationError):
            _card(plan=[_contract("S1")])
