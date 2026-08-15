"""WP5 (#52) focused tests — MVP pilot adapter GPT->Slack->Hermes->WP4 loop.

Deterministic fake Slack/Hermes clients only: the MVP CI path never touches a
network. Proves the *live Slack-mediated topology* (Controller dispatches a
command into the thread; the Executor replies later as a distinct actor; the
loop reads only the Executor-authored reply), one-root, ordered 3-5 subtasks
with single dispatch, valid Block Kit plan/task_card schema + exact status
mapping + contextual-only actions + rich_text error details, the concrete
SlackWebApiTransport wrapper with Executor actor filtering, the *authority*
canonical human-readable Executor report format, lossless timestamp ordering,
the default 60s live loop with bounded poll count for tests, WP2 projection
inputs binding (cost / gwc / authority / merge / paused), and that deferred
Full-E2E core modules are not imported.
"""

import json
import time

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
    POLL_INTERVAL_SECONDS,
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
    COST_FREE,
    TOKEN_USAGE_UNKNOWN,
)


# --------------------------------------------------------------------------- fakes
class FakeSleeper:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds: int) -> None:
        self.calls.append(seconds)


class FakeSlack(SlackTransport):
    """Faithful fake: Controller command and Executor reply are DISTINCT events.

    The Executor reply is enqueued by the fake *as a separate actor* via
    ``enqueue_executor_reply``; ``read_thread_replies`` filters strictly newer
    than the cursor and never returns the root or the Controller command. The
    fake models the WP5 actor-filter contract itself: ``read_thread_replies``
    drops any reply authored by a non-Executor actor when an ``executor_user_id``
    is supplied (mirroring ``SlackWebApiTransport``). Author metadata is tracked
    by the fake transport only — it is never placed into ``ThreadReply.payload``.
    """

    def __init__(self, executor_user_id="U0BKE3KDY65"):
        self.creates = 0
        self.updates = 0
        self.root_ts = "100.0"
        self._executor_user_id = executor_user_id
        # Each entry: {"reply": ThreadReply, "user": str}
        self._replies: dict[str, list[dict]] = {}

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
        ts = str(float(root_ts) + 0.1 + len(self._replies.get(root_ts, [])) * 0.001)
        self._replies.setdefault(root_ts, []).append(
            {"reply": ThreadReply(ts=ts, payload=report.to_dict()),
             "user": self._executor_user_id}
        )
        return ts

    def enqueue_other_reply(self, root_ts, text: str, user: str) -> str:
        """Simulate a NON-Executor actor (human/Controller) posting in the thread."""
        ts = str(float(root_ts) + 0.1 + len(self._replies.get(root_ts, [])) * 0.001)
        self._replies.setdefault(root_ts, []).append(
            {"reply": ThreadReply(ts=ts, payload={"raw_text": text}), "user": user}
        )
        return ts

    def read_thread_replies(self, channel, root_ts, since_ts, executor_user_id=None):
        entries = self._replies.get(root_ts, [])
        expected = executor_user_id or self._executor_user_id
        out = []
        for entry in entries:
            r = entry["reply"]
            if since_ts is not None and pilot_module._ts_key_pilot(r.ts) <= pilot_module._ts_key_pilot(since_ts):
                continue
            # Fake transport actor filtering (mirrors SlackWebApiTransport): drop
            # replies whose author is not the expected Executor.
            if expected and entry["user"] != expected:
                continue
            out.append(r)
        return out


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
    base = dict(
        run_id="RUN-47",
        channel="C0BJSPXN7UN",
        human_owner="Nhat",
        controller="ChatGPT",
        executor="Hermes Cloud",
        contracts=tuple(contracts),
        slack=slack,
    )
    base.update(kw)
    return MvpPilotConfig(**base)


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

    def test_header_is_a_valid_header_block_not_nested_rich_text(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack)
        blocks = translate_rootcard_to_blocks(pilot._build_initial_card())
        header = blocks[0]
        assert header["type"] == "header"
        assert header["text"]["type"] == "plain_text"

    def test_meta_split_into_at_most_10_field_sections(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        # Force the maximum possible metadata to exceed 10 fields.
        pilot = _build_pilot(
            contracts, slack,
            watcher="Nhat", executor_model="gpt-4o", token_usage=1200,
            branch="fix/x", pr="PR #53", head_sha="03880aa",
            ci_status="success", cost=COST_FREE, gwc_active=True,
            gate_journey="gate-1",
        )
        blocks = translate_rootcard_to_blocks(pilot._build_initial_card())
        sections = [b for b in blocks if b["type"] == "section" and b["block_id"].startswith("mvp_meta_")]
        assert sections, "expected at least one meta section"
        for s in sections:
            assert len(s["fields"]) <= 10
        # All expected metadata present across the split sections.
        all_text = " ".join(f["text"] for s in sections for f in s["fields"])
        for label in ("owner", "controller", "executor", "watcher", "model",
                      "tokens", "cost", "journey", "active", "branch", "pr",
                      "head", "ci"):
            assert f"*{label}:*" in all_text

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

    def test_nested_rich_text_is_rejected(self):
        bad_blocks = [{
            "type": "rich_text",
            "elements": [{"type": "rich_text", "elements": [{"type": "text", "text": "x"}]}],
        }]
        with pytest.raises(TaskControllerValidationError):
            validate_slack_blocks(bad_blocks)

    def test_section_fields_over_ten_is_rejected(self):
        bad_blocks = [{
            "type": "section",
            "fields": [{"type": "mrkdwn", "text": f"*f{i}:* x"} for i in range(11)],
        }]
        with pytest.raises(TaskControllerValidationError):
            validate_slack_blocks(bad_blocks)

    def test_actions_render_only_contextual_actions(self):
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
    def _authority_reply(self, subtask_id="S1", status="RUNNING", after="CONTINUE"):
        return (
            f"🟡 EXECUTOR UPDATE · {subtask_id}/3\n"
            f"Status: {status}\n"
            f"Phase: executing\n\n"
            "Completed\n- unit one\n- unit two\n\n"
            "Evidence\n- exact evidence\n\n"
            "Finding / Risk\n- inherited lock mismatch\n\n"
            "Next\n→ controller release required\n\n"
            f"{subtask_id} · {after}"
        )

    def test_controller_posts_command_executor_replies_later(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        assert cmd_ts > root
        slack.enqueue_executor_reply(root, parse_hermes_thread_update(self._authority_reply("S1")))
        replies = slack.read_thread_replies(pilot.config.channel, root, cmd_ts, pilot.config.executor_user_id)
        assert len(replies) == 1
        assert replies[0].payload["subtask_id"] == "S1"

    def test_loop_reads_only_executor_reply_not_controller_command(self):
        slack = FakeSlack()
        contracts = [_contract("S1", after=CONTINUE), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(root, parse_hermes_thread_update(self._authority_reply("S1")))
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=lambda last_seen_ts: slack.read_thread_replies(
                pilot.config.channel, root, last_seen_ts, pilot.config.executor_user_id),
            update_rootcard=pilot.apply_observation,
            sleeper=FakeSleeper(),
            last_seen_ts=cmd_ts,
            max_polls=1,
        )
        assert outcome.verdict == CONTINUE
        assert slack.creates == 1  # no second root

    def test_full_run_topology_continues(self):
        slack = FakeSlack()
        contracts = [_contract("S1", after=CONTINUE), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(root, parse_hermes_thread_update(self._authority_reply("S1")))
        outcome = pilot.run(max_polls=1, sleeper=FakeSleeper())
        assert outcome.verdict == CONTINUE


# --------------------------------------------------------------------------- boundaries
class TestLoopBoundariesThroughPilot:
    def _authority_reply(self, subtask_id="S1", status="RUNNING", after="CONTINUE"):
        return (
            f"🟡 EXECUTOR UPDATE · {subtask_id}/3\n"
            f"Status: {status}\n"
            f"Phase: executing\n\n"
            "Completed\n- unit one\n\n"
            "Evidence\n- exact evidence\n\n"
            "Next\n→ controller release required\n\n"
            f"{subtask_id} · {after}"
        )

    def _outcome(self, executor_status, after=CONTINUE, contracts_after=CONTINUE):
        slack = FakeSlack()
        contracts = [_contract("S1", after=contracts_after),
                     _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(
            root, parse_hermes_thread_update(self._authority_reply("S1", executor_status, after)))
        return pilot.run(max_polls=1, sleeper=FakeSleeper()), slack

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
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        pilot.dispatch_current()
        # Executor reply claims an uncontracted subtask -> drift
        slack.enqueue_executor_reply(root, parse_hermes_thread_update(
            self._authority_reply("S2")))
        outcome = pilot.run(max_polls=1, sleeper=FakeSleeper())
        assert outcome.verdict == "INTERCEPT"
        assert outcome.reason == REASON_BOUNDARY
        assert slack.creates == 1


# --------------------------------------------------------------------------- material update
class TestMaterialObservationUpdatesSameRoot:
    def _authority_reply(self, subtask_id="S1"):
        return (
            f"🟡 EXECUTOR UPDATE · {subtask_id}/3\n"
            "Status: RUNNING\n"
            "Phase: executing\n\n"
            "Completed\n- u1\n- u2\n\n"
            "Evidence\n- e1\n- latest evidence\n\n"
            "Finding / Risk\n- inherited lock mismatch\n\n"
            "Next\n→ controller release required\n\n"
            f"{subtask_id} · CONTINUE"
        )

    def test_actual_values_render_into_same_rootcard(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             watcher="Nhat", executor_model="gpt-4o",
                             token_usage=1200, executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(root, parse_hermes_thread_update(self._authority_reply("S1")))
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=lambda last_seen_ts: slack.read_thread_replies(
                pilot.config.channel, root, last_seen_ts, pilot.config.executor_user_id),
            update_rootcard=pilot.apply_observation,
            sleeper=FakeSleeper(),
            last_seen_ts=cmd_ts,
            max_polls=1,
        )
        assert outcome.verdict == CONTINUE
        assert slack.creates == 1  # SAME root
        active_card = next(c for c in pilot._card.plan.cards if c.subtask_id == "S1")
        assert active_card.status == TaskCardStatus.IN_PROGRESS
        blocks = translate_rootcard_to_blocks(pilot._card)
        meta_sections = [b for b in blocks if b["type"] == "section" and b["block_id"].startswith("mvp_meta_")]
        all_meta_text = " ".join(f["text"] for s in meta_sections for f in s["fields"])
        assert "*watcher:* Nhat" in all_meta_text
        assert "*model:* gpt-4o" in all_meta_text
        assert "*tokens:* 1200" in all_meta_text
        assert f"*cost:* {COST_UNKNOWN}" in all_meta_text
        plan = next(b for b in blocks if b["type"] == "plan")
        task = plan["tasks"][0]
        assert task["status"] == "in_progress"
        context = next(b for b in blocks if b["type"] == "context")
        texts = " ".join(e["text"] for e in context["elements"])
        assert "inherited lock mismatch" in texts
        assert "latest evidence" in texts
        assert "controller release required" in texts


# --------------------------------------------------------------------------- #1 authority text
class TestCanonicalHumanReadableReportParsing:
    def _authority(self, subtask_id="S1", status="RUNNING", after="CONTINUE",
                   include_finding=True):
        finding = "Finding / Risk\n- inherited lock mismatch\n\n" if include_finding else ""
        return (
            f"🟡 EXECUTOR UPDATE · {subtask_id}/3\n"
            f"Status: {status}\n"
            "Phase: executing\n\n"
            "Completed\n- unit one\n- unit two\n\n"
            "Evidence\n- exact evidence\n\n"
            f"{finding}"
            "Next\n→ controller release required\n\n"
            f"{subtask_id} · {after}"
        )

    def test_parse_authority_text_into_complete_report(self):
        report = parse_hermes_thread_update(self._authority())
        assert isinstance(report, ExecutorReport)
        assert report.subtask_id == "S1"
        assert report.status == "RUNNING"
        assert report.completed == ("unit one", "unit two")
        assert report.evidence == ("exact evidence",)
        assert report.finding_risk == ("inherited lock mismatch",)
        assert report.next_action == "controller release required"
        assert report.after == "CONTINUE"

    def test_header_and_final_subtask_must_agree(self):
        text = (
            "🟡 EXECUTOR UPDATE · S1/3\n"
            "Status: RUNNING\n\n"
            "Completed\n- u\n\n"
            "Evidence\n- e\n\n"
            "Next\n→ x\n\n"
            "S2 · CONTINUE"
        )
        with pytest.raises(MalformedReportError):
            parse_hermes_thread_update(text)

    def test_missing_emoji_header_fails_closed(self):
        text = (
            "EXECUTOR UPDATE · S1/3\n"
            "Status: RUNNING\n\n"
            "Completed\n- u\n\n"
            "Evidence\n- e\n\n"
            "Next\n→ x\n\n"
            "S1 · CONTINUE"
        )
        with pytest.raises(MalformedReportError):
            parse_hermes_thread_update(text)

    def test_final_verdict_derived_for_after(self):
        report = parse_hermes_thread_update(self._authority(after="TERMINAL"))
        assert report.after == "TERMINAL"

    def test_finding_risk_optional_when_authority_allows(self):
        report = parse_hermes_thread_update(self._authority(include_finding=False))
        assert report.finding_risk == ()

    def test_parse_hermes_reply_accepts_authority_text(self):
        report = parse_hermes_reply(self._authority(status="DONE", after="WAIT_CONTROLLER"))
        assert report.status == "DONE"
        assert report.after == "WAIT_CONTROLLER"

    def test_missing_status_fails_closed(self):
        text = (
            "🟡 EXECUTOR UPDATE · S1/3\n\n"
            "Completed\n- u\n\n"
            "Evidence\n- e\n\n"
            "Next\n→ x\n\n"
            "S1 · CONTINUE"
        )
        with pytest.raises(MalformedReportError):
            parse_hermes_thread_update(text)

    def test_missing_after_fails_closed(self):
        text = (
            "🟡 EXECUTOR UPDATE · S1/3\n"
            "Status: RUNNING\n\n"
            "Completed\n- u\n\n"
            "Evidence\n- e\n\n"
            "Next\n→ x\n"
        )
        with pytest.raises(MalformedReportError):
            parse_hermes_thread_update(text)


# --------------------------------------------------------------------------- #2 executor actor filtering
class TestSlackWebApiTransportWrapper:
    def _make_transport(self, messages, executor_user_id="U0BKE3KDY65"):
        class _Msg:
            def __init__(self, ts, text, user):
                self._d = {"ts": ts, "text": text, "user": user}

            def get(self, k, default=None):
                return self._d.get(k, default)

        class _Resp:
            def __init__(self, msgs):
                self._msgs = msgs

            def get(self, k, default=None):
                return self._msgs if k == "messages" else default

        class _Client:
            def conversations_replies(self, **kwargs):
                return _Resp(messages)

            def chat_postMessage(self, **kwargs):
                return {"ts": "200.0"}

            def chat_update(self, **kwargs):
                return {"ts": "100.0"}

        return SlackWebApiTransport(_Client(), executor_user_id=executor_user_id)

    def test_root_uses_chat_postMessage_with_nonempty_fallback_text(self):
        captured = {}

        class _Client:
            def chat_postMessage(self, **kwargs):
                captured.update(kwargs)
                return {"ts": "200.0"}

            def chat_update(self, **kwargs):
                return {"ts": "100.0"}

            def conversations_replies(self, **kwargs):
                return {"messages": []}

        transport = SlackWebApiTransport(_Client(), executor_user_id="U0BKE3KDY65")
        ts = transport.create_root("C", [{"type": "header", "text": {"type": "plain_text", "text": "Run X"}}])
        assert ts == "200.0"
        assert isinstance(captured.get("text"), str) and captured["text"].strip()

    def test_read_returns_only_executor_authored_reports(self):
        authority = (
            "🟡 EXECUTOR UPDATE · S1/3\n"
            "Status: RUNNING\n\n"
            "Completed\n- u1\n\n"
            "Evidence\n- e1\n\n"
            "Next\n→ n1\n\n"
            "S1 · CONTINUE"
        )
        messages = [
            _FakeMsg("100.0", "root", "UROOT"),
            _FakeMsg("100.5", "a human reply, not a report", "UHUMAN"),
            _FakeMsg("100.7", authority, "U0BKE3KDY65"),
        ]
        transport = self._make_transport(messages, executor_user_id="U0BKE3KDY65")
        replies = transport.read_thread_replies("C", "100.0", "100.0", executor_user_id="U0BKE3KDY65")
        assert len(replies) == 1
        assert replies[0].payload["status"] == "RUNNING"

    def test_human_reply_without_executor_identity_is_ignored(self):
        authority = (
            "🟡 EXECUTOR UPDATE · S1/3\n"
            "Status: RUNNING\n\n"
            "Completed\n- u1\n\n"
            "Evidence\n- e1\n\n"
            "Next\n→ n1\n\n"
            "S1 · CONTINUE"
        )
        messages = [
            _FakeMsg("100.0", "root", "UROOT"),
            _FakeMsg("100.5", authority, "U0BKE3KDY65"),
        ]
        # transport bound to a DIFFERENT executor id -> nothing returned
        transport = self._make_transport(messages, executor_user_id="UOTHER")
        replies = transport.read_thread_replies("C", "100.0", "100.0", executor_user_id="UOTHER")
        assert replies == []

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

        transport = SlackWebApiTransport(_Client(), executor_user_id="U0BKE3KDY65")
        ts = transport.dispatch_command("C", "100.0", "do S1", "U0BKE3KDY65")
        assert ts == "200.0"
        assert "U0BKE3KDY65" in captured["text"]
        assert captured["thread_ts"] == "100.0"

    def test_dispatch_command_without_executor_id_fails_closed(self):
        class _Client:
            def chat_postMessage(self, **kwargs):
                return {"ts": "200.0"}

            def chat_update(self, **kwargs):
                return {"ts": "100.0"}

            def conversations_replies(self, **kwargs):
                return {"messages": []}

        transport = SlackWebApiTransport(_Client(), executor_user_id=None)
        with pytest.raises(TaskControllerValidationError):
            transport.dispatch_command("C", "100.0", "do S1", "")

    def test_no_client_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            SlackWebApiTransport(None, executor_user_id="U0BKE3KDY65")


class _FakeMsg:
    def __init__(self, ts, text, user):
        self._d = {"ts": ts, "text": text, "user": user}

    def get(self, k, default=None):
        return self._d.get(k, default) if isinstance(self._d, dict) else None


# --------------------------------------------------------------------------- #3 timestamp ordering
class TestTimestampOrderingLossless:
    def test_ts_key_orders_numeric_not_lexicographic(self):
        key = pilot_module._ts_key_pilot
        assert key("99.0") < key("100.0")
        assert key("1.5") == key("1.500000")
        assert key("100.0") > key("99.999999")

    def test_transport_uses_lossless_ordering(self):
        authority = (
            "🟡 EXECUTOR UPDATE · S1/3\n"
            "Status: RUNNING\n\n"
            "Completed\n- u1\n\n"
            "Evidence\n- e1\n\n"
            "Next\n→ n1\n\n"
            "S1 · CONTINUE"
        )
        # A reply with a lexicographically-smaller-but-numerically-larger ts.
        messages = [
            _FakeMsg("100.0", "root", "UROOT"),
            _FakeMsg("100.9", authority, "U0BKE3KDY65"),
        ]

        class _Resp:
            def get(self, k, default=None):
                return messages if k == "messages" else default

        class _Client:
            def conversations_replies(self, **kwargs):
                return _Resp()

        transport = SlackWebApiTransport(_Client(), executor_user_id="U0BKE3KDY65")
        replies = transport.read_thread_replies("C", "100.0", "100.0", executor_user_id="U0BKE3KDY65")
        assert len(replies) == 1  # the 100.9 reply is newer than 100.0


# --------------------------------------------------------------------------- #4 live 60s loop default
class TestLiveLoopDefaultCadence:
    def _authority_reply(self, subtask_id="S1", status="RUNNING", after="CONTINUE"):
        return (
            f"🟡 EXECUTOR UPDATE · {subtask_id}/3\n"
            f"Status: {status}\n"
            "Phase: x\n\n"
            "Completed\n- u\n\n"
            "Evidence\n- e\n\n"
            "Next\n→ await\n\n"
            f"{subtask_id} · {after}"
        )

    def test_run_defaults_to_real_60s_sleeper_until_boundary(self, monkeypatch):
        slack = FakeSlack()
        contracts = [_contract("S1", after=WAIT_CONTROLLER), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(root, parse_hermes_thread_update(self._authority_reply("S1", "RUNNING", "WAIT_CONTROLLER")))

        # Patch the live sleeper to capture cadence without real sleeping.
        # monkeypatch restores the EXACT original module-global callable on exit,
        # so no test leaves pilot_module._live_sleeper mutated (no runtime leak).
        captured = []

        def fake_live_sleeper(seconds):
            captured.append(seconds)

        monkeypatch.setattr(pilot_module, "_live_sleeper", fake_live_sleeper)
        outcome = pilot.run(max_polls=None)
        assert outcome.verdict == WAIT_CONTROLLER
        assert captured == [POLL_INTERVAL_SECONDS]

    def test_run_without_executor_identity_fails_closed(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id=None)
        with pytest.raises(TaskControllerValidationError):
            pilot.run(max_polls=1, sleeper=FakeSleeper())

    def test_run_rejects_zero_or_negative_max_polls(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        pilot.ensure_root()
        for bad in (0, -1, False):
            with pytest.raises(TaskControllerValidationError):
                pilot.run(max_polls=bad, sleeper=FakeSleeper())


# --------------------------------------------------------------------------- #6 projection inputs binding
class TestProjectionInputsBinding:
    def test_cost_and_gwc_fields_project_into_rootcard(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(
            contracts, slack,
            cost=COST_FREE,
            gwc_active=True,
            gate_journey="gate-1",
            authority_boundary=True,
            merge_ready=True,
            pr="PR #53",
            head_sha="03880aa",
            paused=False,
            executor_user_id="U0BKE3KDY65",
        )
        card = pilot._build_initial_card()
        assert card.cost == COST_FREE
        assert card.gwc_active is True
        assert card.gate_journey == "gate-1"
        assert card.authority_boundary is True
        assert card.merge_ready is True
        assert card.paused is False
        blocks = translate_rootcard_to_blocks(card)
        actions = next(b for b in blocks if b["type"] == "actions")
        labels = [e["text"]["text"] for e in actions["elements"]]
        assert "APPROVE" in labels
        assert "MERGE" in labels

    def test_approve_absent_without_authority_boundary(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(
            contracts, slack,
            authority_boundary=False,
            merge_ready=True, pr="PR #53", head_sha="03880aa",
            executor_user_id="U0BKE3KDY65",
        )
        card = pilot._build_initial_card()
        blocks = translate_rootcard_to_blocks(card)
        actions = next(b for b in blocks if b["type"] == "actions")
        labels = [e["text"]["text"] for e in actions["elements"]]
        assert "APPROVE" not in labels
        assert "MERGE" in labels

    def test_merge_absent_without_merge_ready(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(
            contracts, slack,
            authority_boundary=True,
            merge_ready=False,
            executor_user_id="U0BKE3KDY65",
        )
        card = pilot._build_initial_card()
        blocks = translate_rootcard_to_blocks(card)
        actions = next(b for b in blocks if b["type"] == "actions")
        labels = [e["text"]["text"] for e in actions["elements"]]
        assert "MERGE" not in labels
        assert "APPROVE" in labels

    def test_paused_suppresses_pause_action(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(
            contracts, slack,
            paused=True,
            executor_user_id="U0BKE3KDY65",
        )
        card = pilot._build_initial_card()
        blocks = translate_rootcard_to_blocks(card)
        actions = next(b for b in blocks if b["type"] == "actions")
        labels = [e["text"]["text"] for e in actions["elements"]]
        assert "PAUSE" not in labels
        assert "STOP" in labels


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
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        # An Executor-authored but non-canonical, non-JSON reply must fail closed
        # (never silently downgraded to CONTINUE). Use the fake's Executor-enqueue
        # so the actor filter accepts it, then parse_hermes_reply rejects it.
        slack.enqueue_executor_reply(root, ExecutorReport(
            subtask_id="S1", status="RUNNING", completed=("u",),
            evidence=("e",), finding_risk=(), next_action="x", after="CONTINUE",
        ))
        # Corrupt the stored payload to non-parseable text via a fresh entry:
        slack._replies[root][-1]["reply"] = ThreadReply(
            ts=str(float(root) + 0.1), payload={"__raw_text__": "random chatter"}
        )

        def reader(last_seen_ts):
            return slack.read_thread_replies(
                pilot.config.channel, root, last_seen_ts, pilot.config.executor_user_id
            )

        with pytest.raises(MalformedReportError):
            pilot_module.run_monitoring_loop(
                pilot._selected_contract(),
                read_replies=reader,
                update_rootcard=pilot.apply_observation,
                sleeper=FakeSleeper(),
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
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        reply = (
            "🟡 EXECUTOR UPDATE · S1/3\n"
            "Status: BLOCKED\n\n"
            "Completed\n- u1\n\n"
            "Evidence\n- e1\n\n"
            "Finding / Risk\n- inherited lock mismatch\n\n"
            "Next\n→ controller release required\n\n"
            "S1 · CONTINUE"
        )
        slack.enqueue_executor_reply(root, parse_hermes_thread_update(reply))
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=lambda last_seen_ts: slack.read_thread_replies(
                pilot.config.channel, root, last_seen_ts, pilot.config.executor_user_id),
            update_rootcard=pilot.apply_observation,
            sleeper=FakeSleeper(),
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

# --------------------------------------------------------------------------- #7 unbounded loop + single identity
class TestUnboundedLiveLoop:
    """INTERCEPT #7: max_polls=None must be genuinely unbounded (poll until boundary),
    and the WP4 read path must filter by the single authoritative Executor identity.
    """

    def _authority_reply(self, subtask_id="S1", status="RUNNING", after="CONTINUE"):
        return (
            f"🟡 EXECUTOR UPDATE · {subtask_id}/3\n"
            f"Status: {status}\n"
            "Phase: x\n\n"
            "Completed\n- u\n\n"
            "Evidence\n- e\n\n"
            "Next\n→ await\n\n"
            f"{subtask_id} · {after}"
        )

    def test_max_polls_none_polls_twice_when_first_empty(self):
        """First poll empty; second poll carries the boundary -> loop returns it."""
        slack = FakeSlack()
        contracts = [_contract("S1", after=WAIT_CONTROLLER), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()

        # Inject the Executor reply only on the SECOND poll read.
        polls = {"n": 0}

        def reader(last_seen_ts):
            polls["n"] += 1
            items = slack.read_thread_replies(pilot.config.channel, root, last_seen_ts, pilot.config.executor_user_id)
            if polls["n"] < 2:
                return []  # first poll sees nothing
            slack.enqueue_executor_reply(
                root, parse_hermes_thread_update(self._authority_reply("S1", "RUNNING", "WAIT_CONTROLLER")))
            return slack.read_thread_replies(pilot.config.channel, root, last_seen_ts, pilot.config.executor_user_id)

        sleeper = FakeSleeper()
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=reader,
            update_rootcard=pilot.apply_observation,
            sleeper=sleeper,
            last_seen_ts=cmd_ts,
            max_polls=None,
        )
        assert outcome.verdict == WAIT_CONTROLLER
        assert polls["n"] == 2
        assert len(sleeper.calls) == 2
        assert slack.updates == 1  # same root, material update only once

    def test_max_polls_none_respects_boundary_from_first_poll(self):
        slack = FakeSlack()
        contracts = [_contract("S1", after=WAIT_CONTROLLER), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        slack.enqueue_executor_reply(root, parse_hermes_thread_update(self._authority_reply("S1", "RUNNING", "WAIT_CONTROLLER")))
        sleeper = FakeSleeper()
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=lambda ts: slack.read_thread_replies(pilot.config.channel, root, ts, pilot.config.executor_user_id),
            update_rootcard=pilot.apply_observation,
            sleeper=sleeper,
            last_seen_ts=cmd_ts,
            max_polls=None,
        )
        assert outcome.verdict == WAIT_CONTROLLER
        assert len(sleeper.calls) == 1

    def test_max_polls_one_exits_after_first_empty_poll(self):
        slack = FakeSlack()
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()

        polls = {"n": 0}

        def reader(last_seen_ts):
            polls["n"] += 1
            return []  # always empty -> bounded loop must give up after poll 1

        sleeper = FakeSleeper()
        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=reader,
            update_rootcard=pilot.apply_observation,
            sleeper=sleeper,
            last_seen_ts=cmd_ts,
            max_polls=1,
        )
        assert outcome.reason == REASON_MAX_POLLS
        assert polls["n"] == 1
        assert len(sleeper.calls) == 1

    def test_run_default_none_is_unbounded(self):
        slack = FakeSlack()
        contracts = [_contract("S1", after=WAIT_CONTROLLER), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, slack, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        reads = {"n": 0}

        def deferred_read(channel, root_ts, since_ts, executor_user_id=None):
            reads["n"] += 1
            if reads["n"] < 2:
                return []  # first poll: nothing yet
            slack.enqueue_executor_reply(
                root, parse_hermes_thread_update(self._authority_reply("S1", "RUNNING", "WAIT_CONTROLLER")))
            return original_read(channel, root_ts, since_ts, executor_user_id)

        original_read = slack.read_thread_replies
        slack.read_thread_replies = deferred_read
        outcome = pilot.run(max_polls=None, sleeper=FakeSleeper())
        assert outcome.verdict == WAIT_CONTROLLER
        assert reads["n"] == 2


class TestSingleExecutorIdentity:
    """Addendum to INTERCEPT #7: one authoritative Executor identity for the run.
    Identity lives at the WP5 transport boundary (SlackTransport.read_thread_replies
    takes executor_user_id); MvpPilot.run passes exactly config.executor_user_id.
    A missing identity or a mismatch between the transport-bound id and the
    read-passed id fails closed. No transport metadata leaks into the report
    payload (ThreadReply.payload stays the validated ExecutorReport mapping).
    """

    def _authority_reply(self, subtask_id="S1", status="RUNNING", after="CONTINUE"):
        return (
            f"🟡 EXECUTOR UPDATE · {subtask_id}/3\n"
            f"Status: {status}\n"
            "Phase: x\n\n"
            "Completed\n- u\n\n"
            "Evidence\n- e\n\n"
            "Next\n→ await\n\n"
            f"{subtask_id} · {after}"
        )

    def _fake_transport(self, messages):
        """A concrete WP5 transport that honors the authoritative actor filter."""

        class _Msg:
            def __init__(self, ts, text, user):
                self._d = {"ts": ts, "text": text, "user": user}

            def get(self, k, default=None):
                return self._d.get(k, default)

        class _Resp:
            def __init__(self, msgs):
                self._msgs = msgs

            def get(self, k, default=None):
                return self._msgs if k == "messages" else default

        class _Client:
            def conversations_replies(self, **kwargs):
                return _Resp(messages)

        class _Transport:  # duck-typed SlackTransport (Protocol) implementation
            def create_root(self, channel, blocks):
                validate_slack_blocks(blocks)
                return "100.0"

            def update_root(self, channel, root_ts, blocks):
                validate_slack_blocks(blocks)

            def dispatch_command(self, channel, root_ts, text, executor_user_id):
                return str(float(root_ts) + 0.05)

            def read_thread_replies(self, channel, root_ts, since_ts, executor_user_id=None):
                expected = executor_user_id
                if not expected:
                    raise TaskControllerValidationError(
                        "read_thread_replies requires a bound executor_user_id"
                    )
                out = []
                for m in messages:
                    ts = str(m.get("ts"))
                    if ts == root_ts:
                        continue
                    if since_ts is not None and pilot_module._ts_key_pilot(ts) <= pilot_module._ts_key_pilot(since_ts):
                        continue
                    if m.get("user") != expected:
                        continue
                    raw = m.get("text") or ""
                    if not raw.strip():
                        continue
                    out.append(ThreadReply(ts=ts, payload=parse_hermes_reply(raw).to_dict()))
                return out

        return _Transport()

    def test_missing_identity_fails_closed(self):
        authority = self._authority_reply()
        messages = [
            _FakeMsg("100.0", "root", "UROOT"),
            _FakeMsg("100.7", authority, "U0BKE3KDY65"),
        ]
        transport = self._fake_transport(messages)
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, transport, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()

        def reader(last_seen_ts):
            # Call WITHOUT an executor_user_id -> transport must fail closed.
            return transport.read_thread_replies(pilot.config.channel, root, last_seen_ts)

        with pytest.raises(TaskControllerValidationError):
            pilot_module.run_monitoring_loop(
                pilot._selected_contract(),
                read_replies=reader,
                update_rootcard=pilot.apply_observation,
                sleeper=FakeSleeper(),
                last_seen_ts=cmd_ts,
                max_polls=1,
            )

    def test_mismatch_between_config_and_transport_fails_closed(self):
        # SlackWebApiTransport constructed with one id, but MvpPilot.run passes a
        # different config id on read -> the transport must fail closed on mismatch.
        authority = self._authority_reply()
        messages = [
            _FakeMsg("100.0", "root", "UROOT"),
            _FakeMsg("100.7", authority, "U0BKE3KDY65"),
        ]
        transport = SlackWebApiTransport(
            _ClientWith(messages), executor_user_id="UDIFFERENT"
        )
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, transport, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()
        with pytest.raises(TaskControllerValidationError):
            pilot.run(max_polls=1, sleeper=FakeSleeper())

    def test_match_authority_identity_filters_non_executor(self):
        # Matching identity: a non-Executor author is ignored; the Executor
        # reply is accepted. The human/Controller message never reaches parsing.
        authority = self._authority_reply()
        messages = [
            _FakeMsg("100.0", "root", "UROOT"),
            _FakeMsg("100.5", "a human reply, not a report", "UHUMAN"),
            _FakeMsg("100.7", authority, "U0BKE3KDY65"),
        ]
        transport = self._fake_transport(messages)
        contracts = [_contract("S1"), _contract("S2"), _contract("S3")]
        pilot = _build_pilot(contracts, transport, active_subtask_id="S1",
                             executor_user_id="U0BKE3KDY65")
        root = pilot.ensure_root()
        cmd_ts = pilot.dispatch_current()

        def reader(last_seen_ts):
            return transport.read_thread_replies(
                pilot.config.channel, root, last_seen_ts, pilot.config.executor_user_id
            )

        outcome = pilot_module.run_monitoring_loop(
            pilot._selected_contract(),
            read_replies=reader,
            update_rootcard=pilot.apply_observation,
            sleeper=FakeSleeper(),
            last_seen_ts=cmd_ts,
            max_polls=1,
        )
        assert outcome.verdict == CONTINUE
        assert len(outcome.observations) == 1
        assert outcome.observations[0].subtask_id == "S1"


class _ClientWith:
    """Minimal conversations_replies holder for SlackWebApiTransport mismatch test."""

    def __init__(self, messages):
        self._messages = messages

    def conversations_replies(self, **kwargs):
        return {"messages": self._messages}

    def chat_postMessage(self, **kwargs):
        return {"ts": "200.0"}

    def chat_update(self, **kwargs):
        return {"ts": "100.0"}
