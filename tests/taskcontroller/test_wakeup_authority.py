from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_registry_separates_mailbox_data_path_from_wakeup_notification() -> None:
    registry = (ROOT / "controllers" / "taskcontroller.yaml").read_text(encoding="utf-8")
    assert "pilot_binding: github-reference-mailbox" in registry
    assert "protocol: dw.taskcontroller.wakeup/v1" in registry
    assert "pilot_binding: slack-wakeup" in registry
    assert "pointer_only: true" in registry
    assert "command_payload_forbidden: true" in registry
    assert "progress_payload_forbidden: true" in registry


def test_a2a_protocol_declares_pointer_only_wakeup_semantics() -> None:
    protocol = (
        ROOT / "agents" / "shared" / "taskcontroller-a2a-protocol.md"
    ).read_text(encoding="utf-8")
    assert "## Wake-up notification" in protocol
    assert "dw.taskcontroller.wakeup/v1" in protocol
    assert "pointer-only" in protocol
    assert "Tool/progress narration on the wake-up channel is forbidden" in protocol


def test_slack_overlay_keeps_wakeup_separate_from_human_and_progress_planes() -> None:
    overlay = (
        ROOT / "agents" / "chatgpt-agent" / "slack-controller-mvp.md"
    ).read_text(encoding="utf-8")
    assert "SlackWakeupBinding" in overlay
    assert "MUST NOT include the command request" in overlay
    assert "its semantic result goes to its Agent mailbox" in overlay
    assert "Human control input, wake-up delivery and Executor progress transport are separate concerns" in overlay


def test_hermes_wakeup_requires_zero_slack_progress_replies() -> None:
    overlay = (ROOT / "agents" / "hermes" / "agent-instructions.md").read_text(
        encoding="utf-8"
    )
    assert "## Pointer-only wake-up" in overlay
    assert "do not narrate tools" in overlay
    assert "zero Executor Slack progress replies" in overlay
    assert "publish semantic result to the same Executor mailbox comment" in overlay
