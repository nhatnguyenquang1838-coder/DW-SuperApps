"""TC-MBX-406: auditable Hermes bootstrap receipts."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from taskcontroller.controlplane.request_compiler import (
    BoundedMailboxRequest,
    compile_bounded_mailbox_request,
)
from taskcontroller.domain.values import InputRef
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.envelope import A2AEnvelope
from taskcontroller.interaction.executor_entrypoint import (
    BOOTSTRAP_BOOTSTRAPPED,
    BOOTSTRAP_STARTED,
    ActiveAttemptFence,
    BootstrapReceipt,
    BootstrapReceiptError,
    ExecutorMailboxRequest,
)
from taskcontroller.interaction.wakeup import WakeupSignal
from taskcontroller.standards import (
    ContextPackBuilder,
    EvidenceRef,
    StandardsProfile,
    StandardsResolver,
    StandardsSourceRef,
)


_COMMIT_TASK = "a" * 40
_COMMIT_STANDARDS = "c" * 40


class SourceReader:
    def __init__(self, values: dict[tuple[str, str], bytes]) -> None:
        self.values = values

    def read_exact(self, source: StandardsSourceRef) -> bytes:
        return self.values[(source.commit_sha, source.path)]


class EvidenceReader:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values

    def read_exact(self, evidence: EvidenceRef) -> bytes:
        return self.values[evidence.ref]


def _source(commit: str, path: str, content: str) -> StandardsSourceRef:
    return StandardsSourceRef(
        repository="owner-repo",
        commit_sha=commit,
        path=path,
        blob_digest="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
    )


def _evidence(ref: str, content: str) -> EvidenceRef:
    return EvidenceRef(
        ref=ref,
        digest="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
        media_type="text/plain",
    )


def _context_pack(
    *, standards_content: str = "rules", task_content: str = "task source"
) -> tuple[Any, Any, Any, Any]:
    standards_source = _source(_COMMIT_STANDARDS, "standards/AGENTS.md", standards_content)
    standards_reader = SourceReader(
        {(_COMMIT_STANDARDS, standards_source.path): standards_content.encode()}
    )
    profile = StandardsProfile.create(
        profile_id="taskcontroller.engineering",
        version="v1",
        sources=(standards_source,),
    )
    resolved = StandardsResolver(standards_reader).resolve(profile)

    task_source = _source(_COMMIT_TASK, "src/task.py", task_content)
    evidence = _evidence("github://evidence/406", "exact evidence")
    pack = ContextPackBuilder(
        SourceReader({(_COMMIT_TASK, task_source.path): task_content.encode()}),
        EvidenceReader({evidence.ref: b"exact evidence"}),
    ).build(
        source_refs=(task_source,),
        evidence_refs=(evidence,),
        standards=resolved.session_context,
    )
    return resolved, pack, task_source, evidence


def _v1_request() -> ExecutorMailboxRequest:
    envelope = A2AEnvelope(
        run_id="run-406",
        node_id="node-406",
        sender="controller",
        recipient="hermes-cloud",
        seq=4,
        kind="COMMAND",
        inputs=(InputRef("source", "repo://task@sha"),),
        artifact_refs=("artifact://evidence/406",),
        request="Execute the bounded task.",
        state={},
        updated_at="2026-09-11T10:40:00+07:00",
    )
    signal = WakeupSignal(
        run_id="run-406",
        sender="controller",
        recipient="hermes-cloud",
        mailbox_ref="github://owner-repo/issues/406#executor",
        seq=4,
        updated_at="2026-09-11T10:40:01+07:00",
    )
    return ExecutorMailboxRequest(signal=signal, envelope=envelope)


def _v2_request(standards: Any, source: StandardsSourceRef, evidence: EvidenceRef) -> Any:
    values: dict[str, Any] = {
        "message_id": "message-406",
        "run_id": "run-406-v2",
        "node_id": "node-406-v2",
        "seq": 0,
        "correlation_id": "correlation-406",
        "contract_id": "contract-406",
        "plan_version": "plan-406",
        "contract_digest": "sha256:" + "1" * 64,
        "boundary_digest": "sha256:" + "2" * 64,
        "source_digest": "sha256:" + "3" * 64,
        "source_manifest_ref": "source-manifest-406",
        "objective": "Bind one bootstrap receipt to exact context.",
        "scope": {
            "allowed_actions": ["read_repo"],
            "denied_actions": ["merge", "deploy"],
            "writable_targets": ["src"],
            "source_roots": ["src"],
            "max_children": 0,
            "max_parallel": 1,
            "max_depth": 0,
        },
        "authority_constraints": {
            "denied_actions": ["merge", "deploy"],
            "writable_targets": ["src"],
        },
        "acceptance_criteria": ("The receipt is exact.",),
        "source_refs": ({**source.to_dict(), "repository": "owner/repo"},),
        "evidence_refs": (evidence.ref,),
        "standards_profile": {
            "profile_id": standards.profile.profile_id,
            "version": standards.profile.version,
            "digest": standards.profile.digest,
        },
        "standards_profile_ref": "taskcontroller.engineering/v1",
        "recipient_capability": "taskcontroller.executor",
        "agent_instance": "hermes-cloud",
        "attempt_id": "attempt-406-v2",
        "attempt_number": 1,
        "lease_generation": 9,
        "fencing_token": "fence-406-v2",
        "lease_expires_at": "2026-09-11T11:00:00+07:00",
        "idempotency_key": "idem-406",
    }
    return compile_bounded_mailbox_request(BoundedMailboxRequest(**values))


def test_v1_bootstrap_emits_auditable_receipt_without_changing_compatibility() -> None:
    resolved, pack, _, _ = _context_pack()
    loaded = _v1_request()
    receipt = loaded.bootstrap_receipt(
        resolved.session_context,
        pack,
        active_attempt=ActiveAttemptFence(
            attempt_id="attempt-406",
            lease_generation=3,
            fencing_token="fence-406",
        ),
        receipt_id="receipt-406-bootstrapped",
        recorded_at="2026-09-11T10:41:00+07:00",
    )

    payload = receipt.to_dict()
    assert payload["protocol"] == "dw.taskcontroller.bootstrap-receipt/v1"
    assert payload["event_type"] == BOOTSTRAP_BOOTSTRAPPED
    assert payload["run_id"] == "run-406"
    assert payload["node_id"] == "node-406"
    assert payload["request_digest"].startswith("sha256:")
    assert payload["standards_digest"] == resolved.receipt.digest
    assert payload["source_pack_digest"] == pack.source_pack_digest
    assert payload["active_attempt"] == {
        "attempt_id": "attempt-406",
        "lease_generation": 3,
        "fencing_token": "fence-406",
    }
    assert loaded.to_dict()["status"] == "BOOTSTRAPPED"


def test_started_and_bootstrapped_events_share_the_same_bound_context() -> None:
    resolved, pack, _, _ = _context_pack()
    loaded = _v1_request()
    active = ActiveAttemptFence("attempt-406", 3, "fence-406")

    started = loaded.bootstrap_receipt(
        resolved,
        pack,
        active_attempt=active,
        event_type=BOOTSTRAP_STARTED,
        receipt_id="receipt-406-started",
        recorded_at="2026-09-11T10:41:00+07:00",
    )
    bootstrapped = loaded.bootstrap_receipt(
        resolved,
        pack,
        active_attempt=active,
        event_type=BOOTSTRAP_BOOTSTRAPPED,
        receipt_id="receipt-406-bootstrapped",
        recorded_at="2026-09-11T10:41:01+07:00",
    )

    assert started.event_type == BOOTSTRAP_STARTED
    assert bootstrapped.event_type == BOOTSTRAP_BOOTSTRAPPED
    for field in ("run_id", "node_id", "request_digest", "standards_digest", "source_pack_digest", "active_attempt"):
        assert getattr(started, field) == getattr(bootstrapped, field)


def test_v2_receipt_derives_active_attempt_and_binds_context_digests() -> None:
    resolved, pack, task_source, evidence = _context_pack()
    request = _v2_request(resolved, task_source, evidence)

    receipt = BootstrapReceipt.from_context(
        request=request,
        standards=resolved,
        context_pack=pack,
        receipt_id="receipt-406-v2",
        recorded_at="2026-09-11T10:42:00+07:00",
    )

    assert receipt.request_digest == request.digest()
    assert receipt.active_attempt == ActiveAttemptFence("attempt-406-v2", 9, "fence-406-v2")
    assert receipt.standards_digest == resolved.receipt.digest
    assert receipt.source_pack_digest == pack.source_pack_digest


def test_v2_receipt_rejects_standards_drift_and_records_source_pack_drift() -> None:
    resolved, pack, task_source, evidence = _context_pack()
    request = _v2_request(resolved, task_source, evidence)
    other_resolved, _, _, _ = _context_pack(standards_content="other rules")

    with pytest.raises(BootstrapReceiptError, match="standards"):
        BootstrapReceipt.from_context(
            request=request,
            standards=other_resolved,
            context_pack=pack,
            receipt_id="receipt-406-drift-standards",
            recorded_at="2026-09-11T10:42:00+07:00",
        )

    altered_resolved, altered, altered_source, altered_evidence = _context_pack(
        task_content="altered task source"
    )
    altered_receipt = BootstrapReceipt.from_context(
        request=_v2_request(altered_resolved, altered_source, altered_evidence),
        standards=altered_resolved,
        context_pack=altered,
        receipt_id="receipt-406-altered-context",
        recorded_at="2026-09-11T10:42:00+07:00",
    )
    assert altered_receipt.source_pack_digest == altered.source_pack_digest
    assert altered_receipt.source_pack_digest != pack.source_pack_digest


def test_v1_receipt_requires_explicit_active_fence_and_rejects_invalid_digest() -> None:
    resolved, pack, _, _ = _context_pack()
    loaded = _v1_request()

    with pytest.raises(BootstrapReceiptError, match="active attempt"):
        loaded.bootstrap_receipt(
            resolved,
            pack,
            receipt_id="receipt-406-no-fence",
            recorded_at="2026-09-11T10:43:00+07:00",
        )

    with pytest.raises(BootstrapReceiptError, match="digest"):
        BootstrapReceipt(
            receipt_id="receipt-406-invalid",
            event_type=BOOTSTRAP_BOOTSTRAPPED,
            run_id="run-406",
            node_id="node-406",
            request_digest="not-a-digest",
            standards_digest=resolved.receipt.digest,
            source_pack_digest=pack.source_pack_digest,
            active_attempt=ActiveAttemptFence("attempt-406", 3, "fence-406"),
            recorded_at="2026-09-11T10:43:00+07:00",
        )


def test_receipt_serialization_is_deterministic_and_defensive() -> None:
    resolved, pack, _, _ = _context_pack()
    loaded = _v1_request()
    active = ActiveAttemptFence("attempt-406", 3, "fence-406")
    first = loaded.bootstrap_receipt(
        resolved,
        pack,
        active_attempt=active,
        receipt_id="receipt-406-deterministic",
        recorded_at="2026-09-11T10:44:00+07:00",
    )
    second = loaded.bootstrap_receipt(
        resolved,
        pack,
        active_attempt=active,
        receipt_id="receipt-406-deterministic",
        recorded_at="2026-09-11T10:44:00+07:00",
    )

    assert first.to_dict() == second.to_dict()
    assert first.canonical_bytes() == second.canonical_bytes()
    mutated = first.to_dict()
    mutated["active_attempt"]["attempt_id"] = "attacker"
    assert first.active_attempt.attempt_id == "attempt-406"


def test_receipt_rejects_wrong_request_type() -> None:
    resolved, pack, _, _ = _context_pack()

    with pytest.raises((BootstrapReceiptError, TaskControllerValidationError)):
        BootstrapReceipt.from_context(
            request={"protocol": "unknown"},
            standards=resolved,
            context_pack=pack,
            active_attempt=ActiveAttemptFence("attempt-406", 3, "fence-406"),
            receipt_id="receipt-406-wrong-request",
            recorded_at="2026-09-11T10:45:00+07:00",
        )
