"""TC-MBX-302: durable continuation before v2 dispatch and recovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.audit.facade import AuditFacade
from taskcontroller.controlplane.continuation_dispatch import (
    prepare_v2_dispatch,
    recover_v2_dispatch,
)
from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction import (
    ControllerContinuation,
    ContinuationPhase,
    ContinuationStatus,
)
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope


_SOURCE = {
    "repository": "owner/repo",
    "commit_sha": "a" * 40,
    "path": "taskcontroller/interaction/continuation.py",
    "blob_digest": "sha256:" + "1" * 64,
}


def _checkpoint(**changes: Any) -> ControllerContinuation:
    values: dict[str, Any] = {
        "run_id": "run-302",
        "controller_epoch": 2,
        "phase": ContinuationPhase.WAIT_EXECUTOR.value,
        "status": ContinuationStatus.ACTIVE.value,
        "next_action": "POLL_EXECUTOR",
        "controller_mailbox_ref": "github://owner/repo/issues/302#controller",
        "controller_seq": 4,
        "executor_actor": "hermes-mac",
        "executor_mailbox_ref": "github://owner/repo/issues/302#executor",
        "expected_executor_seq": 4,
        "last_seen_executor_seq": 3,
        "wakeup_binding": "slack-websocket",
        "exact_head_sha": "a" * 40,
        "updated_at": "2026-09-11T05:30:00+07:00",
        "human_root_ref": "slack://C0BJSPXN7UN/302",
    }
    values.update(changes)
    return ControllerContinuation(**values)


def _request(**changes: Any) -> BoundedMailboxRequest:
    values: dict[str, Any] = {
        "message_id": "message-302",
        "run_id": "run-302",
        "node_id": "node-302",
        "seq": 4,
        "correlation_id": "correlation-302",
        "contract_id": "contract-302",
        "plan_version": "plan-302",
        "contract_digest": "sha256:" + "3" * 64,
        "boundary_digest": "sha256:" + "4" * 64,
        "source_digest": "sha256:" + "5" * 64,
        "source_manifest_ref": "source-manifest-302",
        "objective": "Recover the Controller from durable mailbox evidence.",
        "scope": {
            "allowed_actions": ["read_repo", "run_tests"],
            "denied_actions": ["merge", "deploy"],
            "writable_targets": ["taskcontroller"],
            "source_roots": ["taskcontroller", "tests/taskcontroller"],
            "max_children": 0,
            "max_parallel": 1,
            "max_depth": 0,
        },
        "authority_constraints": {
            "denied_actions": ["merge", "deploy"],
            "writable_targets": ["taskcontroller"],
        },
        "acceptance_criteria": (
            "The checkpoint is durable before dispatch.",
            "A restart does not require chat history.",
        ),
        "source_refs": (_SOURCE,),
        "evidence_refs": ("evidence://tests/302",),
        "standards_profile": {
            "profile_id": "standards.default",
            "version": "1",
            "digest": "sha256:" + "6" * 64,
        },
        "standards_profile_ref": "standards.default/v1",
        "recipient_capability": "taskcontroller.executor",
        "agent_instance": "hermes-mac",
        "environment_requirements": {
            "os": "darwin",
            "runtime": "python3.11",
            "arch": "arm64",
        },
        "attempt_id": "attempt-302",
        "attempt_number": 1,
        "lease_generation": 7,
        "fencing_token": "fence-302",
        "lease_expires_at": "2026-09-11T06:00:00+07:00",
        "idempotency_key": "idem-302",
        "producer_namespace": "controller",
        "producer_actor_id": "controller-302",
        "execution_id": "execution-302",
    }
    values.update(changes)
    return BoundedMailboxRequest(**values)


class _RecordingContinuationStore:
    """Audit-backed store that exposes persistence ordering without fake state."""

    def __init__(self, audit: AuditFacade) -> None:
        self.audit = audit
        self.calls: list[str] = []

    def save_manifest(self, manifest) -> None:
        self.calls.append("save_manifest")
        self.audit.save_manifest(manifest)

    def load_manifest(self, run_id: str, manifest_kind: str):
        self.calls.append("load_manifest")
        return self.audit.load_manifest(run_id, manifest_kind)


def test_prepare_persists_checkpoint_before_v2_request_and_binds_id(tmp_path: Path) -> None:
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    store = _RecordingContinuationStore(audit)
    checkpoint = _checkpoint()

    envelope = prepare_v2_dispatch(store, checkpoint, _request())

    assert store.calls == ["load_manifest", "save_manifest", "load_manifest"]
    assert envelope.to_dict()["payload"]["checkpoint_id"] == checkpoint.checkpoint_id
    assert envelope.to_dict()["digest"] == envelope.digest()
    assert recover_v2_dispatch(store, envelope) == checkpoint
    audit.close()


def test_checkpoint_id_is_deterministic_and_changes_with_bounded_state() -> None:
    first = _checkpoint()
    same = _checkpoint()
    changed = _checkpoint(controller_epoch=3)

    assert first.checkpoint_id == same.checkpoint_id
    assert first.checkpoint_id.startswith("sha256:")
    assert changed.checkpoint_id != first.checkpoint_id


def test_controller_restart_recovers_from_ledger_and_serialized_mailbox_without_chat(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "run-ledger.sqlite3"
    audit = AuditFacade(db_path)
    checkpoint = _checkpoint()
    envelope = prepare_v2_dispatch(audit, checkpoint, _request())
    mailbox_bytes = json.loads(json.dumps(envelope.to_dict(), sort_keys=True))
    audit.close()

    restarted_audit = AuditFacade(db_path)
    restored_mailbox = V2MailboxEnvelope.from_dict(mailbox_bytes)
    recovered = recover_v2_dispatch(restarted_audit, restored_mailbox)

    assert recovered == checkpoint
    assert recovered.checkpoint_id == restored_mailbox.to_dict()["payload"]["checkpoint_id"]
    restarted_audit.close()


def test_prepare_rejects_request_run_or_sequence_mismatch_before_persistence(tmp_path: Path) -> None:
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    checkpoint = _checkpoint()

    with pytest.raises(TaskControllerValidationError, match="run_id"):
        prepare_v2_dispatch(audit, checkpoint, _request(run_id="other-run"))
    with pytest.raises(TaskControllerValidationError, match="seq"):
        prepare_v2_dispatch(audit, checkpoint, _request(seq=5))

    assert audit.load_manifest(checkpoint.run_id, "dw.taskcontroller.continuation/v1") is None
    audit.close()


def test_recovery_rejects_wrong_checkpoint_id_and_recipient(tmp_path: Path) -> None:
    audit = AuditFacade(tmp_path / "run-ledger.sqlite3")
    checkpoint = _checkpoint()
    prepare_v2_dispatch(audit, checkpoint, _request())

    wrong_id = _request(checkpoint_id="sha256:" + "9" * 64)
    wrong_id_envelope = compile_bounded_mailbox_request(wrong_id)
    with pytest.raises(TaskControllerValidationError, match="checkpoint ID"):
        recover_v2_dispatch(audit, wrong_id_envelope)

    wrong_recipient = _request(
        agent_instance="hermes-cloud",
        checkpoint_id=checkpoint.checkpoint_id,
    )
    wrong_recipient_envelope = compile_bounded_mailbox_request(wrong_recipient)
    with pytest.raises(TaskControllerValidationError, match="AgentInstance"):
        recover_v2_dispatch(audit, wrong_recipient_envelope)
    audit.close()


def test_compiler_rejects_payload_checkpoint_override() -> None:
    request = _request(payload={"checkpoint_id": "sha256:" + "8" * 64})

    with pytest.raises(TaskControllerValidationError, match="compiler-owned"):
        compile_bounded_mailbox_request(request)
