"""WP5 (#52) MVP pilot adapter — GPT Controller → Slack RootCard → Hermes Executor → WP4 loop.

Authority
---------
Controller release WP5 binds the WP1 contract/report, WP2 RootCard, WP3 public
actions and WP4 60s monitoring loop into one narrow in-session pilot path:

    GPT Controller -> one Slack RootCard/thread -> Hermes main Executor
    -> structured milestone report -> WP4 60s loop

Hard rules upheld (same as every other MVP module):

1. PURE DOMAIN. No Slack SDK, no Hermes SDK, no network at import or in the
   default path. Transport is behind injected ``SlackTransport`` /
   ``HermesExecutorClient`` protocols; the deterministic fakes are the MVP CI
   path. Any *real* client is imported LAZILY inside its constructor, so merely
   importing this module never pulls a transport/network dependency.
2. ONE ROOT. ``ensure_root`` calls ``create_root`` exactly once; every later
   update (including model / session / executor rotation) calls ``update_root``
   on the same bound ``root_ts``. Rotation is projection content, never a second
   root.
3. ONLY THE SELECTED CURRENT SUBTASK. The executor is dispatched the *single*
   active contracted subtask and the exact reporting contract. No rejected
   options, no history, no noise. Progression to the next milestone is
   Controller-gated; a CONTINUE never invents an uncontracted subtask.
3b. FULL-E2E DEFAULT OFF. Any advanced capability (lease / journal / recovery /
    routing / takeover / multi-executor / host pack / controlplane) requires an
    explicit positive ``advanced_mode=True`` opt-in and cannot redefine the MVP
    public action semantics. ``_require_advanced`` guards every such path.
4. FAIL CLOSED. A malformed Hermes reply raises ``MalformedReportError`` and is
   never downgraded to CONTINUE.

Slack Block Kit hard contract (Context7 / current Slack docs)
------------------------------------------------------------
WP2 emits a *domain* payload (``plan_block`` / ``task_cards`` / uppercase
statuses) which is NOT Slack-valid. This module translates to the official
schema at the adapter boundary and validates it:

* official Plan block:    ``type="plan"``, required ``title``, optional ``tasks``
* official Task Card:     ``type="task_card"``, required ``task_id``, ``title``,
                          ``status``
* task status exact set:  ``pending | in_progress | complete | error``

Domain -> Slack status mapping (the distinction BLOCKED vs FAILED is preserved
in the task card ``details`` field, because both collapse to ``error``):

    PENDING     -> pending
    IN_PROGRESS -> in_progress
    DONE        -> complete
    BLOCKED     -> error   (details: "BLOCKED")
    FAILED      -> error   (details: "FAILED")
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Protocol, Sequence

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.mvp.monitoring import (
    CONTINUE,
    TERMINAL,
    WAIT_CONTROLLER,
    LoopObservation,
    ProtocolVerdict,
    ThreadReply,
    run_monitoring_loop,
)
from taskcontroller.mvp.protocol_bridge import (
    CONTRACTED_AFTER_VALUES,
    ContractedSubtask,
    ExecutorReport,
    REPORT_STATUSES,
)
from taskcontroller.mvp.rootcard import (
    COST_UNKNOWN,
    PlanBlock,
    RootCard,
    TaskCard,
    TaskCardStatus,
)

# ---------------------------------------------------------------------------
# Slack status translation (adapter boundary)
# ---------------------------------------------------------------------------
SLACK_TASK_STATUSES = ("pending", "in_progress", "complete", "error")

DOMAIN_TO_SLACK_STATUS = {
    TaskCardStatus.PENDING: "pending",
    TaskCardStatus.IN_PROGRESS: "in_progress",
    TaskCardStatus.DONE: "complete",
    TaskCardStatus.BLOCKED: "error",
    TaskCardStatus.FAILED: "error",
}

#: report.status (WP1) -> domain TaskCardStatus (WP2)
REPORT_TO_CARD_STATUS = {
    "RUNNING": TaskCardStatus.IN_PROGRESS,
    "DONE": TaskCardStatus.DONE,
    "BLOCKED": TaskCardStatus.BLOCKED,
    "FAILED": TaskCardStatus.FAILED,
}


def to_slack_task_status(domain_status: str) -> str:
    """Map a domain TaskCardStatus to the exact Slack task_card status."""
    if domain_status not in DOMAIN_TO_SLACK_STATUS:
        raise TaskControllerValidationError(
            f"unknown domain task status: {domain_status!r}"
        )
    return DOMAIN_TO_SLACK_STATUS[domain_status]


def report_status_to_card_status(report_status: str) -> str:
    """Map a WP1 ExecutorReport status to a WP2 TaskCardStatus."""
    if report_status not in REPORT_TO_CARD_STATUS:
        raise TaskControllerValidationError(
            f"unknown report status: {report_status!r}"
        )
    return REPORT_TO_CARD_STATUS[report_status]


# ---------------------------------------------------------------------------
# Block Kit validation (adapter boundary — never trust the domain payload)
# ---------------------------------------------------------------------------
def validate_slack_blocks(blocks: Sequence[Mapping[str, Any]]) -> None:
    """Validate a Block Kit payload against the official plan/task_card schema.

    Raises ``TaskControllerValidationError`` on the first violation. Root
    operational metadata (section / context / rich_text / header) only needs a
    valid ``type``; the strict rules apply to ``plan`` and ``task_card``.
    """
    if not isinstance(blocks, (list, tuple)):
        raise TaskControllerValidationError("blocks must be a list/tuple")
    for idx, block in enumerate(blocks):
        if not isinstance(block, Mapping) or "type" not in block:
            raise TaskControllerValidationError(f"block[{idx}] missing 'type'")
        btype = block["type"]
        if btype == "plan":
            if not isinstance(block.get("title"), str) or not block["title"].strip():
                raise TaskControllerValidationError(
                    f"plan block[{idx}] requires non-empty string 'title'"
                )
            tasks = block.get("tasks")
            if tasks is not None and not isinstance(tasks, (list, tuple)):
                raise TaskControllerValidationError(
                    f"plan block[{idx}] 'tasks' must be a list"
                )
            for j, task in enumerate(tasks or []):
                if not isinstance(task, Mapping) or task.get("type") != "task_card":
                    raise TaskControllerValidationError(
                        f"plan.tasks[{j}] must be type 'task_card'"
                    )
                for req in ("task_id", "title", "status"):
                    if not isinstance(task.get(req), str) or not task[req].strip():
                        raise TaskControllerValidationError(
                            f"task_card[{j}] requires non-empty '{req}'"
                        )
                if task["status"] not in SLACK_TASK_STATUSES:
                    raise TaskControllerValidationError(
                        f"task_card[{j}] status must be one of "
                        f"{SLACK_TASK_STATUSES}, got {task['status']!r}"
                    )
        elif btype == "actions":
            elements = block.get("elements")
            if not isinstance(elements, (list, tuple)) or not elements:
                raise TaskControllerValidationError(
                    f"actions block[{idx}] requires non-empty 'elements'"
                )
            for j, el in enumerate(elements):
                if not isinstance(el, Mapping) or el.get("type") != "button":
                    raise TaskControllerValidationError(
                        f"actions.elements[{j}] must be type 'button'"
                    )
                if not isinstance(el.get("action_id"), str) or not el["action_id"]:
                    raise TaskControllerValidationError(
                        f"actions.elements[{j}] requires 'action_id'"
                    )
                text = el.get("text")
                if (
                    not isinstance(text, Mapping)
                    or text.get("type") != "plain_text"
                    or not isinstance(text.get("text"), str)
                ):
                    raise TaskControllerValidationError(
                        f"actions.elements[{j}] requires plain_text 'text'"
                    )


# ---------------------------------------------------------------------------
# Public action -> Block Kit button (WP3 vocabulary)
# ---------------------------------------------------------------------------
_ACTION_BUTTONS = (
    ("PAUSE", "pause"),
    ("STOP", "stop"),
    ("APPROVE", "approve"),
    ("MERGE", "merge"),
)


def _action_block() -> dict[str, Any]:
    return {
        "type": "actions",
        "block_id": "mvp_actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": label},
                "action_id": action_id,
                "value": label,
            }
            for label, action_id in _ACTION_BUTTONS
        ],
    }


# ---------------------------------------------------------------------------
# RootCard -> Slack blocks translator
# ---------------------------------------------------------------------------
def translate_rootcard_to_blocks(card: RootCard) -> list[dict[str, Any]]:
    """Translate a WP2 RootCard into VALID Slack Block Kit blocks.

    The WP2 domain payload (``plan_block`` / uppercase statuses) is deliberately
    NOT Slack-valid; this produces the official ``plan`` / ``task_card`` schema
    with the exact status mapping, plus section/context metadata and WP3 action
    buttons.
    """
    if not isinstance(card, RootCard):
        raise TaskControllerValidationError("translate requires a RootCard")

    header = {
        "type": "rich_text",
        "block_id": "mvp_header",
        "elements": [
            {
                "type": "rich_text_section",
                "elements": [{"type": "text", "text": f"Run {card.run_id}"}],
            }
        ],
    }
    meta = {
        "type": "section",
        "block_id": "mvp_meta",
        "fields": [
            {"type": "mrkdwn", "text": f"*owner:* {card.human_owner}"},
            {"type": "mrkdwn", "text": f"*controller:* {card.controller}"},
            {"type": "mrkdwn", "text": f"*executor:* {card.executor}"},
            {
                "type": "mrkdwn",
                "text": f"*active:* {card.active_subtask_id} ({card.progress})",
            },
        ],
    }
    plan_block: dict[str, Any] = {
        "type": "plan",
        "title": f"Plan — Run {card.run_id}",
        "tasks": [],
    }
    for card_item in card.plan.cards:
        slack_status = to_slack_task_status(card_item.status)
        task: dict[str, Any] = {
            "type": "task_card",
            "task_id": card_item.subtask_id,
            "title": card_item.objective,
            "status": slack_status,
        }
        # Preserve the BLOCKED/FAILED distinction when status collapses to error.
        if slack_status == "error":
            task["details"] = card_item.status  # domain "BLOCKED" / "FAILED"
        plan_block["tasks"].append(task)

    context_lines = [f"*now:* {card.now}", f"*next:* {card.next}"]
    if card.risk:
        context_lines.append(f"*risk:* {card.risk}")
    if card.last_material_update:
        context_lines.append(f"*last material update:* {card.last_material_update}")
    if card.branch:
        context_lines.append(f"*branch:* {card.branch}")
    if card.pr:
        context_lines.append(f"*pr:* {card.pr}")
    if card.head_sha:
        context_lines.append(f"*head:* {card.head_sha}")
    if card.ci_status:
        context_lines.append(f"*ci:* {card.ci_status}")
    context = {
        "type": "context",
        "block_id": "mvp_context",
        "elements": [
            {"type": "mrkdwn", "text": line} for line in context_lines
        ],
    }
    return [header, meta, plan_block, context, _action_block()]


# ---------------------------------------------------------------------------
# Transport protocols (narrow; fakes are the MVP CI path)
# ---------------------------------------------------------------------------
class SlackTransport(Protocol):
    """Narrow Slack transport: one root, in-place updates, incremental reads."""

    def create_root(self, channel: str, blocks: Sequence[Mapping[str, Any]]) -> str:
        """Create the single root message; returns its ts."""
        ...

    def update_root(
        self, channel: str, root_ts: str, blocks: Sequence[Mapping[str, Any]]
    ) -> None:
        """Update the bound root message in place."""
        ...

    def post_thread_reply(self, channel: str, root_ts: str, text: str) -> str:
        """Post a structured milestone reply into the root thread; returns ts."""
        ...

    def read_thread_replies(
        self, channel: str, root_ts: str, since_ts: str | None
    ) -> list[ThreadReply]:
        """Read thread replies strictly newer than ``since_ts``."""
        ...


class HermesExecutorClient(Protocol):
    """Narrow Hermes main-Executor dispatch interface.

    One main Executor per run by default. Retries / model / session changes MUST
    stay on the same root/thread — that is the caller's responsibility (the pilot
    keeps the bound ``root_ts``); this client only returns a structured reply for
    the dispatched subtask.
    """

    def dispatch(self, subtask: ContractedSubtask) -> str:
        """Return the structured milestone reply text for one subtask."""
        ...


def parse_hermes_reply(text: str | Mapping[str, Any]) -> ExecutorReport:
    """Parse a Hermes milestone reply into a COMPLETE WP1 ExecutorReport.

    Fail closed: missing or invalid fields raise ``MalformedReportError`` (never
    silently downgraded to CONTINUE).
    """
    if isinstance(text, Mapping):
        payload: Mapping[str, Any] = text
    else:
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise MalformedReportError(
                f"Hermes reply is not valid JSON: {exc}"
            ) from exc
    if not isinstance(payload, Mapping):
        raise MalformedReportError("Hermes reply payload must be an object")
    try:
        return ExecutorReport.from_payload(dict(payload))
    except TaskControllerValidationError as exc:
        raise MalformedReportError(f"incomplete Hermes reply: {exc}") from exc


# ---------------------------------------------------------------------------
# Advanced-mode guard (Full-E2E default OFF)
# ---------------------------------------------------------------------------
class AdvancedModeRequired(TaskControllerValidationError):
    """Raised when an advanced Full-E2E capability is used without opt-in."""


FORBIDDEN_DEFERRED_IMPORTS = (
    "lease",
    "journal",
    "recovery",
    "routing",
    "takeover",
    "controlplane",
    "hostpack",
    "host_pack",
)


def _require_advanced(advanced_mode: bool, capability: str) -> None:
    if not advanced_mode:
        raise AdvancedModeRequired(
            f"{capability} requires advanced_mode=True opt-in; MVP default is OFF"
        )


def module_keeps_deferred_core_out(
    path_or_source: str = __file__,
    forbidden: Sequence[str] = FORBIDDEN_DEFERRED_IMPORTS,
) -> bool:
    """AST proof: this module never imports deferred Full-E2E core modules."""
    import os

    raw = path_or_source
    if os.path.isfile(path_or_source):  # a file path -> read its source
        with open(path_or_source, "r", encoding="utf-8") as fh:
            raw = fh.read()
    tree = ast.parse(raw)
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Import):
            targets = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            targets = [node.module or ""]
        for target in targets:
            for frag in forbidden:
                if frag in target.split("."):
                    return False
    return True


# ---------------------------------------------------------------------------
# The pilot engine
# ---------------------------------------------------------------------------
@dataclass
class MvpPilotConfig:
    """Immutable configuration for one MVP run (one root, one main Executor)."""

    run_id: str
    channel: str
    human_owner: str
    controller: str
    executor: str
    contracts: tuple[ContractedSubtask, ...]
    slack: SlackTransport
    hermes: HermesExecutorClient
    root_ts: str | None = None
    active_subtask_id: str | None = None
    executor_model: str | None = None
    token_usage: int | None = None
    branch: str | None = None
    pr: str | None = None
    head_sha: str | None = None
    ci_status: str | None = None
    risk: str | None = None
    advanced_mode: bool = False


@dataclass
class MvpPilot:
    """Binds WP1..WP4 into the live GPT→Slack→Hermes→loop path.

    One root. One main Executor. Only the selected current subtask is dispatched.
    Material observations update the same RootCard in place.
    """

    config: MvpPilotConfig
    _root_ts: str | None = field(default=None, init=False)
    _card: RootCard | None = field(default=None, init=False)
    _plan: PlanBlock | None = field(default=None, init=False)

    # -- construction -------------------------------------------------------
    def _active_subtask_id(self) -> str:
        if self.config.active_subtask_id:
            return self.config.active_subtask_id
        return self.config.contracts[0].subtask_id

    def _selected_contract(self) -> ContractedSubtask:
        wanted = self._active_subtask_id()
        for contract in self.config.contracts:
            if contract.subtask_id == wanted:
                return contract
        raise TaskControllerValidationError(
            f"active subtask {wanted!r} is not in the contracted plan"
        )

    def _build_initial_card(self) -> RootCard:
        contracts = self.config.contracts
        plan = PlanBlock.from_contracts(contracts)
        active = self._active_subtask_id()
        card = RootCard(
            run_id=self.config.run_id,
            human_owner=self.config.human_owner,
            controller=self.config.controller,
            executor=self.config.executor,
            plan=plan,
            active_subtask_id=active,
            now="RUNNING",
            next="await controller",
            last_material_update="root created",
            executor_model=self.config.executor_model,
            token_usage=self.config.token_usage,
            branch=self.config.branch,
            pr=self.config.pr,
            head_sha=self.config.head_sha,
            ci_status=self.config.ci_status,
            risk=self.config.risk,
        )
        return card

    # -- one-root invariant ------------------------------------------------
    def ensure_root(self) -> str:
        """Establish the single root. CREATE_ROOT exactly once; else UPDATE_ROOT.

        Rotation (model / session / executor) only ever calls this again and
        MUST keep the same ``root_ts`` (it cannot create a second root).
        """
        if self._root_ts is not None:
            return self._root_ts  # already bound -> no second CREATE_ROOT
        if self.config.root_ts is not None:
            self._root_ts = self.config.root_ts
            return self._root_ts
        if self._card is None:
            self._card = self._build_initial_card()
            self._plan = self._card.plan
        blocks = translate_rootcard_to_blocks(self._card)
        validate_slack_blocks(blocks)
        self._root_ts = self.config.slack.create_root(self.config.channel, blocks)
        return self._root_ts

    # -- dispatch only the selected current subtask ------------------------
    def dispatch_current(self) -> ExecutorReport:
        """Dispatch ONLY the selected current contracted subtask to Hermes."""
        subtask = self._selected_contract()
        reply = self.config.hermes.dispatch(subtask)  # structured reply
        report = parse_hermes_reply(reply)  # fail closed if incomplete
        return report

    # -- map LoopObservation -> same RootCard in place --------------------
    def apply_observation(self, observation: LoopObservation) -> None:
        """Update the bound RootCard from a material observation, in place.

        Called by the WP4 loop ONLY on a material change. Maps the WP1 report
        fields into WP2 progress / risk / Now / Next and re-posts to the SAME
        root. Never creates a second root.
        """
        if self._card is None:
            self._card = self._build_initial_card()
            self._plan = self._card.plan
        report = observation.report
        new_card_status = report_status_to_card_status(report.status)
        active = self._active_subtask_id()

        def _remap(plan: PlanBlock) -> PlanBlock:
            updated = []
            for c in plan.cards:
                if c.subtask_id == active:
                    updated.append(
                        replace(
                            c,
                            status=new_card_status,
                            detail=(
                                "; ".join(report.completed) if report.completed else None
                            ),
                        )
                    )
                else:
                    updated.append(c)
            return replace(plan, cards=tuple(updated))

        new_plan = _remap(self._card.plan)
        new_card = replace(
            self._card,
            plan=new_plan,
            now=report.status,
            next=report.next_action,
            risk=(report.finding_risk[0] if report.finding_risk else self._card.risk),
            last_material_update=(
                report.evidence[-1]
                if report.evidence
                else self._card.last_material_update
            ),
        )
        self._card = new_card
        self._plan = new_plan
        root_ts = self.ensure_root()  # keep same root
        blocks = translate_rootcard_to_blocks(new_card)
        validate_slack_blocks(blocks)
        self.config.slack.update_root(self.config.channel, root_ts, blocks)

    # -- convenience orchestration -----------------------------------------
    def run(
        self,
        max_polls: int = 1,
        sleeper: Callable[[int], None] | None = None,
    ) -> Any:
        """One in-session pilot pass: ensure root, dispatch, feed WP4 loop."""
        root_ts = self.ensure_root()
        report = self.dispatch_current()
        # Post the structured report into the thread so the loop can read it.
        reply_ts = self.config.slack.post_thread_reply(
            self.config.channel, root_ts, json.dumps(report.to_dict())
        )

        def reader(last_seen_ts: str | None) -> Sequence[ThreadReply]:
            return self.config.slack.read_thread_replies(
                self.config.channel, root_ts, last_seen_ts
            )

        outcome = run_monitoring_loop(
            self._selected_contract(),
            read_replies=reader,
            update_rootcard=self.apply_observation,
            sleeper=sleeper or _noop_sleeper,
            last_seen_ts=root_ts,
            max_polls=max_polls,
        )
        return outcome


def _noop_sleeper(_: int) -> None:
    return None


# Re-export for convenience.
__all__ = [
    "SLACK_TASK_STATUSES",
    "DOMAIN_TO_SLACK_STATUS",
    "REPORT_TO_CARD_STATUS",
    "to_slack_task_status",
    "report_status_to_card_status",
    "validate_slack_blocks",
    "translate_rootcard_to_blocks",
    "parse_hermes_reply",
    "SlackTransport",
    "HermesExecutorClient",
    "AdvancedModeRequired",
    "module_keeps_deferred_core_out",
    "MvpPilotConfig",
    "MvpPilot",
]


# Imported last so the public names above are defined before any helper use.
from taskcontroller.mvp.monitoring import MalformedReportError  # noqa: E402
