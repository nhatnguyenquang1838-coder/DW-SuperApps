"""Deterministic TaskController activation resolver for the active MVP.

TaskController activation is resolved from current repository state, never from
conversation memory. Agent interaction semantics are transport-neutral; the
current pilot binding is a GitHub reference mailbox while Slack is the human
control/visibility plane.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


TASKCONTROLLER_ALIASES = (
    "TaskController",
    "task controller",
    "/dw-taskcontroller",
)

_BASE_LOAD_ORDER = (
    "AGENTS.md",
    "workspace.yaml",
    "controllers/taskcontroller.yaml",
    "agents/README.md",
)

_HOST_REQUIRED = {
    "chatgpt": ("agents/chatgpt-agent/agent-instructions.md",),
}

_INTERACTION_REQUIRED = (
    "agents/shared/taskcontroller-a2a-protocol.md",
)

_SLACK_CHATGPT_REQUIRED = (
    "agents/chatgpt-agent/slack-controller-mvp.md",
)

_HERMES_EXECUTOR_REQUIRED = (
    "agents/hermes/agent-instructions.md",
)

_ALIAS_RE = re.compile(
    r"(?<![\w-])(?:/dw-taskcontroller|taskcontroller|task\s+controller)(?![\w-])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TaskControllerActivationPlan:
    """Canonical host load plan for one explicit TaskController mention."""

    active: bool
    host: str
    transport: str | None
    executor: str | None
    load_order: tuple[str, ...]
    slack_canvases_required: tuple[str, ...]
    interaction_binding: str = "github-reference-mailbox"
    memory_fallback_allowed: bool = False
    full_e2e_runtime_active: bool = False


def mentions_taskcontroller(text: str) -> bool:
    if not isinstance(text, str):
        return False
    return bool(_ALIAS_RE.search(text))


def _dedupe(paths: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return tuple(ordered)


def resolve_taskcontroller_activation(
    text: str,
    *,
    host: str,
    transport: str | None = None,
    executor: str | None = None,
) -> TaskControllerActivationPlan:
    """Resolve mandatory current-repository TaskController entrypoints."""

    host_id = (host or "").strip().lower()
    transport_id = (transport or "").strip().lower() or None
    executor_id = (executor or "").strip().lower() or None

    if not mentions_taskcontroller(text):
        return TaskControllerActivationPlan(
            active=False,
            host=host_id,
            transport=transport_id,
            executor=executor_id,
            load_order=(),
            slack_canvases_required=(),
        )

    paths: list[str] = list(_BASE_LOAD_ORDER)
    paths.extend(_HOST_REQUIRED.get(host_id, ()))
    paths.extend(_INTERACTION_REQUIRED)

    slack_canvases: tuple[str, ...] = ()
    if transport_id == "slack":
        slack_canvases = ("Slack Communication Policy", "Governance Behavior")
        if host_id == "chatgpt":
            paths.extend(_SLACK_CHATGPT_REQUIRED)

    if executor_id in {"hermes", "hermes cloud", "hermes mac", "hermes pc"}:
        paths.extend(_HERMES_EXECUTOR_REQUIRED)

    return TaskControllerActivationPlan(
        active=True,
        host=host_id,
        transport=transport_id,
        executor=executor_id,
        load_order=_dedupe(paths),
        slack_canvases_required=slack_canvases,
    )
