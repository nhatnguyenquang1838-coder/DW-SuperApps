"""MVP RootCard V1 — the human operational cockpit (pure, NO GWC, NO transport).

Authority
---------
``agents/chatgpt-agent/slack-controller-mvp.md`` and
``agents/shared/slack-controller-executor-protocol.md`` define exactly ONE root
message per run: a fast human snapshot, updated in place, carrying an explicit
ordered plan of 3-5 contracted subtasks and a small set of contextual actions.

This module materializes that RootCard as typed, validated, frozen value
objects plus a pure renderer. It is the WP2 counterpart of the WP1
``protocol_bridge`` and upholds the same hard rules:

1. PURE / STATELESS. No store, no CAS, no lease, no journal, no checkpoint, no
   network, no Slack client, no wall clock, no randomness. ``last_material_update``
   is always caller-supplied.
2. NO DEFERRED-CORE DEPENDENCY. Nothing from ``taskcontroller.runtime`` /
   ``packs`` / ``projections`` / ``routing`` / ``execution`` / ``controlplane``
   is imported. The Full-E2E surface stays dormant.
3. ONE ROOT. ``render_root_op`` emits ``CREATE_ROOT`` only when there is no
   existing root binding; with a binding it always emits ``UPDATE_ROOT``.
   Session / model / executor / cost rotation is projection *content*, never
   binding identity, so rotation can never spawn a second root.
4. PROJECTION, NOT AUTHORITY. Rendering an ``APPROVE`` / ``MERGE`` affordance
   is not authority and mutates nothing. The RootCard never approves or merges.
5. EXACT ENUMS. Cost is exactly ``FREE | metered | unknown`` and is never
   inferred. Unknown token usage renders as the literal ``N/A``.
6. GATE JOURNEY ONLY WHEN GWC IS ACTIVE. With ``gwc_active=False`` no gate /
   journey line may appear anywhere in the payload.
7. ROOT IS A SNAPSHOT. Detailed milestone evidence belongs in the thread; the
   RootCard carries no evidence list.
8. FAIL CLOSED. Missing or malformed input raises
   ``TaskControllerValidationError``; nothing degrades silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.mvp.protocol_bridge import (
    CONTRACTED_AFTER_VALUES,
    ContractedSubtask,
)

# --------------------------------------------------------------------------
# Exact enums (never inferred, never widened).
# --------------------------------------------------------------------------
#: Cost vocabulary mandated by the MVP RootCard contract.
COST_FREE = "FREE"
COST_METERED = "metered"
COST_UNKNOWN = "unknown"
COST_VALUES = (COST_FREE, COST_METERED, COST_UNKNOWN)

#: Literal rendered when the runtime does not expose token usage.
TOKEN_USAGE_UNKNOWN = "N/A"

#: The ONLY public contextual RootCard actions in the MVP API.
PUBLIC_ROOTCARD_ACTIONS = ("PAUSE", "STOP", "APPROVE", "MERGE")

#: Control verbs that must never be exposed as default human RootCard UI.
NON_PUBLIC_ACTIONS = ("RESUME", "CANCEL", "REPLAN")

#: Root operations. Exactly two — a rotation can never add a third.
CREATE_ROOT = "CREATE_ROOT"
UPDATE_ROOT = "UPDATE_ROOT"
ROOT_OPS = (CREATE_ROOT, UPDATE_ROOT)

#: MVP plan size bound from the authority docs: 3-5 meaningful subtasks.
MIN_TASK_CARDS = 3
MAX_TASK_CARDS = 5


class TaskCardStatus:
    """TaskCard status vocabulary for the human plan block."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"

    ALL = (PENDING, IN_PROGRESS, DONE, BLOCKED, FAILED)
    #: Statuses that mean the card is finished for plan-progress purposes.
    COMPLETED = (DONE,)


_STATUS_EMOJI = {
    TaskCardStatus.PENDING: ":large_blue_circle:",
    TaskCardStatus.IN_PROGRESS: ":repeat:",
    TaskCardStatus.DONE: ":white_check_mark:",
    TaskCardStatus.BLOCKED: ":warning:",
    TaskCardStatus.FAILED: ":x:",
}


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskControllerValidationError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


# --------------------------------------------------------------------------
# TaskCard / PlanBlock — the explicit ordered plan, materialized from the WP1
# contracted subtasks. NOT a generic labelled section.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class TaskCard:
    """One human plan card derived from exactly one contracted subtask."""

    subtask_id: str
    objective: str
    status: str
    after_report: str
    detail: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.subtask_id, "subtask_id")
        _require_text(self.objective, "objective")
        if self.status not in TaskCardStatus.ALL:
            raise TaskControllerValidationError(
                f"invalid TaskCard status: {self.status!r}; "
                f"expected one of {TaskCardStatus.ALL}"
            )
        if self.after_report not in CONTRACTED_AFTER_VALUES:
            raise TaskControllerValidationError(
                f"invalid TaskCard after_report: {self.after_report!r}; "
                f"expected one of {CONTRACTED_AFTER_VALUES}"
            )
        object.__setattr__(self, "detail", _optional_text(self.detail, "detail"))

    @classmethod
    def from_contract(
        cls,
        contracted: ContractedSubtask,
        status: str = TaskCardStatus.PENDING,
        detail: str | None = None,
    ) -> "TaskCard":
        """Derive a card from a WP1 contracted subtask (no invention)."""
        if not isinstance(contracted, ContractedSubtask):
            raise TaskControllerValidationError(
                "TaskCard.from_contract requires a ContractedSubtask"
            )
        return cls(
            subtask_id=contracted.subtask_id,
            objective=contracted.objective,
            status=status,
            after_report=contracted.after_report,
            detail=detail,
        )

    @property
    def is_complete(self) -> bool:
        return self.status in TaskCardStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "objective": self.objective,
            "status": self.status,
            "after_report": self.after_report,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class PlanBlock:
    """The explicit ordered plan: 3-5 TaskCards, unique ids, order preserved."""

    cards: tuple[TaskCard, ...]

    def __post_init__(self) -> None:
        cards = self.cards
        if isinstance(cards, (str, bytes)) or not isinstance(cards, Sequence):
            raise TaskControllerValidationError("cards must be a sequence of TaskCard")
        cards = tuple(cards)
        for card in cards:
            if not isinstance(card, TaskCard):
                raise TaskControllerValidationError("every plan card must be a TaskCard")
        if not (MIN_TASK_CARDS <= len(cards) <= MAX_TASK_CARDS):
            raise TaskControllerValidationError(
                f"PlanBlock requires {MIN_TASK_CARDS}-{MAX_TASK_CARDS} TaskCards, "
                f"got {len(cards)}"
            )
        ids = [c.subtask_id for c in cards]
        if len(set(ids)) != len(ids):
            raise TaskControllerValidationError("TaskCard subtask_ids must be unique")
        object.__setattr__(self, "cards", cards)

    @classmethod
    def from_contracts(
        cls,
        contracted: Sequence[ContractedSubtask],
        statuses: Mapping[str, str] | None = None,
    ) -> "PlanBlock":
        """Materialize the ordered plan from contracted subtasks, order preserved."""
        if isinstance(contracted, (str, bytes)) or not isinstance(contracted, Sequence):
            raise TaskControllerValidationError(
                "contracted must be an ordered sequence of ContractedSubtask"
            )
        statuses = statuses or {}
        return cls(
            cards=tuple(
                TaskCard.from_contract(
                    c, status=statuses.get(c.subtask_id, TaskCardStatus.PENDING)
                )
                for c in contracted
            )
        )

    @property
    def ordered_ids(self) -> tuple[str, ...]:
        return tuple(c.subtask_id for c in self.cards)

    @property
    def completed_count(self) -> int:
        return sum(1 for c in self.cards if c.is_complete)

    @property
    def progress(self) -> str:
        """Human progress string, e.g. ``2/5``."""
        return f"{self.completed_count}/{len(self.cards)}"

    def card(self, subtask_id: str) -> TaskCard | None:
        for c in self.cards:
            if c.subtask_id == subtask_id:
                return c
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cards": [c.to_dict() for c in self.cards],
            "progress": self.progress,
        }


# --------------------------------------------------------------------------
# RootCard V1
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class RootCard:
    """The MVP human operational cockpit — one root per run, updated in place.

    Every field is caller-supplied. Nothing is inferred: unknown token usage is
    ``None`` and renders as ``N/A``; cost must be an exact
    :data:`COST_VALUES` member; a gate journey may only be supplied when
    ``gwc_active`` is true.
    """

    run_id: str
    human_owner: str
    controller: str
    executor: str
    plan: PlanBlock
    active_subtask_id: str
    now: str
    next: str
    last_material_update: str
    executor_model: str | None = None
    token_usage: int | None = None
    cost: str = COST_UNKNOWN
    watcher: str | None = None
    branch: str | None = None
    pr: str | None = None
    head_sha: str | None = None
    ci_status: str | None = None
    risk: str | None = None
    gwc_active: bool = False
    gate_journey: str | None = None
    authority_boundary: bool = False
    merge_ready: bool = False
    paused: bool = False

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "human_owner",
            "controller",
            "executor",
            "active_subtask_id",
            "now",
            "next",
            "last_material_update",
        ):
            _require_text(getattr(self, name), name)
        if not isinstance(self.plan, PlanBlock):
            raise TaskControllerValidationError("plan must be a PlanBlock")
        if self.plan.card(self.active_subtask_id) is None:
            raise TaskControllerValidationError(
                f"active_subtask_id {self.active_subtask_id!r} is not in the PlanBlock "
                f"{self.plan.ordered_ids}"
            )
        if self.cost not in COST_VALUES:
            raise TaskControllerValidationError(
                f"invalid cost: {self.cost!r}; cost is never inferred and must be "
                f"one of {COST_VALUES}"
            )
        if self.token_usage is not None:
            if isinstance(self.token_usage, bool) or not isinstance(self.token_usage, int):
                raise TaskControllerValidationError("token_usage must be an int or None")
            if self.token_usage < 0:
                raise TaskControllerValidationError("token_usage must not be negative")
        for name in (
            "executor_model",
            "watcher",
            "branch",
            "pr",
            "head_sha",
            "ci_status",
            "risk",
            "gate_journey",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        if self.gate_journey is not None and not self.gwc_active:
            raise TaskControllerValidationError(
                "gate_journey is only allowed when gwc_active is true"
            )
        if self.merge_ready and not (self.pr and self.head_sha):
            raise TaskControllerValidationError(
                "merge_ready requires an exact bound pr and head_sha"
            )

    # -- derived, still pure -------------------------------------------------
    @property
    def token_usage_display(self) -> str:
        return TOKEN_USAGE_UNKNOWN if self.token_usage is None else str(self.token_usage)

    @property
    def progress(self) -> str:
        return self.plan.progress

    def contextual_actions(self) -> tuple[str, ...]:
        """The contextual public action affordances, in exact MVP API order.

        ``PAUSE`` is a soft-control affordance shown while not already paused.
        ``STOP`` is a hard-stop affordance (semantics are NOT implemented here).
        ``APPROVE`` appears only at an exact human authority boundary.
        ``MERGE`` appears only when merge is a valid next action with an exact
        bound PR/head. ``RESUME`` / ``CANCEL`` / ``REPLAN`` are never public.
        """
        actions: list[str] = []
        if not self.paused:
            actions.append("PAUSE")
        actions.append("STOP")
        if self.authority_boundary:
            actions.append("APPROVE")
        if self.merge_ready:
            actions.append("MERGE")
        return tuple(a for a in PUBLIC_ROOTCARD_ACTIONS if a in actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "human_owner": self.human_owner,
            "watcher": self.watcher,
            "controller": self.controller,
            "executor": self.executor,
            "executor_model": self.executor_model,
            "token_usage": self.token_usage,
            "token_usage_display": self.token_usage_display,
            "cost": self.cost,
            "active_subtask_id": self.active_subtask_id,
            "progress": self.progress,
            "branch": self.branch,
            "pr": self.pr,
            "head_sha": self.head_sha,
            "ci_status": self.ci_status,
            "risk": self.risk,
            "now": self.now,
            "next": self.next,
            "last_material_update": self.last_material_update,
            "gwc_active": self.gwc_active,
            "gate_journey": self.gate_journey,
            "plan": self.plan.to_dict(),
            "actions": list(self.contextual_actions()),
        }


@dataclass(frozen=True)
class RootOp:
    """The root operation a transport should perform. Exactly two kinds."""

    op: str
    run_id: str
    channel: str
    root: str | None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.op not in ROOT_OPS:
            raise TaskControllerValidationError(
                f"invalid root op: {self.op!r}; expected one of {ROOT_OPS}"
            )
        _require_text(self.run_id, "run_id")
        _require_text(self.channel, "channel")
        if self.op == CREATE_ROOT and self.root is not None:
            raise TaskControllerValidationError("CREATE_ROOT must not carry a root")
        if self.op == UPDATE_ROOT:
            _require_text(self.root, "root")


# --------------------------------------------------------------------------
# Pure renderer
# --------------------------------------------------------------------------
def _plan_block_payload(plan: PlanBlock) -> dict[str, Any]:
    """The explicit PlanBlock: a typed block carrying its ordered TaskCards."""
    return {
        "type": "plan_block",
        "progress": plan.progress,
        "task_cards": [
            {
                "type": "task_card",
                "position": i,
                "subtask_id": c.subtask_id,
                "status": c.status,
                "emoji": _STATUS_EMOJI[c.status],
                "objective": c.objective,
                "after_report": c.after_report,
                "detail": c.detail,
            }
            for i, c in enumerate(plan.cards, start=1)
        ],
    }


def render_rootcard(card: RootCard) -> dict[str, Any]:
    """Render the RootCard snapshot payload. Pure; contains no evidence list."""
    if not isinstance(card, RootCard):
        raise TaskControllerValidationError("render_rootcard requires a RootCard")

    fields: list[tuple[str, str]] = [("owner", card.human_owner)]
    if card.watcher:
        fields.append(("watcher", card.watcher))
    if card.gwc_active and card.gate_journey:
        fields.append(("journey", card.gate_journey))
    fields.append(("controller", card.controller))
    fields.append(("executor", card.executor))
    if card.executor_model:
        fields.append(("model", card.executor_model))
    fields.append(("tokens", card.token_usage_display))
    fields.append(("cost", card.cost))
    fields.append(("active", f"{card.active_subtask_id} ({card.progress})"))
    if card.branch:
        fields.append(("branch", card.branch))
    if card.pr:
        fields.append(("pr", card.pr))
    if card.head_sha:
        fields.append(("head", card.head_sha))
    if card.ci_status:
        fields.append(("ci", card.ci_status))
    fields.append(("risk", card.risk or "none"))
    fields.append(("now", card.now))
    fields.append(("next", card.next))
    fields.append(("last material update", card.last_material_update))

    return {
        "kind": "ROOTCARD_V1",
        "run_id": card.run_id,
        "header": f"Run {card.run_id}",
        "fields": [{"label": label, "value": value} for label, value in fields],
        "plan_block": _plan_block_payload(card.plan),
        "actions": list(card.contextual_actions()),
        "authority_granted": False,
    }


def render_root_op(
    card: RootCard,
    channel: str,
    root: str | None = None,
) -> RootOp:
    """Emit the root operation for this RootCard.

    ``root is None`` (no existing binding) -> ``CREATE_ROOT``.
    An existing bound ``root`` -> ``UPDATE_ROOT`` in place, ALWAYS. Metadata
    rotation (model, executor, session, cost, token usage) is content and can
    therefore never produce a second root.
    """
    payload = render_rootcard(card)
    if root is None:
        return RootOp(
            op=CREATE_ROOT,
            run_id=card.run_id,
            channel=channel,
            root=None,
            payload=payload,
        )
    return RootOp(
        op=UPDATE_ROOT,
        run_id=card.run_id,
        channel=channel,
        root=root,
        payload=payload,
    )
