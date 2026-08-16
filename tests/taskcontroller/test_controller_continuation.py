from __future__ import annotations

from pathlib import Path

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.domain.values import InputRef
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction import (
    A2AEnvelope,
    ControllerContinuation,
    ContinuationPhase,
    ContinuationStatus,
    assert_controller_may_finalize,
    persist_continuation,
    recover_continuation,
)


def _checkpoint(**overrides) -> ControllerContinuation:
    data = {
        "run_id": "run.resilience.1",
        "controller_epoch": 3,
        "phase": ContinuationPhase.WAIT_EXECUTOR.value,
        "status": ContinuationStatus.ACTIVE.value,
        "next_action": "POLL_EXECUTOR",
        "controller_mailbox_ref": "github://org/repo/issues/57#issuecomment-5308536445",
        "controller_seq": 4,
        "executor_actor": "hermes-cloud",
        "executor_mailbox_ref": "github://org/repo/issues/57#issuecomment-5308548539",
        "expected_executor_seq": 4,
        "last_seen_executor_seq": 3,
        "wakeup_binding": "slack-websocket",
        "exact_head_sha": "a" * 40,
        "human_root_ref": "slack://C0BJSPXN7UN/1786898962.707179",
        "updated_at": "2026-08-17T01:10:00+07:00",
    }
    data.update(overrides)
    return ControllerContinuation(**data)


def test_continuation_checkpoint_round_trips_through_existing_run_ledger(tmp_path: Path) -> None:
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    checkpoint = _checkpoint()

    persist_continuation(audit, checkpoint)
    recovered = recover_continuation(audit, checkpoint.run_id)

    assert recovered == checkpoint
    assert recovered is not None
    assert recovered.poll_target().mailbox_ref == checkpoint.executor_mailbox_ref
    assert recovered.poll_target().expected_seq == 4
    audit.close()


def test_active_run_cannot_semantically_finalize() -> None:
    with pytest.raises(TaskControllerValidationError, match="ACTIVE"):
        assert_controller_may_finalize(_checkpoint())

    assert_controller_may_finalize(
        _checkpoint(
            phase=ContinuationPhase.TERMINAL.value,
            status=ContinuationStatus.TERMINAL.value,
            next_action="NONE",
        )
    )


def test_poll_target_contains_only_exact_mailbox_pointer_and_cursor() -> None:
    target = _checkpoint().poll_target()

    assert target.actor == "hermes-cloud"
    assert target.mailbox_ref.endswith("#issuecomment-5308548539")
    assert target.last_seen_seq == 3
    assert target.expected_seq == 4
    assert not hasattr(target, "thread_history")
    assert not hasattr(target, "issue_body")


def test_checkpoint_rejects_non_durable_or_non_monotonic_wait_state() -> None:
    with pytest.raises(TaskControllerValidationError):
        _checkpoint(executor_mailbox_ref="")
    with pytest.raises(TaskControllerValidationError):
        _checkpoint(expected_executor_seq=3, last_seen_executor_seq=3)
    with pytest.raises(TaskControllerValidationError):
        _checkpoint(wakeup_binding="")


def test_reference_envelope_enforces_bounded_context() -> None:
    base = dict(
        run_id="run.resilience.1",
        node_id="node.1",
        sender="controller",
        recipient="hermes-cloud",
        seq=1,
        kind="COMMAND",
        inputs=(InputRef(input_id="src", source_ref="github://org/repo@abc/path.py", media_type="text/x-python"),),
        artifact_refs=(),
        updated_at="2026-08-17T01:10:00+07:00",
    )

    with pytest.raises(TaskControllerValidationError, match="request"):
        A2AEnvelope(**base, request="x" * 5000)

    with pytest.raises(TaskControllerValidationError, match="state"):
        A2AEnvelope(**base, state={"payload": "x" * 10000})


def test_registry_promotes_checkpoint_and_hermes_slack_wakeup_to_pilot_requirements() -> None:
    root = Path(__file__).resolve().parents[2]
    registry = (root / "controllers" / "taskcontroller.yaml").read_text(encoding="utf-8")

    assert "continuation_checkpoint: required-before-dispatch" in registry
    assert "active_run_semantic_final: forbidden" in registry
    assert "exact_mailbox_comment_only: true" in registry
    assert "hermes-cloud:" in registry
    assert "wakeup_binding: slack-websocket" in registry
    assert "required: true" in registry
    assert "    - recovery\n" not in registry
    assert "    - checkpoint\n" not in registry
