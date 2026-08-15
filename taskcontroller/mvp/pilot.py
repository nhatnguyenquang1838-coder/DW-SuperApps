"""WP5 (#52) MVP pilot adapter — GPT Controller → Slack → Hermes Executor → WP4 loop.

Authority
---------
Controller release WP5 binds the WP1 contract/report, WP2 RootCard, WP3 public
actions and WP4 60s monitoring loop into one narrow in-session pilot path that
faithfully reproduces the *live Slack-mediated* topology:

    GPT Controller -> one Slack RootCard/thread
        -> Controller dispatches the selected contract/command INTO the thread
           (addressed to the configured Hermes Executor); returns only a
           dispatch receipt/ts, NOT the Executor report
        -> Hermes Executor (separate actor) reads the command and posts its own
           Executor-authored reply later in the thread
        -> WP4 60s loop reads only the Executor-authored reply (strictly newer
           than the pre-dispatch cursor) and classifies it

Hard rules upheld (same as every other MVP module):

1. PURE DOMAIN. No Slack SDK, no Hermes SDK, no network at import or in the
   default path. Transport is behind injected ``SlackTransport`` /
   ``HermesExecutorClient`` protocols; the deterministic fakes are the MVP CI
   path. Any *real* client (``SlackWebApiTransport``) is constructed with an
   injected Web API client/duck type and never imports or stores a token.
2. ONE ROOT. ``ensure_root`` calls ``create_root`` exactly once; every later
   update (including model / session / executor rotation) calls ``update_root``
   on the same bound ``root_ts``. Rotation is projection content, never a second
   root.
3. ONLY THE SELECTED CURRENT SUBTASK. The Controller dispatches the *single*
   active contracted subtask and the exact reporting contract into the thread.
   A CONTINUE never invents an uncontracted subtask. The Executor's reply is
   classified only against the selected subtask; a reply claiming a different
   subtask is a drift (INTERCEPT).
3b. FULL-E2E DEFAULT OFF. Any advanced capability requires an explicit positive
    ``advanced_mode=True`` opt-in. ``_require_advanced`` guards every such path.
4. FAIL CLOSED. A malformed Hermes reply (JSON or canonical text) raises
   ``MalformedReportError`` and is never downgraded to CONTINUE.
5. NO HARDCODED IDENTITY. The Executor identity is bound through configuration
   (``executor_user_id``); no current-user ID is hardcoded in library code.

Slack Block Kit hard contract (Context7 / current Slack docs)
------------------------------------------------------------
WP2 emits a *domain* payload (``plan_block`` / ``task_cards`` / uppercase
statuses) which is NOT Slack-valid. This module translates to the official
schema at the adapter boundary and validates it:

* official Plan block:    ``type="plan"``, required ``title``, optional ``tasks``
* official Task Card:     ``type="task_card"``, required ``task_id``, ``title``,
                          ``status``; ``details`` (if present) MUST be a
                          ``rich_text`` entity (current Slack schema) — a raw
                          string is invalid
* task status exact set:  ``pending | in_progress | complete | error``
* contextual actions:     only ``card.contextual_actions()`` are ever rendered;
                          APPROVE only at an exact authority boundary; MERGE only
                          when merge-ready with an exact bound PR/head
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Protocol, Sequence

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.mvp.monitoring import (
    CONTINUE,
    TERMINAL,
    WAIT_CONTROLLER,
    LoopObservation,
    MalformedReportError,
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
    PUBLIC_ROOTCARD_ACTIONS,
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
#: A valid task_card ``details`` element MUST be a rich_text entity.
def _is_rich_text_entity(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("type") == "rich_text"
        and isinstance(value.get("elements"), (list, tuple))
    )


#: Valid WP3 public action_ids (mirrors rootcard.PUBLIC_ROOTCARD_ACTIONS order).
_VALID_ACTION_IDS = frozenset({"pause", "stop", "approve", "merge"})


def validate_slack_blocks(blocks: Sequence[Mapping[str, Any]]) -> None:
    """Validate a Block Kit payload against the official plan/task_card schema.

    Raises ``TaskControllerValidationError`` on the first violation. Operational
    metadata (section / context / rich_text / header) only needs a valid
    ``type``; strict rules apply to ``plan`` and ``task_card``. A ``task_card``
    ``details`` field, when present, MUST be a ``rich_text`` entity (a raw
    string is invalid per the current Slack schema). Action buttons may only be
    the four WP3 public actions.
    """
    if not isinstance(blocks, (list, tuple)):
        raise TaskControllerValidationError("blocks must be a list/tuple")
    for idx, block in enumerate(blocks):
        if not isinstance(block, Mapping) or "type" not in block:
            raise TaskControllerValidationError(f"block[{idx}] missing 'type'")
        btype = block["type"]
        if btype == "plan":
            _validate_plan_block(block, idx)
        elif btype == "actions":
            _validate_actions_block(block, idx)


def _validate_plan_block(block: Mapping[str, Any], idx: int) -> None:
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
        if "details" in task and not _is_rich_text_entity(task["details"]):
            raise TaskControllerValidationError(
                f"task_card[{j}] 'details' must be a rich_text entity, "
                f"got {type(task['details']).__name__}"
            )


def _validate_actions_block(block: Mapping[str, Any], idx: int) -> None:
    elements = block.get("elements")
    if not isinstance(elements, (list, tuple)) or not elements:
        raise TaskControllerValidationError(
            f"actions block[{idx}] requires non-empty 'elements'"
        )
    allowed = set(PUBLIC_ROOTCARD_ACTIONS)
    for j, el in enumerate(elements):
        if not isinstance(el, Mapping) or el.get("type") != "button":
            raise TaskControllerValidationError(
                f"actions.elements[{j}] must be type 'button'"
            )
        action_id = el.get("action_id")
        if not isinstance(action_id, str) or action_id not in _VALID_ACTION_IDS:
            raise TaskControllerValidationError(
                f"actions.elements[{j}] invalid action_id {action_id!r}; "
                f"only WP3 public actions allowed"
            )
        # the rendered label must be a recognised public action
        text = el.get("text")
        if not isinstance(text, Mapping) or text.get("type") != "plain_text":
            raise TaskControllerValidationError(
                f"actions.elements[{j}] requires plain_text 'text'"
            )
        if text.get("text") not in allowed:
            raise TaskControllerValidationError(
                f"actions.elements[{j}] label {text.get('text')!r} is not a "
                f"WP3 public action"
            )


# ---------------------------------------------------------------------------
# RootCard -> Slack blocks translator (WP2 domain -> official Block Kit)
# ---------------------------------------------------------------------------
def _rich_text_details(label: str, body: str) -> dict[str, Any]:
    """A valid rich_text details entity for an error task_card.

    ``label`` is the exact domain status (``BLOCKED`` / ``FAILED``); ``body``
    carries the human reason. Per the current Slack schema, ``details`` MUST be
    a rich_text entity — a raw string is invalid.
    """
    return {
        "type": "rich_text",
        "elements": [
            {
                "type": "rich_text_section",
                "elements": [
                    {"type": "text", "text": f"{label}: "},
                    {"type": "text", "text": body, "style": {"bold": True}},
                ],
            }
        ],
    }


def _action_block(actions: Sequence[str]) -> dict[str, Any]:
    """Render ONLY the supplied contextual public actions as WP3 buttons."""
    # PUBLIC_ROOTCARD_ACTIONS preserves exact MVP API order; render in that order.
    ordered = [a for a in PUBLIC_ROOTCARD_ACTIONS if a in actions]
    return {
        "type": "actions",
        "block_id": "mvp_actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": label},
                "action_id": label.lower(),
                "value": label,
            }
            for label in ordered
        ],
    }


def translate_rootcard_to_blocks(card: RootCard) -> list[dict[str, Any]]:
    """Translate a WP2 RootCard into VALID Slack Block Kit blocks.

    The WP2 domain payload (``plan_block`` / uppercase statuses / raw string
    details) is deliberately NOT Slack-valid; this produces the official
    ``plan`` / ``task_card`` schema with the exact status mapping, plus complete
    operational metadata and ONLY the contextual public actions.
    """
    if not isinstance(card, RootCard):
        raise TaskControllerValidationError("translate requires a RootCard")

    header = {
        "type": "rich_text",
        "block_id": "mvp_header",
        "elements": [
            {
                "type": "rich_text",
                "elements": [{"type": "text", "text": f"Run {card.run_id}"}],
            }
        ],
    }

    # -- operational metadata (complete WP2 live fields) --------------------
    meta_fields: list[dict[str, str]] = [
        {"type": "mrkdwn", "text": f"*owner:* {card.human_owner}"},
        {"type": "mrkdwn", "text": f"*controller:* {card.controller}"},
        {"type": "mrkdwn", "text": f"*executor:* {card.executor}"},
    ]
    if card.watcher:
        meta_fields.append({"type": "mrkdwn", "text": f"*watcher:* {card.watcher}"})
    if card.executor_model:
        meta_fields.append(
            {"type": "mrkdwn", "text": f"*model:* {card.executor_model}"}
        )
    meta_fields.append(
        {"type": "mrkdwn", "text": f"*tokens:* {card.token_usage_display}"}
    )
    meta_fields.append({"type": "mrkdwn", "text": f"*cost:* {card.cost}"})
    if card.gwc_active and card.gate_journey:
        meta_fields.append(
            {"type": "mrkdwn", "text": f"*journey:* {card.gate_journey}"}
        )
    meta_fields.append(
        {
            "type": "mrkdwn",
            "text": f"*active:* {card.active_subtask_id} ({card.progress})",
        }
    )
    if card.branch:
        meta_fields.append({"type": "mrkdwn", "text": f"*branch:* {card.branch}"})
    if card.pr:
        meta_fields.append({"type": "mrkdwn", "text": f"*pr:* {card.pr}"})
    if card.head_sha:
        meta_fields.append({"type": "mrkdwn", "text": f"*head:* {card.head_sha}"})
    if card.ci_status:
        meta_fields.append({"type": "mrkdwn", "text": f"*ci:* {card.ci_status}"})
    meta = {"type": "section", "block_id": "mvp_meta", "fields": meta_fields}

    # -- explicit plan / task cards ----------------------------------------
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
        # Preserve the BLOCKED/FAILED distinction via a valid rich_text entity.
        if slack_status == "error":
            reason = card_item.detail or card_item.status
            task["details"] = _rich_text_details(card_item.status, reason)
        plan_block["tasks"].append(task)

    # -- context: now/next/risk/delivery -----------------------------------
    context_lines = [f"*now:* {card.now}", f"*next:* {card.next}"]
    if card.risk:
        context_lines.append(f"*risk:* {card.risk}")
    if card.last_material_update:
        context_lines.append(f"*last material update:* {card.last_material_update}")
    context = {
        "type": "context",
        "block_id": "mvp_context",
        "elements": [{"type": "mrkdwn", "text": line} for line in context_lines],
    }

    return [header, meta, plan_block, context, _action_block(card.contextual_actions())]


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

    def dispatch_command(
        self, channel: str, root_ts: str, text: str, executor_user_id: str
    ) -> str:
        """Post the Controller command addressed to the Executor; returns its ts.

        This is the *command* message — distinct from the Executor's later
        reply. The WP4 loop reads only replies strictly newer than this ts.
        """
        ...

    def read_thread_replies(
        self, channel: str, root_ts: str, since_ts: str | None
    ) -> list[ThreadReply]:
        """Read thread replies strictly newer than ``since_ts``."""
        ...


class HermesExecutorClient(Protocol):
    """Narrow Hermes main-Executor dispatch interface.

    By MVP design the Executor is a *separate actor* that reads the dispatched
    command from the Slack thread and posts its own reply. The pilot never sees
    the report directly through this client in the live topology; the reply is
    observed through the Slack transport. A test-only synchronous helper may
    still expose a direct structured reply, but it MUST NOT define the
    production MVP topology.
    """

    def dispatch(self, subtask: ContractedSubtask) -> str:
        """Return the structured milestone reply text for one subtask (test only)."""
        ...


# ---------------------------------------------------------------------------
# C. Canonical human-readable Executor report parsing
# ---------------------------------------------------------------------------
#: Canonical MVP Slack Executor update markers (case-insensitive line headers).
_CANONICAL_FIELDS = {
    "subtask_id": "subtask_id",
    "subtask": "subtask_id",
    "status": "status",
    "completed": "completed",
    "evidence": "evidence",
    "finding/risk": "finding_risk",
    "finding": "finding_risk",
    "risk": "finding_risk",
    "next": "next_action",
    "after": "after",
}
_CANONICAL_HEADER = re.compile(r"^\s*executor\s+update", re.IGNORECASE)
_STATUS_WORDS = {
    "running": "RUNNING",
    "done": "DONE",
    "blocked": "BLOCKED",
    "failed": "FAILED",
}
_AFTER_WORDS = {v.lower(): v for v in CONTRACTED_AFTER_VALUES}


def _norm_header(line: str) -> str | None:
    m = re.match(r"^\s*([A-Za-z/]+)\s*[:\-]\s*(.*)$", line)
    if not m:
        return None
    key = m.group(1).lower()
    return key


def parse_hermes_thread_update(text: str) -> ExecutorReport:
    """Parse the canonical human-readable MVP Slack Executor update.

    Format (one header per line, order-independent except the header line):

        EXECUTOR UPDATE
        Status: RUNNING
        Completed: unit one; unit two
        Evidence: exact evidence
        Finding/Risk: inherited lock mismatch
        Next: controller release required
        After: CONTINUE

    Fail closed: missing required fields, ambiguous status/after, or a missing
    header line raise ``MalformedReportError`` (never CONTINUE).
    """
    if not isinstance(text, str) or not text.strip():
        raise MalformedReportError("empty Hermes thread update")
    if not _CANONICAL_HEADER.search(text):
        raise MalformedReportError(
            "Hermes thread update must begin with an 'EXECUTOR UPDATE' header"
        )

    collected: dict[str, list[str]] = {}
    for raw in text.splitlines():
        key = _norm_header(raw)
        if key is None:
            continue
        mapped = _CANONICAL_FIELDS.get(key)
        if mapped is None:
            continue
        value = raw.split(":", 1)[1].strip() if ":" in raw else ""
        collected.setdefault(mapped, []).append(value)

    def _join(field: str) -> str:
        parts = [p for p in collected.get(field, []) if p]
        return "; ".join(parts)

    # status
    status_raw = _join("status")
    status = _STATUS_WORDS.get(status_raw.strip().lower())
    if status is None or status not in REPORT_STATUSES:
        raise MalformedReportError(
            f"Hermes thread update has ambiguous/missing status: {status_raw!r}"
        )

    after_raw = _join("after")
    after = _AFTER_WORDS.get(after_raw.strip().lower())
    if after is None or after not in CONTRACTED_AFTER_VALUES:
        raise MalformedReportError(
            f"Hermes thread update has ambiguous/missing After: {after_raw!r}"
        )

    subtask_id = _join("subtask_id") or ""
    if not subtask_id:
        raise MalformedReportError("Hermes thread update missing subtask_id")

    completed = tuple(c.strip() for c in _join("completed").split(";") if c.strip())
    evidence = tuple(e.strip() for e in _join("evidence").split(";") if e.strip())
    finding_risk = tuple(
        f.strip() for f in _join("finding_risk").split(";") if f.strip()
    )
    next_action = _join("next_action") or "await controller"

    try:
        return ExecutorReport(
            subtask_id=subtask_id,
            status=status,
            completed=completed,
            evidence=evidence,
            finding_risk=finding_risk,
            next_action=next_action,
            after=after,
        )
    except TaskControllerValidationError as exc:
        raise MalformedReportError(f"incomplete Hermes thread update: {exc}") from exc


def parse_hermes_reply(text: str | Mapping[str, Any]) -> ExecutorReport:
    """Parse a Hermes milestone reply into a COMPLETE WP1 ExecutorReport.

    Accepts either a JSON/mapping payload or the canonical human-readable Slack
    text (``EXECUTOR UPDATE`` …). Fail closed: incomplete or ambiguous input
    raises ``MalformedReportError`` (never silently downgraded to CONTINUE).
    """
    if isinstance(text, Mapping):
        payload: Mapping[str, Any] = text
    elif isinstance(text, str):
        stripped = text.strip()
        # Try the canonical human-readable form first when it has the header.
        if _CANONICAL_HEADER.search(stripped):
            return parse_hermes_thread_update(stripped)
        try:
            payload = json.loads(stripped)
        except (json.JSONDecodeError, TypeError) as exc:
            raise MalformedReportError(
                f"Hermes reply is neither valid JSON nor a canonical update: {exc}"
            ) from exc
    else:
        raise MalformedReportError("Hermes reply must be a string or mapping")

    if not isinstance(payload, Mapping):
        raise MalformedReportError("Hermes reply payload must be an object")
    try:
        return ExecutorReport.from_payload(dict(payload))
    except TaskControllerValidationError as exc:
        raise MalformedReportError(f"incomplete Hermes reply: {exc}") from exc


# ---------------------------------------------------------------------------
# B. Concrete Slack Web API transport wrapper
# ---------------------------------------------------------------------------
class SlackWebApiTransport:
    """Concrete Slack transport over an injected Web API client/duck type.

    The injected ``client`` is expected to expose the standard WebClient method
    surface (``chat_postMessage``, ``chat_update``, ``conversations_replies``).
    No token/secret is stored or logged; the client is supplied by the caller.
    No network call occurs at construction, and ``slack_sdk`` is never imported
    here (the duck type only needs the method surface). CI never instantiates
    this class; the deterministic fakes are the MVP path.
    """

    def __init__(self, client: Any, fallback_text: str = "") -> None:
        if client is None:
            raise TaskControllerValidationError(
                "SlackWebApiTransport requires an injected Web API client"
            )
        self._client = client
        self._fallback_text = fallback_text

    def create_root(
        self, channel: str, blocks: Sequence[Mapping[str, Any]]
    ) -> str:
        resp = self._client.chat_postMessage(
            channel=channel, blocks=list(blocks), text=self._fallback_text or None
        )
        return str(resp["ts"])

    def update_root(
        self, channel: str, root_ts: str, blocks: Sequence[Mapping[str, Any]]
    ) -> None:
        self._client.chat_update(
            channel=channel,
            ts=root_ts,
            blocks=list(blocks),
            text=self._fallback_text or None,
        )

    def dispatch_command(
        self, channel: str, root_ts: str, text: str, executor_user_id: str
    ) -> str:
        mention = f"<@{executor_user_id}>" if executor_user_id else ""
        body = f"{mention} {text}".strip()
        resp = self._client.chat_postMessage(
            channel=channel, thread_ts=root_ts, text=body
        )
        return str(resp["ts"])

    def read_thread_replies(
        self, channel: str, root_ts: str, since_ts: str | None
    ) -> list[ThreadReply]:
        resp = self._client.conversations_replies(channel=channel, ts=root_ts)
        items = resp.get("messages", []) or []
        out: list[ThreadReply] = []
        for msg in items:
            ts = str(msg.get("ts", ""))
            if not ts:
                continue
            if ts == root_ts:  # exclude the root itself
                continue
            if since_ts is not None and float(ts) <= float(since_ts):
                continue
            raw = msg.get("text") or ""
            if not raw.strip():
                continue
            # The Executor reply is the canonical human-readable update; parse it
            # into a clean mapping payload for the WP4 loop (fail closed).
            payload = parse_hermes_reply(raw).to_dict()
            out.append(ThreadReply(ts=ts, payload=payload))
        return out


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
    root_ts: str | None = None
    active_subtask_id: str | None = None
    executor_user_id: str | None = None
    executor_model: str | None = None
    token_usage: int | None = None
    watcher: str | None = None
    branch: str | None = None
    pr: str | None = None
    head_sha: str | None = None
    ci_status: str | None = None
    risk: str | None = None
    advanced_mode: bool = False


@dataclass
class MvpPilot:
    """Binds WP1..WP4 into the live GPT→Slack→Hermes→loop path.

    One root. One main Executor (configured identity, never hardcoded). Only the
    selected current subtask is dispatched into the thread. Material
    observations update the same RootCard in place.
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
            watcher=self.config.watcher,
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

    # -- A. dispatch only the selected current subtask INTO the thread -----
    def format_command(self, subtask: ContractedSubtask) -> str:
        """Render the Controller command text addressed to the Executor."""
        lines = [
            "EXECUTOR COMMAND",
            f"Subtask: {subtask.subtask_id}",
            f"Objective: {subtask.objective}",
            f"Allowed work: {'; '.join(subtask.allowed_work)}",
            f"Expected output: {'; '.join(subtask.expected_output)}",
            f"Report requirement: {'; '.join(subtask.report_requirement)}",
            f"After report: {subtask.after_report}",
        ]
        return "\n".join(lines)

    def dispatch_current(self) -> str:
        """Dispatch ONLY the selected current contracted subtask into the thread.

        Returns the dispatch receipt ts of the command message — NOT the
        Executor report. The Executor (separate actor) replies later.
        """
        subtask = self._selected_contract()
        root_ts = self.ensure_root()
        command = self.format_command(subtask)
        receipt_ts = self.config.slack.dispatch_command(
            self.config.channel,
            root_ts,
            command,
            self.config.executor_user_id or "",
        )
        return receipt_ts

    # -- map LoopObservation -> same RootCard in place ---------------------
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
            risk=(
                report.finding_risk[0]
                if report.finding_risk
                else self._card.risk
            ),
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

    # -- A. convenience orchestration: live Slack-mediated topology --------
    def run(
        self,
        max_polls: int = 1,
        sleeper: Callable[[int], None] | None = None,
    ) -> Any:
        """One in-session pilot pass: ensure root, dispatch command, feed WP4.

        The Controller posts the command into the thread (addressed to the
        configured Executor) and records a pre-dispatch cursor. The WP4 loop
        then reads ONLY Executor-authored replies strictly newer than that
        cursor and classifies them. The Controller never fabricates the
        Executor report.
        """
        root_ts = self.ensure_root()
        # Pre-dispatch cursor: the loop must read replies NEWER than this.
        pre_dispatch_ts = root_ts
        dispatch_ts = self.dispatch_current()
        if dispatch_ts > pre_dispatch_ts:
            pre_dispatch_ts = dispatch_ts

        def reader(last_seen_ts: str | None) -> Sequence[ThreadReply]:
            return self.config.slack.read_thread_replies(
                self.config.channel, root_ts, last_seen_ts
            )

        outcome = run_monitoring_loop(
            self._selected_contract(),
            read_replies=reader,
            update_rootcard=self.apply_observation,
            sleeper=sleeper or _noop_sleeper,
            last_seen_ts=pre_dispatch_ts,
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
    "parse_hermes_thread_update",
    "SlackTransport",
    "HermesExecutorClient",
    "SlackWebApiTransport",
    "AdvancedModeRequired",
    "module_keeps_deferred_core_out",
    "MvpPilotConfig",
    "MvpPilot",
]
