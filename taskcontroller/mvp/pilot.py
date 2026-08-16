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
    POLL_INTERVAL_SECONDS,
    ProtocolVerdict,
    ThreadReply,
    run_monitoring_loop,
)
from taskcontroller.audit.event import AuditEvent
from taskcontroller.audit.facade import AuditFacade, NoOpAuditFacade
from taskcontroller.audit.integrity import BoundInputSnapshot
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
    the four WP3 public actions. A ``rich_text`` block's child elements must be
    valid rich_text children (``rich_text_section`` / ``rich_text_list`` /
    ``rich_text_quote`` / ``rich_text_preformatted``); a ``rich_text`` nested
    inside a ``rich_text`` is invalid. A ``section``'s ``fields`` list is capped
    at 10 (the Slack limit).
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
        elif btype == "section":
            _validate_section_block(block, idx)
        elif btype == "rich_text":
            _validate_rich_text_block(block, idx)


#: Valid child element types for a rich_text block (current Slack schema).
_RICH_TEXT_CHILD_TYPES = frozenset(
    {"rich_text_section", "rich_text_list", "rich_text_quote", "rich_text_preformatted"}
)

#: Slack hard cap on a section block's ``fields`` list.
_SECTION_FIELDS_MAX = 10


def _validate_rich_text_block(block: Mapping[str, Any], idx: int) -> None:
    elements = block.get("elements")
    if not isinstance(elements, (list, tuple)) or not elements:
        raise TaskControllerValidationError(
            f"rich_text block[{idx}] requires non-empty 'elements'"
        )
    for j, child in enumerate(elements):
        if not isinstance(child, Mapping):
            raise TaskControllerValidationError(
                f"rich_text.block[{idx}].elements[{j}] must be an object"
            )
        ctype = child.get("type")
        if ctype not in _RICH_TEXT_CHILD_TYPES:
            raise TaskControllerValidationError(
                f"rich_text.block[{idx}].elements[{j}] has invalid child type "
                f"{ctype!r}; rich_text nesting is not allowed and only "
                f"{sorted(_RICH_TEXT_CHILD_TYPES)} are valid"
            )


def _validate_section_block(block: Mapping[str, Any], idx: int) -> None:
    fields = block.get("fields")
    if fields is None:
        return
    if not isinstance(fields, (list, tuple)):
        raise TaskControllerValidationError(
            f"section block[{idx}] 'fields' must be a list"
        )
    if len(fields) > _SECTION_FIELDS_MAX:
        raise TaskControllerValidationError(
            f"section block[{idx}] has {len(fields)} fields; Slack caps "
            f"section.fields at {_SECTION_FIELDS_MAX}"
        )


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
    operational metadata (split into multiple valid ``section`` blocks, each
    with at most 10 ``fields`` — the Slack cap) and ONLY the contextual public
    actions.
    """
    if not isinstance(card, RootCard):
        raise TaskControllerValidationError("translate requires a RootCard")

    header = {
        "type": "header",
        "block_id": "mvp_header",
        "text": {"type": "plain_text", "text": f"Run {card.run_id}", "emoji": True},
    }

    # -- operational metadata (complete WP2 live fields) --------------------
    # Build the full ordered field list, then split into chunks of <=10 to
    # respect the Slack section.fields cap (exactly 10 max).
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

    # Deterministic chunking into <=10-field sections.
    meta_blocks: list[dict[str, Any]] = []
    for i in range(0, len(meta_fields), 10):
        chunk = meta_fields[i : i + 10]
        meta_blocks.append(
            {
                "type": "section",
                "block_id": f"mvp_meta_{i // 10}",
                "fields": chunk,
            }
        )

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

    return [header, *meta_blocks, plan_block, context, _action_block(card.contextual_actions())]


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
        self, channel: str, root_ts: str, since_ts: str | None,
        executor_user_id: str | None = None,
    ) -> list[ThreadReply]:
        """Read thread replies strictly newer than ``since_ts``.

        ``executor_user_id`` is the authoritative expected actor for the run;
        the transport MUST filter to that actor's replies (a human/Controller
        reply is ignored). The caller (``MvpPilot.run``) supplies exactly
        ``config.executor_user_id`` on every read.
        """
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
#: Verdicts the authority final line may carry (after the ``·``).
_AFTER_WORDS = {v.lower(): v for v in CONTRACTED_AFTER_VALUES}
_STATUS_WORDS = {
    "running": "RUNNING",
    "done": "DONE",
    "blocked": "BLOCKED",
    "failed": "FAILED",
}
#: Heading markers (case-insensitive, stripped) that begin a bullet section.
_SECTION_MARKERS = {
    "status": "status",
    "phase": "phase",
    "completed": "completed",
    "evidence": "evidence",
    "finding/risk": "finding_risk",
    "finding": "finding_risk",
    "risk": "finding_risk",
    "next": "next_action",
}


def _normalize_section_key(raw: str) -> str | None:
    """Case/space-insensitive section heading lookup (e.g. 'Finding / Risk')."""
    return _SECTION_MARKERS.get(raw.strip().lower().replace(" ", ""))


def _ts_key_pilot(ts: str) -> tuple[int, int, int, str]:
    """Lossless integer ordering key for a Slack ``ts`` (seconds.microseconds).

    Mirrors WP4 ``monitoring._ts_key``: no ``float()``, no lexicographic
    compare. Slack ``ts`` values are numeric strings; compare the integer
    second and the integer microsecond separately so ``"99.0" < "100.0"`` and
    ``"1.5" == "1.500000"`` both hold exactly. Non-numeric values fall into a
    stable lexicographic bucket so ordering never raises.
    """
    if isinstance(ts, str):
        candidate = ts.strip()
        seconds, _, fraction = candidate.partition(".")
        if seconds.isdigit() and (fraction == "" or fraction.isdigit()):
            micros = int((fraction + "000000")[:6]) if fraction else 0
            return (0, int(seconds), micros, "")
    return (1, 0, 0, ts if isinstance(ts, str) else repr(ts))


def _split_header_subtask_id(header: str) -> str | None:
    """Derive the subtask id from the authority header ``🟡 EXECUTOR UPDATE · Sx/y``.

    Returns ``Sx`` (the part before ``/``) or ``None`` when the header carries
    no ``· <id>`` token.
    """
    if "·" not in header:
        return None
    tail = header.split("·", 1)[1].strip()
    if not tail:
        return None
    # The subtask id is the first whitespace-free token (before any ``/``).
    token = tail.split()[0] if tail.split() else tail
    return token.split("/", 1)[0]


def _split_final_verdict(line: str) -> str | None:
    """Derive the After verdict from the final boundary line ``Sx · CONTINUE``.

    The subtask id precedes the ``·`` and the verdict follows it.
    """
    if "·" not in line:
        return None
    tail = line.split("·", 1)[1].strip()
    if not tail:
        return None
    token = tail.split()[0] if tail.split() else tail
    return _AFTER_WORDS.get(token.strip().lower())


def _split_final_subtask(line: str) -> str | None:
    """Derive the subtask id from the final boundary line ``Sx · CONTINUE``.

    The subtask id precedes the ``·`` (with optional ``/y`` denominator).
    """
    if "·" not in line:
        return None
    head = line.split("·", 1)[0].strip()
    if not head:
        return None
    return head.split("/", 1)[0]


def _collect_bullets(sections: dict[str, list[str]], key: str) -> tuple[str, ...]:
    return tuple(s.strip() for s in sections.get(key, []) if s.strip())


def parse_hermes_thread_update(text: str) -> ExecutorReport:
    """Parse the *authority* human-readable MVP Slack Executor update.

    Authority format (emoji-prefixed header; no ``Subtask_id:`` / ``After:``
    labels required — subtask and After come from the header and final
    boundary line):

        🟡 EXECUTOR UPDATE · Sx/y
        Status: RUNNING|DONE|BLOCKED|FAILED
        Phase: <phase>

        Completed
        - item

        Evidence
        - item

        Finding / Risk
        - item             # optional when material

        Next
        → exact next action

        Sx · CONTINUE|WAIT_CONTROLLER|TERMINAL

    Rules enforced (fail closed):
    * the header MUST carry the canonical emoji ``🟡`` and an ``EXECUTOR UPDATE``
      marker (case-insensitive);
    * subtask id is derived from the header; if a final ``<id> · <AFTER>`` line
      also names a subtask, the two MUST agree;
    * status MUST be one of ``REPORT_STATUSES``;
    * After MUST be one of ``CONTRACTED_AFTER_VALUES``, derived from the final
      boundary line;
    * ``Completed`` / ``Evidence`` MUST be non-empty; ``Finding / Risk`` is
      optional only (may be empty). ``Next`` is parsed from the ``→`` marker.
    JSON / colon compatibility is preserved via :func:`parse_hermes_reply`.
    """
    if not isinstance(text, str) or not text.strip():
        raise MalformedReportError("empty Hermes thread update")

    lines = text.splitlines()
    header: str | None = None
    for raw in lines:
        stripped = raw.strip()
        if stripped and "🟡" in stripped and "executor update" in stripped.lower():
            header = stripped
            break
    if header is None:
        raise MalformedReportError(
            "Hermes thread update must carry the canonical "
            "'🟡 EXECUTOR UPDATE' header line"
        )

    header_subtask = _split_header_subtask_id(header)

    # -- parse heading (Status:/Phase:) + bullet sections ----------------
    sections: dict[str, list[str]] = {}
    current: str | None = None
    status: str | None = None
    phase: str | None = None
    next_action: str | None = None
    final_subtask: str | None = None
    final_after: str | None = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            # A blank line closes any open bullet section context.
            current = None
            continue
        low = stripped.lower()

        # final boundary line: "<id> · <AFTER>" (no heading marker, has "·")
        if (
            current is None
            and ":" not in stripped
            and "·" in stripped
            and _split_final_verdict(stripped) is not None
        ):
            final_after = _split_final_verdict(stripped)
            final_subtask = _split_final_subtask(stripped)
            continue

        # heading line: "Key: value"
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            norm_key = _normalize_section_key(key)
            mapped = norm_key
            if mapped == "status":
                status = _STATUS_WORDS.get(value.strip().lower())
                current = None
                continue
            if mapped == "phase":
                phase = value.strip() or None
                current = None
                continue
            if mapped in ("completed", "evidence", "finding_risk", "next_action"):
                # heading value may itself hold the content
                if value.strip():
                    sections.setdefault(mapped, []).append(value.strip())
                current = mapped
                continue
            # unknown heading -> ignore but do not break section context wrongly
            current = None
            continue

        # bare section heading (no colon), e.g. "Completed" / "Evidence" /
        # "Finding / Risk" / "Next" — opens a bullet section.
        bare = _normalize_section_key(low)
        if bare in ("completed", "evidence", "finding_risk", "next_action"):
            current = bare
            continue

        # "Next → ..." bullet or heading
        if low.startswith("next"):
            rest = stripped.split("→", 1)[1].strip() if "→" in stripped else stripped[len("next"):].strip()
            if rest:
                next_action = rest
                current = "next_action"
                continue

        # bullet item
        if stripped.startswith("-") or stripped.startswith("•"):
            item = stripped.lstrip("-•").strip()
            if current in ("completed", "evidence", "finding_risk", "next_action") and item:
                sections.setdefault(current, []).append(item)
            continue

        # "→ exact next action" inside the Next section
        if "→" in stripped and current == "next_action":
            item = stripped.split("→", 1)[1].strip()
            if item:
                next_action = item
            continue

        # any other line: close section context
        current = None

    # -- subtask agreement ------------------------------------------------
    subtask_id = header_subtask or final_subtask
    if header_subtask and final_subtask and header_subtask != final_subtask:
        raise MalformedReportError(
            f"Hermes thread update subtask mismatch: header={header_subtask!r} "
            f"final={final_subtask!r}"
        )
    if not subtask_id:
        raise MalformedReportError("Hermes thread update missing subtask id")

    # -- status -------------------------------------------------------------
    if status is None or status not in REPORT_STATUSES:
        raise MalformedReportError(
            f"Hermes thread update has ambiguous/missing status: {status!r}"
        )

    # -- after --------------------------------------------------------------
    if final_after is None or final_after not in CONTRACTED_AFTER_VALUES:
        raise MalformedReportError(
            f"Hermes thread update has ambiguous/missing After boundary: {final_after!r}"
        )

    completed = _collect_bullets(sections, "completed")
    evidence = _collect_bullets(sections, "evidence")
    finding_risk = _collect_bullets(sections, "finding_risk")

    if not completed:
        raise MalformedReportError("Hermes thread update has no Completed items")
    if not evidence:
        raise MalformedReportError("Hermes thread update has no Evidence items")
    if not next_action:
        next_action = "await controller"

    try:
        return ExecutorReport(
            subtask_id=subtask_id,
            status=status,
            completed=completed,
            evidence=evidence,
            finding_risk=finding_risk,
            next_action=next_action,
            after=final_after,
        )
    except TaskControllerValidationError as exc:
        raise MalformedReportError(f"incomplete Hermes thread update: {exc}") from exc


def parse_hermes_reply(text: str | Mapping[str, Any]) -> ExecutorReport:
    """Parse a Hermes milestone reply into a COMPLETE WP1 ExecutorReport.

    Accepts either a JSON/mapping payload or the canonical human-readable Slack
    authority text (``🟡 EXECUTOR UPDATE · Sx/y`` …). Fail closed: incomplete or
    ambiguous input raises ``MalformedReportError`` (never silently downgraded
    to CONTINUE).
    """
    if isinstance(text, Mapping):
        payload: Mapping[str, Any] = text
    elif isinstance(text, str):
        stripped = text.strip()
        # Try the canonical human-readable form first when it has the header.
        if "🟡" in stripped and "executor update" in stripped.lower():
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

    Executor actor filtering: ``read_thread_replies`` accepts the authoritative
    ``executor_user_id`` (the run's ``config.executor_user_id``) on every call
    and returns ONLY Executor-authored report messages (matching ``msg.user``),
    so a human/Controller reply after dispatch can never be misparsed. A missing
    identity fails closed. Timestamp filtering uses the lossless integer ordering
    key (no ``float``, no lexicographic compare) — same semantics as WP4
    ``_ts_key``. Exactly one identity governs the run.
    """

    def __init__(
        self,
        client: Any,
        executor_user_id: str | None = None,
        fallback_text: str = "",
    ) -> None:
        if client is None:
            raise TaskControllerValidationError(
                "SlackWebApiTransport requires an injected Web API client"
            )
        self._client = client
        self._executor_user_id = executor_user_id
        self._fallback_text = fallback_text or "TaskController MVP root"

    def create_root(
        self, channel: str, blocks: Sequence[Mapping[str, Any]]
    ) -> str:
        resp = self._client.chat_postMessage(
            channel=channel, blocks=list(blocks), text=self._fallback_text
        )
        return str(resp["ts"])

    def update_root(
        self, channel: str, root_ts: str, blocks: Sequence[Mapping[str, Any]]
    ) -> None:
        self._client.chat_update(
            channel=channel,
            ts=root_ts,
            blocks=list(blocks),
            text=self._fallback_text,
        )

    def dispatch_command(
        self, channel: str, root_ts: str, text: str, executor_user_id: str
    ) -> str:
        if not executor_user_id:
            # No hardcoded identity; the live path must bind one or fail closed.
            raise TaskControllerValidationError(
                "dispatch_command requires a bound executor_user_id"
            )
        mention = f"<@{executor_user_id}>"
        body = f"{mention} {text}".strip()
        resp = self._client.chat_postMessage(
            channel=channel, thread_ts=root_ts, text=body
        )
        return str(resp["ts"])

    def read_thread_replies(
        self,
        channel: str,
        root_ts: str,
        since_ts: str | None,
        executor_user_id: str | None = None,
    ) -> list[ThreadReply]:
        # The authoritative actor for the run is exactly the supplied
        # executor_user_id (the caller passes config.executor_user_id). When the
        # transport was constructed with one too, they MUST agree (single
        # identity); a mismatch is a programming error and fails closed.
        expected = executor_user_id or self._executor_user_id
        if self._executor_user_id and executor_user_id and \
                self._executor_user_id != executor_user_id:
            raise TaskControllerValidationError(
                "executor identity mismatch: transport binds "
                f"{self._executor_user_id!r} but read asked for {executor_user_id!r}"
            )
        if not expected:
            # No identity bound anywhere — a live read cannot distinguish the
            # Executor from a human/Controller reply. Fail closed.
            raise TaskControllerValidationError(
                "read_thread_replies requires a bound executor_user_id"
            )
        resp = self._client.conversations_replies(channel=channel, ts=root_ts)
        items = resp.get("messages", []) or []
        out: list[ThreadReply] = []
        for msg in items:
            ts = str(msg.get("ts", ""))
            if not ts:
                continue
            if ts == root_ts:  # exclude the root itself
                continue
            # Lossless integer ordering — no float, no lexicographic compare.
            if since_ts is not None and _ts_key_pilot(ts) <= _ts_key_pilot(since_ts):
                continue
            # Executor actor filtering: accept only Executor-authored messages.
            if msg.get("user") != expected:
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
    cost: str = COST_UNKNOWN
    gwc_active: bool = False
    gate_journey: str | None = None
    authority_boundary: bool = False
    merge_ready: bool = False
    paused: bool = False
    audit_facade: Any = None
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
    def _build_bound_input_snapshot(self) -> BoundInputSnapshot:
        return BoundInputSnapshot(
            repo_refs={
                "main": getattr(self.config, "head_sha", None) or "",
            },
            contract_overlays=list(self.config.contracts[0].allowed_work if self.config.contracts else []),
            execution_contract={
                "run_id": self.config.run_id,
                "subtask_id": self._active_subtask_id(),
            },
            source_evidence=[
                self.config.controller,
                self.config.executor,
            ],
        )

    def _record_audit_event(self, event: AuditEvent) -> None:
        facade = getattr(self.config, "audit_facade", None)
        if facade is None:
            return
        if isinstance(facade, NoOpAuditFacade):
            return
        facade.record(self.config.run_id, event)

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
            cost=self.config.cost,
            watcher=self.config.watcher,
            branch=self.config.branch,
            pr=self.config.pr,
            head_sha=self.config.head_sha,
            ci_status=self.config.ci_status,
            risk=self.config.risk,
            gwc_active=self.config.gwc_active,
            gate_journey=self.config.gate_journey,
            authority_boundary=self.config.authority_boundary,
            merge_ready=self.config.merge_ready,
            paused=self.config.paused,
        )
        return card

    # -- one-root invariant ------------------------------------------------
    def ensure_root(self) -> str:
        """Establish the single root. CREATE_ROOT exactly once; else UPDATE_ROOT.

        Rotation (model / session / executor) only ever calls this again and
        MUST keep the same ``root_ts`` (it cannot create a second root).
        """
        if self._root_ts is not None:
            # Already bound -> no second CREATE_ROOT. Audit the rotation update.
            self._record_audit_event(
                AuditEvent(
                    event_id=f"root-rotate-{self.config.run_id}",
                    timestamp="2026-08-16T00:00:00Z",
                    run_id=self.config.run_id,
                    source="mvp.pilot",
                    decision_kind="ROOT_UPDATE",
                    payload_summary="root rotation / metadata update",
                )
            )
            return self._root_ts
        if self.config.root_ts is not None:
            self._root_ts = self.config.root_ts
            return self._root_ts
        if self._card is None:
            self._card = self._build_initial_card()
            self._plan = self._card.plan
        blocks = translate_rootcard_to_blocks(self._card)
        validate_slack_blocks(blocks)
        self._root_ts = self.config.slack.create_root(self.config.channel, blocks)
        self._record_audit_event(
            AuditEvent(
                event_id=f"root-create-{self.config.run_id}",
                timestamp="2026-08-16T00:00:00Z",
                run_id=self.config.run_id,
                source="mvp.pilot",
                decision_kind="ROOT_CREATE",
                payload_summary="initial RootCard created",
            )
        )
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
        max_polls: int | None = None,
        sleeper: Callable[[int], None] | None = None,
    ) -> Any:
        """One in-session pilot pass: ensure root, dispatch command, feed WP4.

        The Controller posts the command into the thread (addressed to the
        configured Executor) and records a pre-dispatch cursor. The WP4 loop
        then reads ONLY Executor-authored replies strictly newer than that
        cursor and classifies them. The Controller never fabricates the
        Executor report.

        Live default behaviour (per the in-session monitoring design):
        * ``sleeper`` defaults to a REAL ``time.sleep(POLL_INTERVAL_SECONDS)``
          (exactly 60s) injected through the WP4 loop — no zero-wait, no
          single empty poll. Tests inject a fake sleeper.
        * ``max_polls=None`` (the default) means the live loop stays active
          until a boundary verdict is reached (unbounded). A positive int is
          only for tests/debug. ``max_polls < 1``/``0``/``False`` is rejected.
        * The live path FAILS CLOSED if no Executor identity is bound — a
          live dispatch must address a real, configured Executor (no hardcoded
          ID).

        Synchronous and in-session only: no thread, no scheduler, no detached
        execution.
        """
        if self.config.executor_user_id is None:
            # No hardcoded Hermes ID; a live dispatch requires a bound identity.
            raise TaskControllerValidationError(
                "live MvpPilot.run() requires config.executor_user_id bound"
            )
        if max_polls is not None:
            if (
                isinstance(max_polls, bool)
                or not isinstance(max_polls, int)
                or max_polls < 1
            ):
                raise TaskControllerValidationError(
                    "max_polls must be a positive int or None (unbounded)"
                )
        root_ts = self.ensure_root()
        # Pre-dispatch cursor: the loop must read replies NEWER than this.
        pre_dispatch_ts = root_ts
        dispatch_ts = self.dispatch_current()
        # Lossless integer ordering — set cursor to the validated dispatch ts
        # when it is strictly later than the root.
        if _ts_key_pilot(dispatch_ts) > _ts_key_pilot(pre_dispatch_ts):
            pre_dispatch_ts = dispatch_ts

        def reader(last_seen_ts: str | None) -> Sequence[ThreadReply]:
            # Pass the single authoritative Executor identity on every read so the
            # transport filters strictly to the Executor's replies. No hardcoded
            # ID; config.executor_user_id is the source of truth for the run.
            return self.config.slack.read_thread_replies(
                self.config.channel,
                root_ts,
                last_seen_ts,
                self.config.executor_user_id,
            )

        # Default live sleeper: REAL 60s wait via injected default. Tests pass
        # a fake sleeper so no unit test ever really sleeps.
        live_sleeper = sleeper if sleeper is not None else _live_sleeper

        outcome = run_monitoring_loop(
            self._selected_contract(),
            read_replies=reader,
            update_rootcard=self.apply_observation,
            sleeper=live_sleeper,
            last_seen_ts=pre_dispatch_ts,
            max_polls=max_polls,
            poll_interval_seconds=POLL_INTERVAL_SECONDS,
        )
        return outcome


def _live_sleeper(seconds: int) -> None:
    """Default live sleeper: REAL wall-clock wait (exactly 60s per poll).

    Injected into the WP4 loop as the production cadence. The MVP loop is
    synchronous and in-session; this is the only place a real sleep occurs, and
    only on the production/default path. Tests never call this.
    """
    import time

    time.sleep(seconds)


#: Back-compat no-op (tests that want zero wait without a real sleep use a fake
#: sleeper instead). Kept only so old call sites that passed ``sleeper=None``
#: explicitly still default to a *real* 60s wait via ``_live_sleeper``.
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
