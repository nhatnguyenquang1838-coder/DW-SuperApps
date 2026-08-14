"""WP5 (#52) focused tests — MVP pilot adapter GPT->Slack->Hermes->WP4 loop.

Deterministic fake Slack/Hermes clients only: the MVP CI path never touches a
network. Proves: one-root, ordered 3-5 subtasks with single dispatch, valid
Block Kit plan/task_card schema + exact status mapping, CONTINUE/WAIT_CONTROLLER
/INTERCEPT/TERMINAL boundaries, material observation updating the SAME RootCard
with real values, malformed report fail-closed, and that deferred Full-E2E core
modules are not imported/activated.
"""

import json

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.mvp import pilot as pilot_module
from taskcontroller.mvp.monitoring import (
    CONTINUE,
    TERMINAL,
    WAIT_CONTROLLER,
    MalformedReportError,
    ThreadReply,
    REASON_BOUNDARY,
    REASON_MAX_POLLS,
)
from taskcontroller.mvp.pilot import (
    AdvancedModeRequired,
    HermesExecutorClient,
    SlackTransport,
    MvpPilot,
    MvpPilotConfig,
    parse_hermes_reply,
    translate_rootcard_to_blocks,
    validate_slack_blocks,
)
from taskcontroller.mvp.protocol_bridge import (
    CONTRACTED_AFTER_VALUES,
    ContractedSubtask,
    ExecutorReport,
)
from taskcontroller.mvp.rootcard import RootCard, TaskCard, TaskCardStatus


# --------------------------------------------------------------------------- fakes
class FakeSlack(SlackTransport):
    def __init__(self):
        self.creates = 0
        self.updates = 0
        self.replies = []
        self.root_ts = "100.0"
        self._store = {}

    def create_root(self, channel, blocks):
        self.creates += 1
        validate_slack_blocks(blocks)
        return self.root_ts

    def update_root(self, channel, root_ts, blocks):
        self.updates += 1
        validate_slack_blocks(blocks)

    def post_thread_reply(self, channel, root_ts, text):
        ts = str(float(root_ts) + 0.1 + len(self.replies) * 0.001)
        self.replies.append(ts)
        self._store.setdefault(root_ts, []).append(ThreadReply(ts, json.loads(text)))
        return ts

    def read_thread_replies(self, channel, root_ts, since_ts):
        items = self._store.get(root_ts, [])
        if since_ts is None:
            return list(items)
        return [r for r in items if float(r.ts) > float(since_ts)]


class FakeHermes(HermesExecutorClient):
    def __init__(self, replies):
        self.replies = replies

    def dispatch(self, subtask):
        return self.replies[subtask.subtask_id]


def _contract(subtask_id, after=CONTINUE, objective="objective for "):
    return ContractedSubtask(
        subtask_id=subtask_id,
        objective=objective + subtask_id,
        allowed_work=("do the work",),
        expected_output=("the output",),
        report_requirement=("report it",),
        after_report=after,
    )


def _report(subtask_id, status="RUNNING", completed=None, evidence=None,
            finding_risk=None, next_action="await controller", after=CONTINUE):
    return ExecutorReport(
        subtask_id=subtask_id,
        status=status,
        completed=tuple(completed if completed is not None else ["unit finished"]),
        evidence=tuple(evidence or ["exact evidence"]),
        finding_risk=tuple(finding_risk or []),
        next_action=next_action,
        after=after,
    )


def _pilot_config(slack, hermes, contracts, **kw):
    return MvpPilotConfig(
        run_id="RUN-47",
        channel="C0BJSPXN7UN",
        human_owner="Nhat",
        controller="ChatGPT",
        executor="Hermes Cloud",
        contracts=tuple(contracts),
        slack=slack,
        hermes=hermes,
        **kw,
    )


def _build_pilot(contracts, slack, hermes, **kw):
    return MvpPilot(config=_pilot_config(slack, hermes, contracts, **kw))


def _card_fields(card):
    return {k: getattr(card, k) for k in (
        "run_id", "human_owner", "controller", "executor", "active_subtask_id",
        "now", "next", "last_material_update", "executor_model", "token_usage",
        "cost", "watcher", "branch", "pr", "head_sha", "ci_status", "risk",
        "gwc_active", "gate_journey", "authority_boundary", "merge_ready",
        "paused") if hasattr(card, k)}


def _replaced_card(card, new_status, subtask_id="S1"):
    updated_cards = tuple(
        c if c.subtask_id != subtask_id else c.__class__(
            subtask_id=c.subtask_id, objective=c.objective,
            status=new_status, after_report=c.after_report,
        )
        for c in card.plan.cards
    )
    return card.__class__(**{**_card_fields(card), "plan": card.plan.__class__(updated_cards)})




# --------------------------------------------------------------------------- one root
class TestOneRootInvariant:
    def test_ensure_root_creates_exactly_once(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, FakeHermes({}))
        assert pilot.ensure_root() == "100.0"
        pilot.ensure_root()
        pilot.ensure_root()
        assert slack.creates == 1
        assert pilot.ensure_root() == "100.0"

    def test_repeat_update_rotation_never_spawns_second_root(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, FakeHermes({}))
        root = pilot.ensure_root()
        pilot.config = _pilot_config(
            slack, FakeHermes({}), contracts, executor_model="new-model"
        )
        same = pilot.ensure_root()
        assert same == root == "100.0"
        assert slack.creates == 1


# --------------------------------------------------------------------------- ordered dispatch
class TestOrderedSubtaskDispatch:
    def test_3_to_5_contracted_subtasks_maintain_order(self):
        slack = FakeSlack()
        contracts = [_contract(f"S{i}") for i in (1, 2, 3, 4, 5)]
        pilot = _build_pilot(contracts, slack, FakeHermes({}))
        plan_ids = [c.subtask_id for c in pilot._build_initial_card().plan.cards]
        assert plan_ids == ["S1", "S2", "S3", "S4", "S5"]

    def test_only_selected_current_subtask_is_dispatched(self):
        slack = FakeSlack()
        dispatched = []

        class TrackingHermes(HermesExecutorClient):
            def dispatch(self, subtask):
                dispatched.append(subtask.subtask_id)
                return json.dumps(_report(subtask.subtask_id).to_dict())

        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        cfg = _pilot_config(slack, TrackingHermes(), contracts, active_subtask_id="S2")
        pilot = MvpPilot(config=cfg)
        pilot.dispatch_current()
        assert dispatched == ["S2"]

    def test_uncontracted_active_subtask_is_rejected(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        cfg = _pilot_config(slack, FakeHermes({}), contracts, active_subtask_id="S9")
        pilot = MvpPilot(config=cfg)
        with pytest.raises(TaskControllerValidationError):
            pilot.dispatch_current()


# --------------------------------------------------------------------------- block kit schema
class TestSlackBlockKitSchema:
    def test_translated_payload_is_valid_plan_task_card(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, FakeHermes({}))
        blocks = translate_rootcard_to_blocks(pilot._build_initial_card())
        validate_slack_blocks(blocks)
        plan = next(b for b in blocks if b["type"] == "plan")
        assert plan["title"].startswith("Plan —")
        assert len(plan["tasks"]) == 3
        for task in plan["tasks"]:
            assert task["type"] == "task_card"
            assert task["status"] in ("pending", "in_progress", "complete", "error")
            assert "task_id" in task and "title" in task

    def test_exact_status_mapping(self):
        mapping = {
            TaskCardStatus.PENDING: "pending",
            TaskCardStatus.IN_PROGRESS: "in_progress",
            TaskCardStatus.DONE: "complete",
            TaskCardStatus.BLOCKED: "error",
            TaskCardStatus.FAILED: "error",
        }
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, FakeHermes({}))
        card = pilot._build_initial_card()
        for status, expected in mapping.items():
            replaced = _replaced_card(card, status)
            blocks = translate_rootcard_to_blocks(replaced)
            plan = next(b for b in blocks if b["type"] == "plan")
            assert plan["tasks"][0]["status"] == expected

    def test_blocked_vs_failed_distinction_preserved_in_details(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, FakeHermes({}))
        card = pilot._build_initial_card()
        for status in (TaskCardStatus.BLOCKED, TaskCardStatus.FAILED):
            replaced = _replaced_card(card, status)
            blocks = translate_rootcard_to_blocks(replaced)
            plan = next(b for b in blocks if b["type"] == "plan")
            assert plan["tasks"][0]["details"] == status

    def test_actions_are_valid_wp3_buttons(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, FakeHermes({}))
        blocks = translate_rootcard_to_blocks(pilot._build_initial_card())
        actions = next(b for b in blocks if b["type"] == "actions")
        labels = [e["text"]["text"] for e in actions["elements"]]
        assert labels == ["PAUSE", "STOP", "APPROVE", "MERGE"]

    def test_invalid_plan_block_is_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            validate_slack_blocks([{"type": "plan", "title": ""}])
        with pytest.raises(TaskControllerValidationError):
            validate_slack_blocks([{"type": "plan", "title": "t",
                                    "tasks": [{"type": "task_card",
                                               "task_id": "x", "title": "y",
                                               "status": "bogus"}]}])
        with pytest.raises(TaskControllerValidationError):
            validate_slack_blocks([{"type": "actions", "elements": [
                {"type": "button", "action_id": "",
                 "text": {"type": "plain_text", "text": "x"}}]}])


# --------------------------------------------------------------------------- boundaries
class TestLoopBoundariesThroughPilot:
    def _run(self, after, report_after=None, evidence=None, status="RUNNING"):
        slack = FakeSlack()
        contracts = [_contract("S1", after=after), _contract("S2"), _contract("S3")]
        hermes = FakeHermes({
            "S1": json.dumps(_report("S1", status=status,
                                     evidence=evidence or ["e1"],
                                     after=report_after or after).to_dict())
        })
        pilot = _build_pilot(contracts, slack, hermes, active_subtask_id="S1")
        return pilot.run(max_polls=1), slack, pilot

    def test_continue_returns_without_stopping(self):
        outcome, slack, pilot = self._run(CONTINUE)
        assert outcome.verdict == CONTINUE
        assert slack.updates == 1

    def test_wait_controller_stops_delegated_continuation(self):
        outcome, slack, pilot = self._run(WAIT_CONTROLLER, report_after=WAIT_CONTROLLER)
        assert outcome.verdict == WAIT_CONTROLLER
        assert outcome.polls == 1

    def test_terminal_closes_segment_but_grants_no_authority(self):
        outcome, slack, pilot = self._run(TERMINAL, report_after=TERMINAL)
        assert outcome.verdict == TERMINAL
        assert outcome.delegated_segment_closed is True
        assert outcome.runtime_done is False
        assert outcome.grants_authority is False

    def test_drift_triggers_bounded_intercept_not_continue(self):
        slack = FakeSlack()
        bad = _report("S2")  # report claims an uncontracted subtask
        hermes = FakeHermes({"S1": json.dumps(bad.to_dict())})
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, hermes, active_subtask_id="S1")
        outcome = pilot.run(max_polls=1)
        # drift -> INTERCEPT boundary (scope drift), never CONTINUE/TERMINAL
        assert outcome.verdict == "INTERCEPT"
        assert outcome.reason == REASON_BOUNDARY
        assert slack.creates == 1  # no second root


# --------------------------------------------------------------------------- material update
class TestMaterialObservationUpdatesSameRoot:
    def test_actual_values_render_into_same_rootcard(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        hermes = FakeHermes({
            "S1": json.dumps(_report(
                "S1", status="RUNNING", completed=["u1", "u2"],
                evidence=["e1", "latest evidence"],
                finding_risk=["inherited lock mismatch"],
                next_action="controller release required",
            ).to_dict())
        })
        pilot = _build_pilot(contracts, slack, hermes, active_subtask_id="S1")
        root = pilot.ensure_root()
        report = pilot.dispatch_current()
        slack.post_thread_reply(pilot.config.channel, root, json.dumps(report.to_dict()))
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=lambda last_seen_ts: slack.read_thread_replies(
                pilot.config.channel, root, last_seen_ts),
            update_rootcard=pilot.apply_observation,
            sleeper=lambda _: None,
            last_seen_ts=root,
            max_polls=1,
        )
        assert outcome.verdict == CONTINUE
        assert slack.creates == 1  # SAME root
        active_card = next(c for c in pilot._card.plan.cards if c.subtask_id == "S1")  # type: ignore[union-attr]
        assert active_card.status == TaskCardStatus.IN_PROGRESS
        blocks = translate_rootcard_to_blocks(pilot._card)  # type: ignore[arg-type]
        plan = next(b for b in blocks if b["type"] == "plan")
        task = plan["tasks"][0]
        assert task["status"] == "in_progress"
        context = next(b for b in blocks if b["type"] == "context")
        texts = " ".join(e["text"] for e in context["elements"])
        assert "inherited lock mismatch" in texts
        assert "latest evidence" in texts
        assert "controller release required" in texts


# --------------------------------------------------------------------------- malformed
class TestMalformedReplyFailClosed:
    def test_non_json_reply_raises(self):
        with pytest.raises(MalformedReportError):
            parse_hermes_reply("{not json")

    def test_missing_field_reply_raises(self):
        with pytest.raises(MalformedReportError):
            parse_hermes_reply(json.dumps({"subtask_id": "S1"}))

    def test_invalid_status_reply_raises(self):
        # WP1 rejects the bad status at construction, so build the raw payload
        bad = {"subtask_id": "S1", "status": "NOPE",
               "completed": ["u"], "evidence": ["e"],
               "finding_risk": [], "next_action": "x", "after": "CONTINUE"}
        with pytest.raises(MalformedReportError):
            parse_hermes_reply(bad)

    def test_malformed_reply_never_reaches_continue(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        hermes = FakeHermes({"S1": "{not json"})
        pilot = _build_pilot(contracts, slack, hermes, active_subtask_id="S1")
        with pytest.raises(MalformedReportError):
            pilot.run(max_polls=1)


# --------------------------------------------------------------------------- default OFF
class TestFullE2EDefaultOff:
    def test_module_keeps_deferred_core_out(self):
        assert pilot_module.module_keeps_deferred_core_out() is True

    def test_advanced_mode_guard_blocks_without_opt_in(self):
        with pytest.raises(AdvancedModeRequired):
            pilot_module._require_advanced(False, "lease takeover")

    def test_advanced_mode_allowed_when_opted_in(self):
        assert pilot_module._require_advanced(True, "lease takeover") is None


class TestBlockedFailedRenderAsError:
    def test_blocked_report_renders_error_with_details_and_ends_segment(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        hermes = FakeHermes({
            "S1": json.dumps(_report(
                "S1", status="BLOCKED", after=CONTINUE,
                completed=["u1"], evidence=["e1"],
                finding_risk=["inherited lock mismatch"],
                next_action="controller release required",
            ).to_dict())
        })
        pilot = _build_pilot(contracts, slack, hermes, active_subtask_id="S1")
        root = pilot.ensure_root()
        report = pilot.dispatch_current()
        slack.post_thread_reply(pilot.config.channel, root, json.dumps(report.to_dict()))
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=lambda last_seen_ts: slack.read_thread_replies(
                pilot.config.channel, root, last_seen_ts),
            update_rootcard=pilot.apply_observation,
            sleeper=lambda _: None,
            last_seen_ts=root,
            max_polls=1,
        )
        # BLOCKED -> TERMINAL closes the delegated segment
        assert outcome.verdict == TERMINAL
        assert outcome.delegated_segment_closed is True
        assert outcome.runtime_done is False
        # the translated Slack task_card must carry error + BLOCKED distinction
        blocks = translate_rootcard_to_blocks(pilot._card)
        plan = next(b for b in blocks if b["type"] == "plan")
        task = plan["tasks"][0]
        assert task["status"] == "error"
        assert task["details"] == "BLOCKED"
