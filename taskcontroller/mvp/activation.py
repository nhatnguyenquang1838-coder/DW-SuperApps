"""Deterministic TaskController activation resolver for the active MVP.

This module makes TaskController activation an explicit workspace contract rather
than a conversational-memory convention. It does not start the dormant Full-E2E
runtime and it performs no I/O. Hosts use the returned ordered entrypoints to
load the current repository instructions before planning or dispatching work.
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

_SLACK_CHATGPT_REQUIRED = (
    "agents/shared/slack-controller-executor-protocol.md",
    "agents/chatgpt-agent/slack-controller-mvp.md",
)

_HERMES_EXECUTOR_REQUIRED = (
    "agents/shared/slack-controller-executor-protocol.md",
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
    memory_fallback_allowed: bool = False
    full_e2e_runtime_active: bool = False


def mentions_taskcontroller(text: str) -> bool:
    """Return True only for an explicit TaskController alias mention."""
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
    """Resolve the mandatory current-repository load chain.

    Explicit mention is the activation boundary. No prior conversation state,
    previous "booted" claim, Slack history, or memory may substitute for the
    returned entrypoints.

    The active current-main MVP uses the protocol bridge only. Full-E2E runtime
    surfaces such as SlackTaskControllerPack, leases, journal, recovery and
    checkpoint remain deferred until separately activated by repository policy.
    """
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
