"""Deterministic TaskController activation resolver for the active A2A runtime.

TaskController activation is resolved from current repository state, never from
conversation memory or external policy documents. Agent interaction semantics
are transport-neutral; the current binding is a GitHub reference mailbox while
Slack is the human control/visibility plane. Every active plan explicitly binds
the executable runtime session that must boot mailboxes before first Executor
dispatch.
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

TASKCONTROLLER_RUNTIME_SESSION = "taskcontroller/runtime/session.py"

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

_HUMAN_PLANE_REQUIRED = (
    "agents/shared/taskcontroller-human-plane-policy.md",
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
    """Canonical host load and executable-runtime plan for TaskController."""

    active: bool
    host: str
    transport: str | None
    executor: str | None
    load_order: tuple[str, ...]
    human_plane_policy: str | None = None
    interaction_binding: str = "github-reference-mailbox"
    memory_fallback_allowed: bool = False
    full_e2e_runtime_active: bool = False
    runtime_session: str | None = None
    mailbox_boot_required: bool = False
    mailbox_boot_fail_closed: bool = False
    machine_progress_transport: str | None = None
    slack_machine_progress_allowed: bool = False
    pointer_only_wakeup: bool = False


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
    """Resolve mandatory current-repository TaskController entrypoints/runtime."""

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
        )

    paths: list[str] = list(_BASE_LOAD_ORDER)
    paths.extend(_HOST_REQUIRED.get(host_id, ()))
    paths.extend(_INTERACTION_REQUIRED)

    human_plane_policy: str | None = None
    if transport_id == "slack":
        paths.extend(_HUMAN_PLANE_REQUIRED)
        human_plane_policy = _HUMAN_PLANE_REQUIRED[0]
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
        human_plane_policy=human_plane_policy,
        full_e2e_runtime_active=True,
        runtime_session=TASKCONTROLLER_RUNTIME_SESSION,
        mailbox_boot_required=True,
        mailbox_boot_fail_closed=True,
        machine_progress_transport="github-reference-mailbox",
        slack_machine_progress_allowed=False,
        pointer_only_wakeup=True,
    )
