"""Deterministic TaskController activation resolver for the active A2A runtime.

TaskController activation is resolved from current repository state, never from
conversation memory or external policy documents. Agent interaction semantics
are transport-neutral; the canonical machine binding is append-only GitHub
mailbox/v2 while Slack is the human control/visibility plane. Every active plan
explicitly binds the executable high-integrity runtime session that materializes
Controller dispatch, bootstraps Executor consumption, resumes Controller state,
and recovers without chat/Slack replay.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from taskcontroller.interaction.mailbox_v2 import V1_PROTOCOL, V2_PROTOCOL


TASKCONTROLLER_ALIASES = (
    "TaskController",
    "task controller",
    "/dw-taskcontroller",
)

TASKCONTROLLER_RUNTIME_SESSION = "taskcontroller/runtime/high_integrity_session.py"
TASKCONTROLLER_COMPATIBILITY_RUNTIME_SESSION = "taskcontroller/runtime/session.py"
TASKCONTROLLER_CONTROLLER_ADMISSION_GUARD = "taskcontroller/controlplane/controller_admission.py"

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
    interaction_binding: str = "github-mailbox-v2"
    memory_fallback_allowed: bool = False
    full_e2e_runtime_active: bool = False
    runtime_session: str | None = None
    mailbox_boot_required: bool = False
    # This boolean applies to actual Executor dispatch, not native Controller BOOT.
    mailbox_boot_boundary: str | None = None
    controller_only_progress_allowed_without_executor: bool = False
    mailbox_boot_fail_closed: bool = False
    machine_progress_transport: str | None = None
    slack_machine_progress_allowed: bool = False
    pointer_only_wakeup: bool = False
    interaction_protocol: str = V2_PROTOCOL
    requires_v2_semantics: bool = True
    controller_admission_required: bool = False
    controller_admission_guard: str | None = None
    raw_comment_body_sha_authoritative: bool = False
    whole_issue_machine_state_allowed: bool = False
    schema_resolution_mode: str = "descriptor-bound"


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
    requires_v2_semantics: bool | None = None,
) -> TaskControllerActivationPlan:
    """Resolve mandatory current-repository TaskController entrypoints/runtime.

    mailbox/v2 is the default canonical machine protocol.  Passing
    requires_v2_semantics=False is an explicit compatibility opt-in to the
    demoted A2A/v1 mutable-mailbox runtime. Source/Controller activation is
    distinct from first Executor dispatch readiness; Controller-native
    understanding/planning gates never require an Executor acknowledgement.
    """

    host_id = (host or "").strip().lower()
    transport_id = (transport or "").strip().lower() or None
    executor_id = (executor or "").strip().lower() or None
    resolved_v2 = True if requires_v2_semantics is None else requires_v2_semantics

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
        runtime_session=(
            TASKCONTROLLER_RUNTIME_SESSION
            if resolved_v2
            else TASKCONTROLLER_COMPATIBILITY_RUNTIME_SESSION
        ),
        interaction_binding=(
            "github-mailbox-v2" if resolved_v2 else "github-reference-mailbox-v1"
        ),
        mailbox_boot_required=True,
        mailbox_boot_boundary="first_executor_dispatch",
        controller_only_progress_allowed_without_executor=True,
        mailbox_boot_fail_closed=True,
        machine_progress_transport=(
            "github-mailbox-v2" if resolved_v2 else "github-reference-mailbox-v1"
        ),
        slack_machine_progress_allowed=False,
        pointer_only_wakeup=True,
        interaction_protocol=V2_PROTOCOL if resolved_v2 else V1_PROTOCOL,
        requires_v2_semantics=resolved_v2,
        controller_admission_required=resolved_v2,
        controller_admission_guard=(
            TASKCONTROLLER_CONTROLLER_ADMISSION_GUARD
            if resolved_v2
            else None
        ),
        raw_comment_body_sha_authoritative=False,
        whole_issue_machine_state_allowed=False,
        schema_resolution_mode="descriptor-bound",
    )
