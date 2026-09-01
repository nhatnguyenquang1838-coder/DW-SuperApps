"""Contract tests for explicit TaskController activation routing.

These tests prevent a regression back to memory-driven / implicit activation
and lock the reference-based Agent interaction boundary: Slack is the human
control plane while the Agent protocol uses a transport-neutral A2A contract
with a GitHub reference mailbox as the first pilot binding. Human-plane policy
is repository-canonical and has no external Slack policy source.
"""

from __future__ import annotations

from pathlib import Path

from taskcontroller.mvp.activation import (
    TASKCONTROLLER_ALIASES,
    mentions_taskcontroller,
    resolve_taskcontroller_activation,
)

ROOT = Path(__file__).resolve().parents[2]


def test_explicit_aliases_activate_case_insensitively():
    samples = (
        "TaskController",
        "use task controller with Hermes",
        "/dw-taskcontroller run this",
        "please boot TASKCONTROLLER now",
    )
    for text in samples:
        assert mentions_taskcontroller(text) is True


def test_alias_contract_is_stable():
    assert TASKCONTROLLER_ALIASES == (
        "TaskController",
        "task controller",
        "/dw-taskcontroller",
    )


def test_partial_words_do_not_activate():
    for text in ("TaskControllerX", "mytaskcontroller", "dw-taskcontroller-old"):
        assert mentions_taskcontroller(text) is False


def test_unmentioned_controller_returns_inactive_plan():
    plan = resolve_taskcontroller_activation(
        "run the tests",
        host="chatgpt",
        transport="slack",
        executor="hermes cloud",
    )
    assert plan.active is False
    assert plan.load_order == ()
    assert plan.human_plane_policy is None
    assert plan.full_e2e_runtime_active is False
    assert plan.runtime_session is None


def test_chatgpt_slack_hermes_loads_reference_a2a_and_repo_human_plane_policy():
    plan = resolve_taskcontroller_activation(
        "TaskController: control Hermes Cloud",
        host="chatgpt",
        transport="slack",
        executor="hermes cloud",
    )
    assert plan.active is True
    assert plan.memory_fallback_allowed is False
    assert plan.full_e2e_runtime_active is True
    assert plan.runtime_session == "taskcontroller/runtime/session.py"
    assert plan.interaction_binding == "github-reference-mailbox"
    assert plan.load_order == (
        "AGENTS.md",
        "workspace.yaml",
        "controllers/taskcontroller.yaml",
        "agents/README.md",
        "agents/chatgpt-agent/agent-instructions.md",
        "agents/shared/taskcontroller-a2a-protocol.md",
        "agents/shared/taskcontroller-human-plane-policy.md",
        "agents/chatgpt-agent/slack-controller-mvp.md",
        "agents/hermes/agent-instructions.md",
    )
    assert "agents/shared/slack-controller-executor-protocol.md" not in plan.load_order
    assert plan.human_plane_policy == "agents/shared/taskcontroller-human-plane-policy.md"


def test_chatgpt_non_slack_does_not_invent_slack_or_human_plane_overlay():
    plan = resolve_taskcontroller_activation(
        "TaskController inspect this plan",
        host="chatgpt",
    )
    assert plan.active is True
    assert plan.full_e2e_runtime_active is True
    assert plan.runtime_session == "taskcontroller/runtime/session.py"
    assert "agents/chatgpt-agent/agent-instructions.md" in plan.load_order
    assert "agents/chatgpt-agent/slack-controller-mvp.md" not in plan.load_order
    assert "agents/shared/taskcontroller-human-plane-policy.md" not in plan.load_order
    assert plan.human_plane_policy is None


def test_workspace_registers_taskcontroller_as_controller_not_power():
    workspace = (ROOT / "workspace.yaml").read_text(encoding="utf-8")
    assert "controllers:" in workspace
    assert "id: taskcontroller" in workspace
    assert "kind: workspace-controller" in workspace
    assert "registry: controllers/taskcontroller.yaml" in workspace
    assert "activation: explicit-mention" in workspace


def test_registry_forbids_memory_fallback_and_activates_a2a_runtime():
    registry = (ROOT / "controllers" / "taskcontroller.yaml").read_text(encoding="utf-8")
    assert "memory_fallback_allowed: false" in registry
    assert "missing_required_entrypoint: BLOCKED" in registry
    assert "runtime_session: taskcontroller/runtime/session.py" in registry
    assert "full_e2e_runtime: active" in registry
    assert "full_e2e_runtime: deferred" not in registry
    assert "legacy_slack_pilot: compatibility-only" in registry
    assert "taskcontroller/mvp/activation.py" in registry
    assert "taskcontroller/mvp/protocol_bridge.py" in registry


def test_registry_separates_agent_binding_from_slack_human_plane():
    registry = (ROOT / "controllers" / "taskcontroller.yaml").read_text(encoding="utf-8")
    assert "pilot_binding: github-reference-mailbox" in registry
    assert "human_control_plane: slack" in registry
    assert "agents/shared/taskcontroller-a2a-protocol.md" in registry
    assert "one_actor_one_mutable_mailbox: true" in registry
    assert "thread_semantics: controller-command-executor-report-evidence" not in registry


def test_registry_routes_human_plane_policy_only_to_dw_superapps_repo():
    registry = (ROOT / "controllers" / "taskcontroller.yaml").read_text(encoding="utf-8")
    assert "canonical_policy: agents/shared/taskcontroller-human-plane-policy.md" in registry
    assert "human_plane_policy_authority: agents/shared/taskcontroller-human-plane-policy.md" in registry
    assert "policy_source: current-repository-state" in registry
    assert "external_policy_sources: forbidden" in registry
    assert "external_human_plane_policy_sources: forbidden" in registry
    assert "slack_canvases" not in registry
    assert "Slack Communication Policy" not in registry
    assert "Governance Behavior" not in registry


def test_root_agents_contains_hard_activation_guard():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Any explicit user mention of `TaskController`" in agents
    assert "MUST activate TaskController" in agents
    assert "MUST NOT substitute for the canonical load chain" in agents
    assert "Activating TaskController does not automatically activate any Power" in agents


def test_root_agents_declares_slack_human_plane_and_reference_agent_binding():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Slack is the Human Control Plane" in agents
    assert "GitHub reference mailbox is the current Agent interaction pilot binding" in agents
    assert "Slack thread history MUST NOT be the canonical Agent execution journal" in agents
    assert "agents/shared/taskcontroller-human-plane-policy.md" in agents
    assert "Slack Communication Policy" not in agents
    assert "Governance Behavior" not in agents


def test_chatgpt_overlay_blocks_boot_claim_before_repo_load_and_external_policy():
    overlay = (
        ROOT / "agents" / "chatgpt-agent" / "agent-instructions.md"
    ).read_text(encoding="utf-8")
    assert "before planning, delegating, posting to Slack, or claiming the controller is booted" in overlay
    assert "Do not substitute conversation memory" in overlay
    assert "activation `BLOCKED`" in overlay
    assert "agents/shared/taskcontroller-human-plane-policy.md" in overlay
    assert "only TaskController Slack policy input" in overlay
    assert "GWC" not in overlay


def test_agent_protocol_is_reference_based_and_transport_neutral():
    protocol = (
        ROOT / "agents" / "shared" / "taskcontroller-a2a-protocol.md"
    ).read_text(encoding="utf-8")
    assert "Reference-Based Agent Interaction Protocol" in protocol
    assert "one actor = one mutable mailbox comment" in protocol
    assert "context by exact reference" in protocol
    assert "Slack is not the Executor progress transport" in protocol
    assert "A2A HTTP" in protocol


def test_human_plane_policy_is_repo_canonical_without_external_policy_sources():
    policy = (
        ROOT / "agents" / "shared" / "taskcontroller-human-plane-policy.md"
    ).read_text(encoding="utf-8")
    assert "canonical repository source of truth" in policy
    assert "No Slack-hosted policy document" in policy
    assert "repository policy is the only policy input" in policy
    assert "Slack Communication Policy" not in policy
    assert "Governance Behavior" not in policy
    assert "GWC" not in policy


def test_slack_overlay_is_human_projection_not_machine_journal():
    overlay = (
        ROOT / "agents" / "chatgpt-agent" / "slack-controller-mvp.md"
    ).read_text(encoding="utf-8")
    assert "Slack is the Human Control Plane" in overlay
    assert "semantic timeline" in overlay
    assert "Do not use Slack thread replies as the Executor progress transport" in overlay
    assert "mailbox cursor" in overlay
    assert "agents/shared/taskcontroller-human-plane-policy.md" in overlay
    assert "Do not load Slack-hosted policy documents" in overlay
    assert "Slack Communication Policy" not in overlay
    assert "Governance Behavior" not in overlay


def test_hermes_reports_to_mailbox_not_slack_journal():
    overlay = (ROOT / "agents" / "hermes" / "agent-instructions.md").read_text(
        encoding="utf-8"
    )
    assert "GitHub reference mailbox" in overlay
    assert "update its own mailbox comment in place" in overlay
    assert "Do not use Slack as the normal progress journal" in overlay


def test_active_taskcontroller_requires_mailbox_boot_before_first_dispatch():
    plan = resolve_taskcontroller_activation(
        "TaskController: control Hermes Mac",
        host="chatgpt",
        transport="slack",
        executor="hermes mac",
    )

    assert plan.active is True
    assert plan.full_e2e_runtime_active is True
    assert plan.runtime_session == "taskcontroller/runtime/session.py"
    assert plan.mailbox_boot_required is True
    assert plan.mailbox_boot_fail_closed is True
    assert plan.machine_progress_transport == "github-reference-mailbox"
    assert plan.slack_machine_progress_allowed is False
    assert plan.pointer_only_wakeup is True


def test_registry_forbids_slack_machine_fallback_when_a2a_is_active():
    registry = (ROOT / "controllers" / "taskcontroller.yaml").read_text(encoding="utf-8")

    assert "mailbox_boot:" in registry
    assert "required_when_active: true" in registry
    assert "before_first_dispatch: true" in registry
    assert "controller_mailbox_required: true" in registry
    assert "executor_mailbox_required: true" in registry
    assert "exact_readback_required: true" in registry
    assert "missing_behavior: TASKCONTROLLER_MAILBOX_NOT_MATERIALIZED" in registry
    assert "slack_machine_transport_fallback: forbidden" in registry


def test_active_host_overlays_do_not_load_legacy_slack_machine_protocol():
    paths = (
        ROOT / "agents" / "chatgpt-agent" / "agent-instructions.md",
        ROOT / "agents" / "chatgpt-agent" / "slack-controller-mvp.md",
        ROOT / "agents" / "hermes" / "agent-instructions.md",
    )

    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "agents/shared/slack-controller-executor-protocol.md" not in text


def test_active_taskcontroller_chain_has_no_gwc_or_slack_canvas_policy_dependency():
    active_paths = (
        ROOT / "controllers" / "taskcontroller.yaml",
        ROOT / "agents" / "README.md",
        ROOT / "agents" / "chatgpt-agent" / "agent-instructions.md",
        ROOT / "agents" / "shared" / "taskcontroller-human-plane-policy.md",
        ROOT / "agents" / "chatgpt-agent" / "slack-controller-mvp.md",
        ROOT / "taskcontroller" / "mvp" / "activation.py",
    )

    forbidden = (
        "Slack Communication Policy",
        "Governance Behavior",
        "slack_canvas_projections_optional",
        "slack_canvases_required",
    )

    for path in active_paths:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{token!r} leaked into {path}"

    for path in active_paths[1:5]:
        text = path.read_text(encoding="utf-8")
        assert "GWC" not in text, f"GWC-specific TaskController coupling leaked into {path}"
