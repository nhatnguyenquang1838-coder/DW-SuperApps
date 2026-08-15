"""WP5 (#52) focused tests — MVP pilot adapter GPT->Slack->Hermes->WP4 loop.

Deterministic fake Slack/Hermes clients only: the MVP CI path never touches a
network. Proves the *live Slack-mediated topology* (Controller dispatches a
command into the thread; the Executor replies later as a distinct actor; the
loop reads only the Executor reply), one-root, ordered 3-5 subtasks with single
dispatch, valid Block Kit plan/task_card schema + exact status mapping +
contextual-only actions + rich_text error details, the concrete
SlackWebApiTransport wrapper, canonical human-readable Executor report parsing,
material observation updating the SAME RootCard with real values, malformed
report fail-closed, and that deferred Full-E2E core modules are not imported.
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
)
from taskcontroller.mvp.pilot import (
    AdvancedModeRequired,
    HermesExecutorClient,
    SlackTransport,
    SlackWebApiTransport,
    MvpPilot,
    MvpPilotConfig,
    parse_hermes_reply,
    parse_hermes_thread_update,
    translate_rootcard_to_blocks,
    validate_slack_blocks,
)
from taskcontroller.mvp.protocol_bridge import (
    CONTRACTED_AFTER_VALUES,
    ContractedSubtask,
    ExecutorReport,
)
from taskcontroller.mvp.rootcard import (
    RootCard,
    TaskCard,
    TaskCardStatus,
    COST_UNKNOWN,
    TOKEN_USAGE_UNKNOWN,
)


# --------------------------------------------------------------------------- fakes
class FakeSlack(SlackTransport):
    """Faithful fake: Controller command and Executor reply are DISTINCT events.

    The Executor reply is enqueued by the fake *as a separate actor* via
    ``enqueue_executor_reply``; ``read_thread_replies`` filters strictly newer
    than the cursor and never returns the root or the Controller command.
    """

    def __init__(self):
        self.creates = 0
        self.updates = 0
        self.root_ts = "100.0"
        self._executor_replies: dict[str, list[ThreadReply]] = {}

    def create_root(self, channel, blocks):
        self.creates += 1
        validate_slack_blocks(blocks)
        return self.root_ts

    def update_root(self, channel, root_ts, blocks):
        self.updates += 1
        validate_slack_blocks(blocks)

    def dispatch_command(self, channel, root_ts, text, executor_user_id):
        # The Controller's command message. Distinct from the Executor reply.
        return str(float(root_ts) + 0.05)

    def enqueue_executor_reply(self, root_ts, report: ExecutorReport) -> str:
        """Simulate the Executor (separate actor) posting its own reply."""
        ts = str(float(root_ts) + 0.1 + len(self._executor_replies.get(root_ts, [])) * 0.001)
        self._executor_replies.setdefault(root_ts, []).append(
            ThreadReply(ts=ts, payload=report.to_dict())
        )
        return ts

    def enqueue_executor_reply_bad(self, root_ts, text: str) -> str:
        # A malformed executor reply stored as text; the Web API reader would
        # parse it and fail closed. For the fake we keep the raw text and let
        # the pilot's reader path exercise parse via a thin wrapper.
        ts = str(float(root_ts) + 0.1 + len(self._executor_replies.get(root_ts, [])) * 0.001)
        payload = {"__raw_text__": text}
        self._executor_replies.setdefault(root_ts, []).append(
            ThreadReply(ts=ts, payload=payload)
        )
        return ts

    def read_thread_replies(self, channel, root_ts, since_ts):
        items = self._executor_replies.get(root_ts, [])
        if since_ts is None:
            return list(items)
        return [r for r in items if float(r.ts) > float(since_ts)]


class FakeHermes(HermesExecutorClient):
    """Test-only synchronous helper. NOT the production topology."""

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


def _pilot_config(slack, contracts, **kw):
    return MvpPilotConfig(
        run_id="RUN-47",
        channel="C0BJSPXN7UN",
        human_owner="Nhat",
        controller="ChatGPT",
        executor="Hermes Cloud",
        contracts=tuple(contracts),
        slack=slack,
        **kw,
    )


def _build_pilot(contracts, slack, **kw):
    return MvpPilot(config=_pilot_config(slack, contracts, **kw))


def _card_fields(card):
    return {k: getattr(card, k) for k in (
        "run_id", "human_owner", "controller", "executor", "plan",
        "active_subtask_id", "now", "next", "last_material_update",
        "executor_model", "token_usage", "cost", "watcher", "branch", "pr",
        "head_sha", "ci_status", "risk", "gwc_active", "gate_journey",
        "authority_boundary", "merge_ready", "paused") if hasattr(card, k)}


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
        pilot = _build_pilot(contracts, slack)
        assert pilot.ensure_root() == "100.0"
        pilot.ensure_root()
        pilot.ensure_root()
        assert slack.creates == 1
        assert pilot.ensure_root() == "100.0"

    def test_repeat_update_rotation_never_spawns_second_root(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack)
        root = pilot.ensure_root()
        pilot.config = _pilot_config(
            slack, contracts, executor_model="new-model"
        )
        same = pilot.ensure_root()
        assert same == root == "100.0"
        assert slack.creates == 1


# --------------------------------------------------------------------------- ordered dispatch
class TestOrderedSubtaskDispatch:
    def test_3_to_5_contracted_subtasks_maintain_order(self):
        slack = FakeSlack()
        contracts = [_contract(f"S{i}") for i in (1, 2, 3, 4, 5)]
        pilot = _build_pilot(contracts, slack)
        plan_ids = [c.subtask_id for c in pilot._build_initial_card().plan.cards]
        assert plan_ids == ["S1", "S2", "S3", "S4", "S5"]

    def test_only_selected_current_subtask_command_is_dispatched(self):
        slack = FakeSlack()
        dispatched = []

        class TrackingSlack(FakeSlack):
            def dispatch_command(self, channel, root_ts, text, executor_user_id):
                dispatched.append(text)
                return super().dispatch_command(channel, root_ts, text, executor_user_id)

        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, TrackingSlack(), active_subtask_id="S2")
        pilot.dispatch_current()
        # The command text must address only the selected subtask S2.
        assert len(dispatched) == 1
        assert "S2" in dispatched[0]
        assert "S1" not in dispatched[0]

    def test_uncontracted_active_subtask_is_rejected(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        cfg = _pilot_config(slack, contracts, active_subtask_id="S9")
        pilot = MvpPilot(config=cfg)
        with pytest.raises(TaskControllerValidationError):
            pilot.dispatch_current()


# --------------------------------------------------------------------------- block kit schema
class TestSlackBlockKitSchema:
    def test_translated_payload_is_valid_plan_task_card(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack)
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
        pilot = _build_pilot(contracts, slack)
        card = pilot._build_initial_card()
        for status, expected in mapping.items():
            replaced = _replaced_card(card, status)
            blocks = translate_rootcard_to_blocks(replaced)
            plan = next(b for b in blocks if b["type"] == "plan")
            assert plan["tasks"][0]["status"] == expected

    def test_blocked_vs_failed_distinction_in_rich_text_details(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack)
        card = pilot._build_initial_card()
        for status in (TaskCardStatus.BLOCKED, TaskCardStatus.FAILED):
            replaced = _replaced_card(card, status)
            blocks = translate_rootcard_to_blocks(replaced)
            plan = next(b for b in blocks if b["type"] == "plan")
            details = plan["tasks"][0]["details"]
            assert details["type"] == "rich_text"
            text = "".join(
                e2.get("text", "")
                for e in details["elements"]
                for e2 in e.get("elements", [])
            )
            assert status in text

    def test_raw_string_details_is_rejected(self):
        bad_blocks = [{
            "type": "plan",
            "title": "t",
            "tasks": [{
                "type": "task_card", "task_id": "x", "title": "y",
                "status": "error", "details": "BLOCKED",
            }],
        }]
        with pytest.raises(TaskControllerValidationError):
            validate_slack_blocks(bad_blocks)

    def test_actions_render_only_contextual_actions(self):
        # A default card has no authority boundary / merge_ready -> no APPROVE/MERGE.
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack)
        blocks = translate_rootcard_to_blocks(pilot._build_initial_card())
        actions = next(b for b in blocks if b["type"] == "actions")
        labels = [e["text"]["text"] for e in actions["elements"]]
        assert labels == ["PAUSE", "STOP"]

    def test_approve_only_at_authority_boundary(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack)
        card = pilot._build_initial_card()
        card = card.__class__(**{**_card_fields(card), "authority_boundary": True})
        blocks = translate_rootcard_to_blocks(card)
        actions = next(b for b in blocks if b["type"] == "actions")
        labels = [e["text"]["text"] for e in actions["elements"]]
        assert "APPROVE" in labels
        assert "MERGE" not in labels

    def test_merge_only_when_merge_ready(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack)
        card = pilot._build_initial_card()
        card = card.__class__(**{**_card_fields(card), "merge_ready": True,
                                  "pr": "PR #53", "head_sha": "03880aa"})
        blocks = translate_rootcard_to_blocks(card)
        actions = next(b for b in blocks if b["type"] == "actions")
        labels = [e["text"]["text"] for e in actions["elements"]]
        assert "MERGE" in labels

    def test_invalid_action_exposure_rejected(self):
        bad_blocks = [{
            "type": "actions",
            "elements": [{"type": "button", "action_id": "resume",
                          "text": {"type": "plain_text", "text": "RESUME"}}],
        }]
        with pytest.raises(TaskControllerValidationError):
            validate_slack_blocks(bad_blocks)

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


# --------------------------------------------------------------------------- live topology
class TestLiveSlackMediatedTopology:
    def test_controller_posts_command_executor_replies_later(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        # Controller dispatches the command (returns a receipt ts, NOT a report)
        cmd_ts = pilot.dispatch_current()
        assert cmd_ts > root
        # Executor (separate actor) enqueues its own reply later
        slack.enqueue_executor_reply(root, _report("S1", status="RUNNING"))
        replies = slack.read_thread_replies(pilot.config.channel, root, cmd_ts)
        assert len(replies) == 1
        assert replies[0].payload["subtask_id"] == "S1"

    def test_loop_reads_only_executor_reply_not_controller_command(self):
        slack = FakeSlack()
        contracts = [_contract("S1", after=CONTINUE), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(root, _report("S1", status="RUNNING"))
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=lambda last_seen_ts: slack.read_thread_replies(
                pilot.config.channel, root, last_seen_ts),
            update_rootcard=pilot.apply_observation,
            sleeper=lambda _: None,
            last_seen_ts=cmd_ts,
            max_polls=1,
        )
        assert outcome.verdict == CONTINUE
        assert slack.creates == 1  # no second root

    def test_full_run_topology_continues(self):
        slack = FakeSlack()
        contracts = [_contract("S1", after=CONTINUE), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(root, _report("S1", status="RUNNING"))
        outcome = pilot.run(max_polls=1)
        assert outcome.verdict == CONTINUE


# --------------------------------------------------------------------------- boundaries
class TestLoopBoundariesThroughPilot:
    def _outcome(self, executor_status, after=CONTINUE, contracts_after=CONTINUE):
        slack = FakeSlack()
        contracts = [_contract("S1", after=contracts_after),
                     _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(
            root, _report("S1", status=executor_status, after=after))
        return pilot.run(max_polls=1), slack

    def test_continue_returns_without_stopping(self):
        outcome, slack = self._outcome("RUNNING", after=CONTINUE)
        assert outcome.verdict == CONTINUE
        assert slack.updates == 1

    def test_wait_controller_stops_delegated_continuation(self):
        outcome, _ = self._outcome("RUNNING", after=WAIT_CONTROLLER,
                                    contracts_after=WAIT_CONTROLLER)
        assert outcome.verdict == WAIT_CONTROLLER
        assert outcome.polls == 1

    def test_terminal_closes_segment_but_grants_no_authority(self):
        outcome, _ = self._outcome("DONE", after=TERMINAL, contracts_after=TERMINAL)
        assert outcome.verdict == TERMINAL
        assert outcome.delegated_segment_closed is True
        assert outcome.runtime_done is False
        assert outcome.grants_authority is False

    def test_drift_triggers_bounded_intercept_not_continue(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1")
        root = pilot.ensure_root()
        pilot.dispatch_current()
        # Executor reply claims an uncontracted subtask -> drift
        slack.enqueue_executor_reply(root, _report("S2", status="RUNNING"))
        outcome = pilot.run(max_polls=1)
        assert outcome.verdict == "INTERCEPT"
        assert outcome.reason == REASON_BOUNDARY
        assert slack.creates == 1


# --------------------------------------------------------------------------- material update
class TestMaterialObservationUpdatesSameRoot:
    def test_actual_values_render_into_same_rootcard(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             watcher="Nhat", executor_model="gpt-4o",
                             token_usage=1200)
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(root, _report(
            "S1", status="RUNNING", completed=["u1", "u2"],
            evidence=["e1", "latest evidence"],
            finding_risk=["inherited lock mismatch"],
            next_action="controller release required",
        ))
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=lambda last_seen_ts: slack.read_thread_replies(
                pilot.config.channel, root, last_seen_ts),
            update_rootcard=pilot.apply_observation,
            sleeper=lambda _: None,
            last_seen_ts=cmd_ts,
            max_polls=1,
        )
        assert outcome.verdict == CONTINUE
        assert slack.creates == 1  # SAME root
        active_card = next(c for c in pilot._card.plan.cards if c.subtask_id == "S1")  # type: ignore[union-attr]
        assert active_card.status == TaskCardStatus.IN_PROGRESS
        # Complete operational metadata preserved in the translated blocks.
        blocks = translate_rootcard_to_blocks(pilot._card)  # type: ignore[arg-type]
        meta = next(b for b in blocks if b["type"] == "section")
        meta_text = " ".join(f["text"] for f in meta["fields"])
        assert "*watcher:* Nhat" in meta_text
        assert "*model:* gpt-4o" in meta_text
        assert "*tokens:* 1200" in meta_text
        assert f"*cost:* {COST_UNKNOWN}" in meta_text
        plan = next(b for b in blocks if b["type"] == "plan")
        task = plan["tasks"][0]
        assert task["status"] == "in_progress"
        context = next(b for b in blocks if b["type"] == "context")
        texts = " ".join(e["text"] for e in context["elements"])
        assert "inherited lock mismatch" in texts
        assert "latest evidence" in texts
        assert "controller release required" in texts


# --------------------------------------------------------------------------- C canonical text
class TestCanonicalHumanReadableReportParsing:
    def _canonical(self, status="RUNNING", after="CONTINUE"):
        return (
            "EXECUTOR UPDATE\n"
            f"Subtask: S1\n"
            f"Status: {status}\n"
            "Completed: unit one; unit two\n"
            "Evidence: exact evidence\n"
            "Finding/Risk: inherited lock mismatch\n"
            "Next: controller release required\n"
            f"After: {after}\n"
        )

    def test_parse_canonical_text_into_complete_report(self):
        report = parse_hermes_thread_update(self._canonical())
        assert isinstance(report, ExecutorReport)
        assert report.subtask_id == "S1"
        assert report.status == "RUNNING"
        assert report.completed == ("unit one", "unit two")
        assert report.evidence == ("exact evidence",)
        assert report.finding_risk == ("inherited lock mismatch",)
        assert report.next_action == "controller release required"
        assert report.after == "CONTINUE"

    def test_parse_hermes_reply_accepts_canonical_text(self):
        report = parse_hermes_reply(self._canonical(status="DONE", after="WAIT_CONTROLLER"))
        assert report.status == "DONE"
        assert report.after == "WAIT_CONTROLLER"

    def test_missing_header_fails_closed(self):
        with pytest.raises(MalformedReportError):
            parse_hermes_thread_update("Status: RUNNING\nAfter: CONTINUE")

    def test_ambiguous_status_fails_closed(self):
        with pytest.raises(MalformedReportError):
            parse_hermes_thread_update(
                "EXECUTOR UPDATE\nSubtask: S1\nStatus: MAYBE\nAfter: CONTINUE")

    def test_ambiguous_after_fails_closed(self):
        with pytest.raises(MalformedReportError):
            parse_hermes_thread_update(
                "EXECUTOR UPDATE\nSubtask: S1\nStatus: RUNNING\nAfter: SOON")


# --------------------------------------------------------------------------- B web api wrapper
class TestSlackWebApiTransportWrapper:
    def _fake_client(self, messages):
        class _Client:
            def chat_postMessage(self, **kwargs):
                return {"ts": "200.0"}

            def chat_update(self, **kwargs):
                return {"ts": "100.0"}

            def conversations_replies(self, **kwargs):
                return {"messages": messages}

        return _Client()

    def test_root_uses_chat_postMessage(self):
        transport = SlackWebApiTransport(self._fake_client([]))
        ts = transport.create_root("C", [{"type": "section", "text": {}}])
        assert ts == "200.0"

    def test_read_filters_root_and_returns_executor_reply(self):
        messages = [
            {"ts": "100.0", "text": "root"},
            {"ts": "100.5", "text": "EXECUTOR UPDATE\nSubtask: S1\nCompleted: u1\nEvidence: e1\nFinding/Risk: r1\nNext: n1\nStatus: RUNNING\nAfter: CONTINUE"},
        ]
        transport = SlackWebApiTransport(self._fake_client(messages))
        replies = transport.read_thread_replies("C", "100.0", "100.0")
        assert len(replies) == 1
        assert replies[0].payload["status"] == "RUNNING"

    def test_dispatch_command_mentions_executor(self):
        captured = {}

        class _Client:
            def chat_postMessage(self, **kwargs):
                captured.update(kwargs)
                return {"ts": "200.0"}

            def chat_update(self, **kwargs):
                return {"ts": "100.0"}

            def conversations_replies(self, **kwargs):
                return {"messages": []}

        transport = SlackWebApiTransport(_Client())
        ts = transport.dispatch_command("C", "100.0", "do S1", "U0BKE3KDY65")
        assert ts == "200.0"
        assert "U0BKE3KDY65" in captured["text"]
        assert captured["thread_ts"] == "100.0"

    def test_no_client_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            SlackWebApiTransport(None)


# --------------------------------------------------------------------------- malformed
class TestMalformedReplyFailClosed:
    def test_non_json_reply_raises(self):
        with pytest.raises(MalformedReportError):
            parse_hermes_reply("{not json")

    def test_missing_field_reply_raises(self):
        with pytest.raises(MalformedReportError):
            parse_hermes_reply(json.dumps({"subtask_id": "S1"}))

    def test_invalid_status_reply_raises(self):
        bad = {"subtask_id": "S1", "status": "NOPE",
               "completed": ["u"], "evidence": ["e"],
               "finding_risk": [], "next_action": "x", "after": "CONTINUE"}
        with pytest.raises(MalformedReportError):
            parse_hermes_reply(bad)

    def test_malformed_executor_reply_never_reaches_continue(self):
        # The Web API reader path parses the Executor text reply and fails
        # closed when it is not a valid canonical update.
        from taskcontroller.mvp.monitoring import run_monitoring_loop as _rml

        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply_bad(root, "not a valid update")

        def reader(last_seen_ts):
            items = slack.read_thread_replies(pilot.config.channel, root, last_seen_ts)
            out = []
            for r in items:
                raw = r.payload.get("__raw_text__", "")
                # mirror the Web API transport parse path
                payload = parse_hermes_reply(raw).to_dict()
                out.append(ThreadReply(ts=r.ts, payload=payload))
            return out

        with pytest.raises(MalformedReportError):
            _rml(
                pilot._selected_contract(),
                read_replies=reader,
                update_rootcard=pilot.apply_observation,
                sleeper=lambda _: None,
                last_seen_ts=cmd_ts,
                max_polls=1,
            )


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
    def test_blocked_report_renders_error_rich_text_and_ends_segment(self):
        slack = FakeSlack()
        contracts = [_contract("S1", after=CONTINUE), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(root, _report(
            "S1", status="BLOCKED", after=CONTINUE,
            completed=["u1"], evidence=["e1"],
            finding_risk=["inherited lock mismatch"],
            next_action="controller release required",
        ))
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=lambda last_seen_ts: slack.read_thread_replies(
                pilot.config.channel, root, last_seen_ts),
            update_rootcard=pilot.apply_observation,
            sleeper=lambda _: None,
            last_seen_ts=cmd_ts,
            max_polls=1,
        )
        assert outcome.verdict == TERMINAL
        assert outcome.delegated_segment_closed is True
        assert outcome.runtime_done is False
        blocks = translate_rootcard_to_blocks(pilot._card)
        plan = next(b for b in blocks if b["type"] == "plan")
        task = plan["tasks"][0]
        assert task["status"] == "error"
        assert task["details"]["type"] == "rich_text"
