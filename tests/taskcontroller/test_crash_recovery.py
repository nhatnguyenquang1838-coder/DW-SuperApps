"""TC-MBX-805: deterministic controller crash recovery without chat replay."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction import (
    A2AEnvelope,
    ControllerContinuation,
    ContinuationPhase,
    ContinuationStatus,
    MailboxCursor,
    bind_continuation,
    render_mailbox_comment,
)
from taskcontroller.controlplane.crash_recovery import (
    CRASH_RECOVERY_MANIFEST_KIND,
    ControllerRecoveryBinding,
    CrashRecoveryError,
    MailboxRecoveryRef,
    RunLedgerRef,
    persist_recovery_binding,
    recover_controller_after_restart,
    recover_recovery_binding,
)


_HEAD = "a" * 40
_CONTROLLER_REF = "github://owner/repo/issues/805#controller"
_EXECUTOR_REF = "github://owner/repo/issues/805#executor"


def _checkpoint(**changes: Any) -> ControllerContinuation:
    values: dict[str, Any] = {
        "run_id": "run.crash.805",
        "controller_epoch": 2,
        "phase": ContinuationPhase.WAIT_EXECUTOR.value,
        "status": ContinuationStatus.ACTIVE.value,
        "next_action": "POLL_EXECUTOR",
        "controller_mailbox_ref": _CONTROLLER_REF,
        "controller_seq": 4,
        "executor_actor": "hermes-mac",
        "executor_mailbox_ref": _EXECUTOR_REF,
        "expected_executor_seq": 4,
        "last_seen_executor_seq": 3,
        "wakeup_binding": "slack-websocket",
        "exact_head_sha": _HEAD,
        "updated_at": "2026-09-12T21:00:00+07:00",
        "human_root_ref": "slack://C0BJSPXN7UN/805",
    }
    values.update(changes)
    return ControllerContinuation(**values)


def _binding(**changes: Any) -> ControllerRecoveryBinding:
    checkpoint = changes.pop("continuation", _checkpoint())
    controller_cursor = MailboxCursor(
        actor="controller",
        last_seen_seq=checkpoint.controller_seq,
        mailbox_ref=checkpoint.controller_mailbox_ref,
        last_head_sha=checkpoint.exact_head_sha,
    )
    executor_cursor = MailboxCursor(
        actor=checkpoint.executor_actor,
        last_seen_seq=checkpoint.last_seen_executor_seq,
        mailbox_ref=checkpoint.executor_mailbox_ref,
        last_head_sha=checkpoint.exact_head_sha,
    )
    values: dict[str, Any] = {
        "run_id": checkpoint.run_id,
        "node_id": "node.crash.805",
        "controller_actor": "controller",
        "continuation": checkpoint,
        "ledger_ref": RunLedgerRef(
            run_id=checkpoint.run_id,
            manifest_kind=CRASH_RECOVERY_MANIFEST_KIND,
        ),
        "controller_mailbox": MailboxRecoveryRef(
            actor="controller",
            mailbox_ref=checkpoint.controller_mailbox_ref,
            cursor=controller_cursor,
            target_seq=checkpoint.controller_seq,
        ),
        "executor_mailbox": MailboxRecoveryRef(
            actor=checkpoint.executor_actor,
            mailbox_ref=checkpoint.executor_mailbox_ref,
            cursor=executor_cursor,
            target_seq=checkpoint.expected_executor_seq,
        ),
        "exact_head_sha": checkpoint.exact_head_sha,
        "updated_at": checkpoint.updated_at,
        "evidence_refs": ("github://owner/repo/issues/805#evidence",),
        "normalized_result_ref": None,
    }
    values.update(changes)
    return ControllerRecoveryBinding(**values)


def _controller_envelope(binding: ControllerRecoveryBinding) -> A2AEnvelope:
    envelope = A2AEnvelope(
        run_id=binding.run_id,
        node_id=binding.node_id,
        sender=binding.controller_actor,
        recipient=binding.continuation.executor_actor,
        seq=binding.continuation.controller_seq,
        kind="COMMAND",
        request="Resume bounded work from canonical mailbox evidence.",
        state={"head_sha": binding.exact_head_sha},
        updated_at=binding.updated_at,
    )
    return bind_continuation(envelope, binding.continuation)


class _CanonicalMailbox:
    def __init__(self, body: str) -> None:
        self.body = body
        self.reads: list[str] = []

    def read_mailbox(self, mailbox_ref: str) -> str:
        self.reads.append(mailbox_ref)
        if mailbox_ref != _CONTROLLER_REF:
            return ""
        return self.body


def test_binding_round_trips_through_run_ledger_manifest(tmp_path: Path) -> None:
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    binding = _binding()

    persisted = persist_recovery_binding(audit, binding)
    recovered = recover_recovery_binding(audit, binding.run_id)

    assert persisted == binding
    assert recovered == binding
    manifest = audit.load_manifest(binding.run_id, CRASH_RECOVERY_MANIFEST_KIND)
    assert manifest is not None
    assert manifest.metadata["binding_digest"] == binding.binding_digest
    audit.close()


def test_kill_restart_recovers_byte_equivalent_controller_boundary_without_chat(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "run-ledger.sqlite3"
    binding = _binding()
    mailbox = _CanonicalMailbox(render_mailbox_comment(_controller_envelope(binding)))

    audit = AuditFacade(db_path)
    persist_recovery_binding(audit, binding)
    audit.close()

    restarted = AuditFacade(db_path)
    first = recover_controller_after_restart(
        restarted,
        mailbox,
        run_id=binding.run_id,
        controller_actor=binding.controller_actor,
    )
    second = recover_controller_after_restart(
        restarted,
        mailbox,
        run_id=binding.run_id,
        controller_actor=binding.controller_actor,
    )

    assert first.binding == binding
    assert first.controller_envelope == _controller_envelope(binding)
    assert first.next_action == "POLL_EXECUTOR"
    assert first.to_dict() == second.to_dict()
    assert first.recovery_digest == second.recovery_digest
    assert mailbox.reads == [binding.controller_mailbox.mailbox_ref] * 2
    assert "chat_history" not in first.to_dict()
    assert "thread_history" not in first.to_dict()
    restarted.close()


def test_recovery_uses_only_controller_mailbox_ref_not_human_root_history(tmp_path: Path) -> None:
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    binding = _binding()
    persist_recovery_binding(audit, binding)
    mailbox = _CanonicalMailbox(render_mailbox_comment(_controller_envelope(binding)))

    result = recover_controller_after_restart(
        audit,
        mailbox,
        run_id=binding.run_id,
        controller_actor="controller",
    )

    assert result.binding.continuation.human_root_ref == "slack://C0BJSPXN7UN/805"
    assert mailbox.reads == [binding.controller_mailbox.mailbox_ref]
    audit.close()


def test_recovery_rejects_continuation_manifest_conflict_fail_closed(tmp_path: Path) -> None:
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    binding = _binding()
    persist_recovery_binding(audit, binding)

    conflicting = replace(binding.continuation, controller_epoch=3)
    audit.save_manifest(conflicting.to_manifest())

    with pytest.raises(CrashRecoveryError, match="RECOVERY_RECONCILIATION_BLOCKED"):
        recover_recovery_binding(audit, binding.run_id)
    audit.close()


def test_recovery_rejects_tampered_controller_mailbox_head_fail_closed(tmp_path: Path) -> None:
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    binding = _binding()
    persist_recovery_binding(audit, binding)
    tampered = replace(_controller_envelope(binding), state={"head_sha": "b" * 40})
    mailbox = _CanonicalMailbox(render_mailbox_comment(tampered))

    with pytest.raises(CrashRecoveryError, match="RECOVERY_RECONCILIATION_BLOCKED"):
        recover_controller_after_restart(
            audit,
            mailbox,
            run_id=binding.run_id,
            controller_actor="controller",
        )
    audit.close()


def test_recovery_rejects_missing_mailbox_readback_fail_closed(tmp_path: Path) -> None:
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    binding = _binding()
    persist_recovery_binding(audit, binding)
    mailbox = _CanonicalMailbox("")

    with pytest.raises(CrashRecoveryError, match="RECOVERY_RECONCILIATION_BLOCKED"):
        recover_controller_after_restart(
            audit,
            mailbox,
            run_id=binding.run_id,
            controller_actor="controller",
        )
    audit.close()


def test_binding_rejects_foreign_cursor_and_unknown_chat_history_fields() -> None:
    checkpoint = _checkpoint()
    foreign_cursor = MailboxCursor(
        actor="other-controller",
        last_seen_seq=checkpoint.controller_seq,
        mailbox_ref=checkpoint.controller_mailbox_ref,
        last_head_sha=checkpoint.exact_head_sha,
    )
    with pytest.raises(TaskControllerValidationError, match="cursor actor"):
        MailboxRecoveryRef(
            actor="controller",
            mailbox_ref=checkpoint.controller_mailbox_ref,
            cursor=foreign_cursor,
            target_seq=checkpoint.controller_seq,
        )

    payload = _binding().to_dict()
    payload["chat_history"] = ["must never be a recovery input"]
    with pytest.raises(CrashRecoveryError, match="unknown fields"):
        ControllerRecoveryBinding.from_dict(payload)


def test_conflicting_existing_recovery_manifest_is_not_overwritten(tmp_path: Path) -> None:
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    original = _binding()
    persist_recovery_binding(audit, original)
    conflicting = _binding(node_id="node.other")

    with pytest.raises(CrashRecoveryError, match="RECOVERY_RECONCILIATION_BLOCKED"):
        persist_recovery_binding(audit, conflicting)

    assert recover_recovery_binding(audit, original.run_id) == original
    audit.close()


def test_serialized_binding_is_deterministic_and_contains_refs_not_transcript() -> None:
    first = _binding()
    second = _binding()

    assert json.dumps(first.to_dict(), sort_keys=True, separators=(",", ":")) == json.dumps(
        second.to_dict(), sort_keys=True, separators=(",", ":")
    )
    assert first.binding_digest == second.binding_digest
    serialized = json.dumps(first.to_dict(), sort_keys=True)
    assert "github://owner/repo/issues/805#controller" in serialized
    assert "slack-websocket" in serialized
    assert "must never be a recovery input" not in serialized
    assert "conversation_history" not in serialized
