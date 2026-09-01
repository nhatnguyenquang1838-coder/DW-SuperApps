"""WP6 S2 Slack live-root renderer (pure, NO GWC, NO transport).

Maps a RunProjectionView + binding into Slack-shaped block payloads and the
operations a transport should perform. The renderer is pure: it never talks to
Slack and never decides binding identity — that is the BindingRegistry's job.

Hard invariant enforced here:
- ROOT = live progress card (PlanBlock -> ordered TaskCards + metadata).
- THREAD = semantic human events only.
- The renderer emits CREATE_ROOT ONLY when no binding exists; for an existing
  binding it emits UPDATE_ROOT (and thread events emit REPLY_THREAD). It NEVER
  emits CREATE_ROOT for an existing binding, so session/model/executor rotation
  can never spawn a new root.
- Existing bindings cannot move channel/root identity through rendering.
- Machine chatter cannot be rendered as a human-plane thread event.
"""

from __future__ import annotations

from typing import Any

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.human_projection import HumanEventKind
from taskcontroller.projections.binding import Binding
from taskcontroller.projections.domain import build_view
from taskcontroller.projections.types import (
    ProjectionOp,
    RunProjectionView,
    TaskStatus,
)

_TASK_EMOJI = {
    TaskStatus.PENDING: ":large_blue_circle:",
    TaskStatus.IN_PROGRESS: ":repeat:",
    TaskStatus.COMPLETE: ":white_check_mark:",
    TaskStatus.ERROR: ":x:",
}

_RUN_EMOJI = _TASK_EMOJI


def _task_card(node) -> dict[str, Any]:
    emoji = _TASK_EMOJI.get(node.status, ":white_circle:")
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{emoji} *{node.label}* — `{node.status.value}`"
            + (f"\n   _{node.detail}_" if node.detail else ""),
        },
    }


def render_root_blocks(view: RunProjectionView, binding: Binding | None) -> dict[str, Any]:
    """Build the Slack block payload for the live progress card (ROOT)."""
    run_emoji = _RUN_EMOJI.get(_status_of(view), ":white_circle:")
    header = {
        "type": "header",
        "text": {"type": "plain_text", "text": f"Run {view.run_id} {run_emoji}"},
    }
    meta_lines = [
        f"*status*: `{view.run_status}`",
        f"*version*: {view.version}",
        f"*plan*: {view.plan_version}",
        f"*journal*: {view.journal_position}",
    ]
    if view.session_id:
        meta_lines.append(f"*session*: {view.session_id}")
    if view.model:
        meta_lines.append(f"*model*: {view.model}")
    if view.executor:
        meta_lines.append(f"*executor*: {view.executor}")
    if view.token_usage is not None:
        meta_lines.append(f"*tokens*: {view.token_usage}")
    meta_section = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(meta_lines)},
    }
    plan_label = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*Plan*"},
    }
    cards = [_task_card(n) for n in view.nodes]
    affordances = {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "actions: "
                + (", ".join(view.legal_affordances) if view.legal_affordances else "—"),
            }
        ],
    }
    return {
        "blocks": [header, meta_section, plan_label, *cards, affordances],
    }


def _status_of(view: RunProjectionView) -> TaskStatus:
    from taskcontroller.projections.domain import map_run_status

    return map_run_status(view.run_status)


def _validate_binding_route(binding_key: str, channel: str, binding: Binding) -> None:
    """Fail closed if a rendered operation tries to escape its persisted binding."""
    if binding.binding_key != binding_key:
        raise TaskControllerValidationError(
            "Slack human-plane binding key does not match persisted binding"
        )
    if binding.channel != channel:
        raise TaskControllerValidationError(
            "Slack human-plane channel does not match persisted binding"
        )
    if not binding.root:
        raise TaskControllerValidationError(
            "Slack human-plane persisted binding has no root"
        )


def _validate_human_event_kind(event_kind: str) -> None:
    try:
        HumanEventKind(event_kind)
    except (TypeError, ValueError) as exc:
        raise TaskControllerValidationError(
            f"Slack thread payload is not a supported human event: {event_kind!r}"
        ) from exc


def render_root_op(
    view: RunProjectionView,
    binding_key: str,
    channel: str,
    binding: Binding | None,
) -> ProjectionOp:
    """Produce the root operation.

    CREATE_ROOT only when no binding exists; otherwise UPDATE_ROOT. Never
    CREATE_ROOT for an existing binding (rotation safety).
    """
    blocks = render_root_blocks(view, binding)
    if binding is None:
        return ProjectionOp(
            op="CREATE_ROOT",
            binding_key=binding_key,
            channel=channel,
            root=None,
            payload=blocks,
        )
    _validate_binding_route(binding_key, channel, binding)
    return ProjectionOp(
        op="UPDATE_ROOT",
        binding_key=binding_key,
        channel=channel,
        root=binding.root,
        payload=blocks,
    )


def render_thread_op(
    binding_key: str,
    channel: str,
    binding: Binding,
    event_kind: str,
    text: str,
    authority_required: bool = False,
) -> ProjectionOp:
    """Produce one semantic human-plane thread reply on the persisted root."""
    _validate_binding_route(binding_key, channel, binding)
    _validate_human_event_kind(event_kind)
    return ProjectionOp(
        op="REPLY_THREAD",
        binding_key=binding_key,
        channel=channel,
        root=binding.root,
        payload={"event_kind": event_kind, "text": text},
        authority_required=authority_required,
    )
