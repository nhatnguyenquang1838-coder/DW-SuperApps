"""Contract tests for explicit TaskController activation routing.

These tests prevent a regression back to memory-driven / implicit activation.
They intentionally test the small deterministic resolver plus the repository
registry/instruction bindings that every host must load from current state.
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


def test_chatgpt_slack_hermes_loads_complete_canonical_chain():
    plan = resolve_taskcontroller_activation(
        "TaskController: control Hermes Cloud",
        host="chatgpt",
        transport="slack",
        executor="hermes cloud",
    )
    assert plan.active is True
    assert plan.memory_fallback_allowed is False
    assert plan.full_e2e_runtime_active is False
    assert plan.load_order == (
        "AGENTS.md",
        "workspace.yaml",
        "controllers/taskcontroller.yaml",
        "agents/README.md",
        "agents/chatgpt-agent/agent-instructions.md",
        "agents/shared/slack-controller-executor-protocol.md",
        "agents/chatgpt-agent/slack-controller-mvp.md",
        "agents/hermes/agent-instructions.md",
    )
    assert plan.slack_canvases_required == (
        "Slack Communication Policy",
        "Governance Behavior",
    )


def test_chatgpt_non_slack_does_not_invent_slack_overlay():
    plan = resolve_taskcontroller_activation(
        "TaskController inspect this plan",
        host="chatgpt",
    )
    assert plan.active is True
    assert "agents/chatgpt-agent/agent-instructions.md" in plan.load_order
    assert "agents/chatgpt-agent/slack-controller-mvp.md" not in plan.load_order
    assert plan.slack_canvases_required == ()


def test_workspace_registers_taskcontroller_as_controller_not_power():
    workspace = (ROOT / "workspace.yaml").read_text(encoding="utf-8")
    assert "controllers:" in workspace
    assert "id: taskcontroller" in workspace
    assert "kind: workspace-controller" in workspace
    assert "registry: controllers/taskcontroller.yaml" in workspace
    assert "activation: explicit-mention" in workspace


def test_registry_forbids_memory_fallback_and_defers_full_e2e():
    registry = (ROOT / "controllers" / "taskcontroller.yaml").read_text(encoding="utf-8")
    assert "memory_fallback_allowed: false" in registry
    assert "missing_required_entrypoint: BLOCKED" in registry
    assert "full_e2e_runtime: deferred" in registry
    assert "taskcontroller/mvp/activation.py" in registry
    assert "taskcontroller/mvp/protocol_bridge.py" in registry


def test_root_agents_contains_hard_activation_guard():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Any explicit user mention of `TaskController`" in agents
    assert "MUST activate TaskController" in agents
    assert "MUST NOT substitute for the canonical load chain" in agents
    assert "Activating TaskController does not automatically activate GWC" in agents


def test_chatgpt_overlay_blocks_boot_claim_before_load():
    overlay = (
        ROOT / "agents" / "chatgpt-agent" / "agent-instructions.md"
    ).read_text(encoding="utf-8")
    assert "before planning, delegating, posting to Slack, or claiming the controller is booted" in overlay
    assert "Do not substitute conversation memory" in overlay
    assert "activation `BLOCKED`" in overlay
