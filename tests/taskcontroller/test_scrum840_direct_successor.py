"""SCRUM-840 regression: bound successor of a recovered WAIT_CONTROLLER run."""
from dataclasses import replace
import pytest
from taskcontroller.domain.ids import ProviderRef
from taskcontroller.domain.models import WorkLease
from taskcontroller.interaction.continuation import ControllerContinuation
from taskcontroller.runtime.high_integrity_session import (
    HighIntegrityMaterializationError, qualify_wait_controller_successor,
)

RUN = "scrum781-q0-fresh-20261010-r1"
OLD_SHA = "4016eab3fd8d116af92114a76197a63459b7355d"
NEW_SHA = "80a3995ce374d678eaeaf223d25959aba4ea8d35"

def checkpoint():
    return ControllerContinuation(
        run_id=RUN, controller_epoch=3, phase="WAIT_CONTROLLER", status="ACTIVE",
        next_action="RESOLVE_EXECUTION_AUTHORITY",
        controller_mailbox_ref=f"github://nhatnguyenquang1838-coder/gwc/issues/595#{RUN}-controller-v2",
        controller_seq=3, executor_actor="q0-actions-engineering",
        executor_mailbox_ref=f"github://nhatnguyenquang1838-coder/gwc/issues/595#{RUN}-executor-v2",
        expected_executor_seq=3, last_seen_executor_seq=2,
        wakeup_binding="github-actions-q0-engineering-consumer", exact_head_sha=OLD_SHA,
        updated_at="2026-10-10T14:24:51Z",
    )

def lease(**update):
    fields = dict(
        lease_id="lease-attempt4", run_id=RUN, node_id="SCRUM-781",
        execution_id="exec-attempt4", attempt_id="scrum781-q0-execute-attempt4",
        holder=ProviderRef("q0-actions-engineering"),
        fencing_token="issuer-fence4", lease_generation=4,
        granted_at="2026-10-11T00:00:00Z",
        expires_at="2026-10-12T00:00:00Z", status="ACTIVE",
    )
    fields.update(update)
    return WorkLease(**fields)

def qualify(**update):
    fields = dict(
        checkpoint=checkpoint(),
        controller_tail_logical_seq=3, executor_tail_logical_seq=2,
        predecessor_attempt=dict(
            attempt_id="scrum781-q0-execute-attempt3",
            fencing_token="old-fence3", lease_generation=3,
            lease_expires_at="2026-10-10T02:11:33Z"),
        active_work_lease=lease(), source_head_sha=NEW_SHA,
        approval_receipt_ref="github://example/approved/current",
        approval_verified=True,
        lease_issuer_receipt_ref="github://example/issuer/current",
        source_replan_receipt_ref="github://example/replan/immutable",
        observed_at="2026-10-11T22:00:00Z",
    )
    fields.update(update)
    return qualify_wait_controller_successor(**fields)

def test_same_run_successor_preserves_progress_and_increments_sequence():
    proposed = qualify()
    assert proposed.run_id == RUN
    assert proposed.executor_actor == "q0-actions-engineering"
    assert proposed.controller_epoch == 4
    assert proposed.controller_seq == 4
    assert proposed.phase == "WAIT_EXECUTOR"
    assert proposed.next_action == "AWAIT_EXECUTOR_EVENT"
    assert proposed.last_seen_executor_seq == 2
    assert proposed.expected_executor_seq == 3
    assert proposed.exact_head_sha == NEW_SHA

@pytest.mark.parametrize(("updates", "code"), [
    ({"approval_verified": False}, "SUCCESSOR_APPROVAL_MISSING"),
    ({"lease_issuer_receipt_ref": ""}, "SUCCESSOR_ISSUER_MISSING"),
    ({"controller_tail_logical_seq": 2}, "SUCCESSOR_CONTROLLER_CURSOR_DRIFT"),
    ({"executor_tail_logical_seq": 3}, "SUCCESSOR_EXECUTOR_CURSOR_DRIFT"),
    ({"source_replan_receipt_ref": None}, "SUCCESSOR_REPLAN_MISSING"),
    ({"active_work_lease": lease(lease_generation=3)}, "SUCCESSOR_LEASE_STALE"),
    ({"active_work_lease": lease(holder=ProviderRef("untrusted"))}, "SUCCESSOR_LEASE_STALE"),
    ({"active_work_lease": lease(expires_at="2026-10-10T02:11:33Z")}, "SUCCESSOR_LEASE_EXPIRED"),
    ({"active_work_lease": lease(attempt_id="scrum781-q0-execute-attempt3")}, "SUCCESSOR_LEASE_STALE"),
    ({"active_work_lease": lease(fencing_token="old-fence3")}, "SUCCESSOR_LEASE_STALE"),
    ({"checkpoint": replace(checkpoint(), phase="WAIT_EXECUTOR", next_action="AWAIT_EXECUTOR_EVENT")}, "SUCCESSOR_STATE_INVALID"),
    ({"predecessor_attempt": {"attempt_id": "a", "fencing_token": "b", "lease_generation": True, "lease_expires_at": "2026-10-10T02:11:33Z"}}, "SUCCESSOR_PREDECESSOR_INVALID"),
    ({"source_head_sha": "invalid"}, "SUCCESSOR_SOURCE_INVALID"),
    ({"active_work_lease": lease(run_id="not-the-current-run")}, "SUCCESSOR_LEASE_STALE"),
])
def test_fail_closed_without_proper_binding(updates, code):
    with pytest.raises(HighIntegrityMaterializationError, match=code):
        qualify(**updates)

def test_already_current_sha_does_not_require_replan_receipt():
    proposed = qualify(source_head_sha=OLD_SHA, source_replan_receipt_ref=None)
    assert proposed.exact_head_sha == OLD_SHA
