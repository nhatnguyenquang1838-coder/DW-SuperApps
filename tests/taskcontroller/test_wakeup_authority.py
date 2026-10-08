from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_registry_separates_mailbox_data_path_from_wakeup_notification() -> None:
    registry = (ROOT / "controllers" / "taskcontroller.yaml").read_text(encoding="utf-8")
    assert "canonical_binding: github-mailbox-v2" in registry
    assert "compatibility_binding: github-reference-mailbox-v1" in registry
    assert "protocol: dw.taskcontroller.wakeup/v1" in registry
    assert "controller_wait_action: AWAIT_EXECUTOR_EVENT" in registry
    assert "periodic_mailbox_polling: forbidden" in registry
    assert "wakeup_binding: mailbox-event" in registry
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
    assert "The Controller MUST NOT run a periodic mailbox polling cadence" in protocol
    assert "Slack MUST NOT be used as the machine wake-up path" in protocol


def test_slack_overlay_keeps_wakeup_separate_from_human_and_progress_planes() -> None:
    overlay = (
        ROOT / "agents" / "chatgpt-agent" / "slack-controller-mvp.md"
    ).read_text(encoding="utf-8")
    assert "SlackWakeupBinding" in overlay
    assert "MUST NOT include the command request" in overlay
    assert "its semantic result goes to its Agent mailbox" in overlay
    assert "Human control input, wake-up delivery and Executor progress transport are separate concerns" in overlay


def test_slack_overlay_forbids_raw_connector_bypass_of_root_thread_binding() -> None:
    overlay = (
        ROOT / "agents" / "chatgpt-agent" / "slack-controller-mvp.md"
    ).read_text(encoding="utf-8")
    assert "Direct Slack connector calls are transport only" in overlay
    assert "existing RootCard binding" in overlay
    assert "UPDATE_ROOT" in overlay
    assert "REPLY_THREAD" in overlay
    assert "WakeupSignal.to_dict()" in overlay
    assert "Cross-channel rebinding is forbidden" in overlay


def test_hermes_uses_event_driven_mailbox_delivery_without_polling() -> None:
    overlay = (ROOT / "agents" / "hermes" / "agent-instructions.md").read_text(
        encoding="utf-8"
    )
    assert "## Event-driven mailbox delivery" in overlay
    assert "does not use periodic mailbox polling" in overlay
    assert "does not use Slack as an Executor wake-up path" in overlay
    assert "append a new typed event through `GitHubMailboxRepository`" in overlay
