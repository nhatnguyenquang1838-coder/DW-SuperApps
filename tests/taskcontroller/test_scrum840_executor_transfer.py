"""SCRUM-840 same-run executor transfer uses existing v2 records and lease types."""
from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from taskcontroller.domain.ids import ProviderRef
from taskcontroller.domain.models import WorkLease
from taskcontroller.interaction.continuation import ControllerContinuation
from taskcontroller.interaction.mailbox_repository import InMemoryMailboxRepository
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.runtime.high_integrity_session import (
    HighIntegrityMaterializationError,
)

FIXTURE_PATH = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
RUN = "test-scrum781-transfer-run"
OLD_HEAD = "a" * 40
BRANCH = "test/SCRUM-781"
WORKTREE = "worktrees/gwc/SCRUM-781-transfer-test"
CONTROLLER_REF = "github://example/gwc/issues/1#test-scrum781-transfer-controller-v2"
EXECUTOR_REF = "github://example/gwc/issues/1#test-scrum781-transfer-executor-v2"


def _iso(offset=timedelta(0)):
    return (datetime.now(UTC) + offset).isoformat().replace("+00:00", "Z")


def _checkpoint():
    return ControllerContinuation(
        run_id=RUN,
        controller_epoch=3,
        phase="WAIT_CONTROLLER",
        status="ACTIVE",
        next_action="RESOLVE_EXECUTION_AUTHORITY",
        controller_mailbox_ref=CONTROLLER_REF,
        controller_seq=3,
        executor_actor="q0-actions-engineering",
        executor_mailbox_ref=EXECUTOR_REF,
        expected_executor_seq=3,
        last_seen_executor_seq=2,
        wakeup_binding="github-actions-q0-engineering-consumer",
        exact_head_sha=OLD_HEAD,
        updated_at="2026-10-10T14:24:51Z",
    )


def _successor(**overrides):
    values = {
        "run_id": RUN,
        "controller_epoch": 4,
        "phase": "WAIT_EXECUTOR",
        "status": "ACTIVE",
        "next_action": "AWAIT_EXECUTOR_EVENT",
        "controller_mailbox_ref": CONTROLLER_REF,
        "controller_seq": 4,
        "executor_actor": "hermes-desktop",
        "executor_mailbox_ref": EXECUTOR_REF,
        "expected_executor_seq": 3,
        "last_seen_executor_seq": 2,
        "wakeup_binding": "hermes-desktop-local-ipc",
        "exact_head_sha": OLD_HEAD,
        "updated_at": "2026-10-12T00:00:00Z",
    }
    values.update(overrides)
    return ControllerContinuation(**values)


def _lease(**overrides):
    values = {
        "lease_id": "lease-attempt4",
        "run_id": RUN,
        "node_id": "node-1",
        "execution_id": "exec-attempt4",
        "attempt_id": "test-run-attempt-4",
        "holder": ProviderRef("hermes-desktop"),
        "fencing_token": "test-fence-4",
        "lease_generation": 4,
        "granted_at": _iso(timedelta(minutes=-1)),
        "expires_at": _iso(timedelta(hours=1)),
        "status": "ACTIVE",
    }
    values.update(overrides)
    return WorkLease(**values)


def _controller_event(*, agent_instance="hermes-desktop-instance-1", run_id=RUN, seq=4):
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = copy.deepcopy(fixture["cases"]["execution_request"])
    payload.update(
        run_id=run_id,
        node_id="node-1",
        seq=seq,
        message_id=f"transfer-message-{seq}",
        idempotency_key=f"transfer-idem-{seq}",
        producer={"namespace": "controller", "actor_id": "controller-1", "role": "controller"},
        recipient={"agent_instance": agent_instance, "capability": "taskcontroller.executor"},
    )
    attempt_id = "test-run-attempt-4"
    payload["attempt"].update(
        agent_instance=agent_instance,
        attempt_id=attempt_id,
        fencing_token="test-fence-4",
        lease_generation=4,
    )
    payload["execution_identity"].update(
        run_id=run_id,
        node_id="node-1",
        attempt_id=attempt_id,
        fencing_token="test-fence-4",
        lease_generation=4,
    )
    payload["provenance"]["agent_instance"] = "controller-1"
    payload["digest"] = canonical_digest(payload)
    envelope = V2MailboxEnvelope.from_dict(payload)
    repository = InMemoryMailboxRepository()
    repository.write(CONTROLLER_REF, -1, envelope)
    return repository.read(CONTROLLER_REF).events[0]


def _qualify(**overrides):
    from taskcontroller.runtime.high_integrity_session import (
        qualify_same_run_executor_transfer,
    )

    values = {
        "predecessor_checkpoint": _checkpoint(),
        "successor_checkpoint": _successor(),
        "controller_event": _controller_event(),
        "predecessor_attempt": {
            "attempt_id": "test-run-attempt-3",
            "fencing_token": "test-fence-3",
            "lease_generation": 3,
            "lease_expires_at": _iso(timedelta(minutes=-1)),
        },
        "active_work_lease": _lease(),
        "expected_agent_instance": "hermes-desktop-instance-1",
        "expected_executor_actor": "hermes-desktop",
        "expected_wakeup_binding": "hermes-desktop-local-ipc",
        "expected_branch": BRANCH,
        "observed_branch": BRANCH,
        "expected_worktree": WORKTREE,
        "observed_worktree": WORKTREE,
        "observed_head_sha": OLD_HEAD,
        "approval_verified": True,
        "approval_receipt_ref": "github://example/gwc/issues/1#test-approval",
        "lease_issuer_receipt_ref": "github://example/gwc/issues/1#test-issuer-receipt",
        "source_replan_receipt_ref": None,
        "observed_at": _iso(),
    }
    values.update(overrides)
    return qualify_same_run_executor_transfer(**values)


def test_transfer_is_qualified_from_existing_continuation_event_and_fresh_lease():
    qualified = _qualify()

    assert qualified == _successor()
    assert qualified.run_id == RUN
    assert qualified.executor_actor == "hermes-desktop"
    assert qualified.exact_head_sha == OLD_HEAD


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"successor_checkpoint": _successor(run_id="other-run")}, "TRANSFER_RUN_MISMATCH"),
        ({"successor_checkpoint": _successor(executor_actor="q0-actions-engineering")}, "TRANSFER_ACTOR_MISMATCH"),
        ({"successor_checkpoint": _successor(wakeup_binding="github-actions-q0-engineering-consumer")}, "TRANSFER_WAKEUP_MISMATCH"),
        ({"controller_event": _controller_event(agent_instance="wrong-instance")}, "TRANSFER_RECIPIENT_MISMATCH"),
        ({"controller_event": _controller_event(run_id="other-run")}, "TRANSFER_EVENT_BINDING_MISMATCH"),
        ({"active_work_lease": _lease(lease_generation=3)}, "TRANSFER_LEASE_STALE"),
        ({"active_work_lease": _lease(holder=ProviderRef("q0-actions-engineering"))}, "TRANSFER_LEASE_STALE"),
        ({"active_work_lease": _lease(attempt_id="other-attempt")}, "TRANSFER_LEASE_STALE"),
        ({"active_work_lease": _lease(fencing_token="other-fence")}, "TRANSFER_LEASE_STALE"),
        ({"active_work_lease": _lease(lease_generation=5)}, "TRANSFER_LEASE_STALE"),
        ({"active_work_lease": _lease(expires_at=_iso(timedelta(seconds=-1)))}, "TRANSFER_LEASE_EXPIRED"),
        ({"approval_verified": False}, "TRANSFER_APPROVAL_MISSING"),
        ({"lease_issuer_receipt_ref": ""}, "TRANSFER_ISSUER_MISSING"),
        ({"observed_branch": "different-branch"}, "TRANSFER_BRANCH_MISMATCH"),
        ({"observed_worktree": "worktrees/gwc/OTHER"}, "TRANSFER_WORKTREE_MISMATCH"),
        ({"observed_head_sha": "f" * 40}, "TRANSFER_HEAD_MISMATCH"),
    ],
)
def test_transfer_requires_exact_same_run_actor_event_and_live_lease(overrides, reason):
    with pytest.raises(HighIntegrityMaterializationError, match=reason):
        _qualify(**overrides)


def test_transfer_cannot_reuse_expired_attempt_three_or_infer_missing_receipt():
    with pytest.raises(HighIntegrityMaterializationError, match="TRANSFER_LEASE_STALE"):
        _qualify(active_work_lease=_lease(attempt_id="test-run-attempt-3"))
    with pytest.raises(HighIntegrityMaterializationError, match="TRANSFER_ISSUER_MISSING"):
        _qualify(lease_issuer_receipt_ref=None)
