"""TC-MBX-801: attempt/WorkLease binding and evidence-only unfenced results."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from taskcontroller.controlplane.lease_binding import (
    LeaseBindingError,
    LeaseFenceDisposition,
    bind_attempt_to_work_lease,
    evaluate_result_fence,
)
from taskcontroller.controlplane.result_resume import (
    POLL_NO_NEW_RESULT,
    POLL_RESULT_AVAILABLE,
    poll_controller_terminal_result,
)
from taskcontroller.domain.enums import LeaseStatus
from taskcontroller.domain.ids import ProviderRef
from taskcontroller.domain.models import WorkLease
from taskcontroller.interaction.mailbox_repository import (
    InMemoryMailboxRepository,
    MailboxActorCursor,
)
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope, canonical_digest
from taskcontroller.interaction.state_advancement import (
    StateAdvancingDisposition,
    validate_state_advancing_write,
)
from taskcontroller.execution.terminal_result import build_terminal_parent_result


_FIXTURE = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
_MAILBOX = "github://owner/repo/issues/801#controller"
_NOW = "2026-09-10T12:00:00+07:00"
_EXPIRES = "2026-09-11T00:30:00+07:00"
_EXPIRED = "2026-09-09T00:30:00+07:00"
_FENCE = "fence-1"


def _attempt(
    *,
    attempt_id: str = "attempt-1",
    fencing_token: str = _FENCE,
    agent_instance: str = "hermes-mac",
    lease_expires_at: str = _EXPIRES,
) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "attempt_number": 1,
        "lease_generation": 1,
        "fencing_token": fencing_token,
        "agent_instance": agent_instance,
        "lease_expires_at": lease_expires_at,
    }


def _lease(
    *,
    status: str = LeaseStatus.ACTIVE.value,
    attempt_id: str = "attempt-1",
    fencing_token: str = _FENCE,
    holder: str = "hermes-mac",
    expires_at: str = _EXPIRES,
) -> WorkLease:
    return WorkLease(
        lease_id="lease-801",
        run_id="run-1",
        node_id="node-1",
        execution_id="exec-1",
        attempt_id=attempt_id,
        holder=ProviderRef(holder),
        fencing_token=fencing_token,
        granted_at="2026-09-10T00:00:00+07:00",
        expires_at=expires_at,
        resource_ref="resource://lease-801",
        status=status,
    )


def _request() -> V2MailboxEnvelope:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]["execution_request"]
    payload = copy.deepcopy(payload)
    payload["message_id"] = "request-801"
    payload["idempotency_key"] = "request-idem-801"
    payload["digest"] = canonical_digest(payload)
    return V2MailboxEnvelope.from_dict(payload)


def _normalized() -> dict[str, Any]:
    return {
        "protocol": "dw.taskcontroller.parent-synthesis/v1",
        "proposed_verdict": "PASS",
        "final_verdict": "PASS",
        "verdict": "PASS",
        "status": "PASS",
        "findings": [],
        "child_refs": [
            {
                "child_id": "child-801",
                "status": "SUCCEEDED",
                "result_digest": "sha256:" + "a" * 64,
                "normalization_digest": "sha256:" + "a" * 64,
                "raw_output_digest": "sha256:" + "b" * 64,
                "child_contract_digest": "sha256:" + "c" * 64,
                "source_digest": "sha256:" + "4" * 64,
                "lens": "implementation",
                "reviewer": "reviewer-801",
            }
        ],
        "child_result_digests": ["sha256:" + "a" * 64],
        "residual_risks": [],
        "unresolved_questions": [],
        "conflicts": [],
        "controller_decision": {
            "decision_id": "decision-801",
            "run_ref": "run-1",
            "decision_type": "COMPLETE",
            "rationale": "The result is bound to the active lease evidence.",
            "evidence_refs": ["artifact://evidence-801"],
        },
    }


def _terminal() -> Any:
    return build_terminal_parent_result(
        _request(),
        _normalized(),
        message_id="terminal-801",
        seq=1,
        producer_namespace="hermes-executor",
        producer_actor_id="hermes-mac",
        recipient={"capability": "taskcontroller.controller", "agent_instance": "controller"},
        idempotency_key="terminal-idem-801",
    )


def _cursor() -> MailboxActorCursor:
    return MailboxActorCursor.initial(
        _MAILBOX,
        run_id="run-1",
        node_id="node-1",
        actor_namespace="hermes-executor",
    )


def _current_identity(envelope: V2MailboxEnvelope) -> dict[str, Any]:
    identity = envelope.execution_identity
    return {
        "run_id": identity["run_id"],
        "node_id": identity["node_id"],
        "plan_version": identity["plan_version"],
        "attempt_id": identity["attempt_id"],
        "lease_generation": identity["lease_generation"],
        "contract_digest": identity["contract_digest"],
    }


def test_bind_attempt_to_work_lease_preserves_holder_fence_expiry_and_refs() -> None:
    binding = bind_attempt_to_work_lease(_attempt(), _lease())

    assert binding.run_id == "run-1"
    assert binding.node_id == "node-1"
    assert binding.execution_id == "exec-1"
    assert binding.attempt_id == "attempt-1"
    assert binding.lease_id == "lease-801"
    assert binding.holder.provider_id == "hermes-mac"
    assert binding.fencing_token == _FENCE
    assert binding.expires_at == _EXPIRES
    assert binding.resource_ref == "resource://lease-801"
    assert binding.to_dict()["lease_id"] == "lease-801"
    assert binding.to_dict()["holder"] == {"provider_id": "hermes-mac"}


@pytest.mark.parametrize(
    ("field", "lease"),
    (
        ("attempt_id", replace(_lease(), attempt_id="attempt-old")),
        ("fencing_token", replace(_lease(), fencing_token="fence-old")),
        ("holder", replace(_lease(), holder=ProviderRef("hermes-other"))),
        ("lease_expires_at", replace(_lease(), expires_at="2026-09-11T01:30:00+07:00")),
    ),
)
def test_binding_rejects_attempt_lease_identity_mismatch(
    field: str,
    lease: WorkLease,
) -> None:
    with pytest.raises(LeaseBindingError) as caught:
        bind_attempt_to_work_lease(_attempt(), lease)

    assert caught.value.code == "ATTEMPT_LEASE_MISMATCH"
    assert field in caught.value.failed_checks


def test_matching_active_fence_is_accepted_without_mutation() -> None:
    terminal = _terminal()
    lease = _lease()
    before_terminal = terminal.to_dict()
    before_lease = lease.to_dict()

    decision = evaluate_result_fence(terminal.envelope, lease, now=_NOW)

    assert decision.disposition == LeaseFenceDisposition.ACCEPTED.value
    assert decision.advances_state is True
    assert decision.evidence_only is False
    assert decision.failed_checks == ()
    assert decision.binding is not None
    assert terminal.to_dict() == before_terminal
    assert lease.to_dict() == before_lease


def test_missing_active_fence_is_stale_historical_evidence() -> None:
    decision = evaluate_result_fence(_terminal().envelope, None, now=_NOW)

    assert decision.disposition == LeaseFenceDisposition.STALE_RESULT.value
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks == ("active_lease",)


@pytest.mark.parametrize(
    "lease",
    (
        replace(_lease(), status=LeaseStatus.RELEASED.value),
        replace(_lease(), status=LeaseStatus.REVOKED.value),
        replace(_lease(), status=LeaseStatus.EXPIRED.value),
        replace(_lease(), expires_at=_EXPIRED),
        replace(_lease(), fencing_token="fence-old"),
        replace(_lease(), holder=ProviderRef("hermes-other")),
    ),
)
def test_inactive_expired_or_mismatched_fence_is_evidence_only(lease: WorkLease) -> None:
    decision = evaluate_result_fence(_terminal().envelope, lease, now=_NOW)

    assert decision.disposition == LeaseFenceDisposition.STALE_RESULT.value
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks


def test_state_advancement_requires_explicit_active_fence_for_new_path() -> None:
    terminal = _terminal()
    current = _current_identity(terminal.envelope)

    decision = validate_state_advancing_write(
        terminal.envelope,
        current_identity=current,
        expected_source_digest=terminal.envelope.execution_identity["source_digest"],
        actor_cursor=-1,
        write_kind="terminal_result",
        active_lease=None,
        lease_now=_NOW,
    )

    assert decision.disposition == StateAdvancingDisposition.STALE_RESULT.value
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks == ("active_lease",)


def test_state_advancement_accepts_matching_active_lease() -> None:
    terminal = _terminal()
    decision = validate_state_advancing_write(
        terminal.envelope,
        current_identity=_current_identity(terminal.envelope),
        expected_source_digest=terminal.envelope.execution_identity["source_digest"],
        actor_cursor=-1,
        write_kind="terminal_result",
        active_lease=_lease(),
        lease_now=_NOW,
    )

    assert decision.disposition == StateAdvancingDisposition.ACCEPTED.value
    assert decision.advances_state is True
    assert decision.evidence_only is False


def test_controller_poll_keeps_unfenced_terminal_as_historical_evidence() -> None:
    repository = InMemoryMailboxRepository()
    terminal = _terminal()
    repository.write(_MAILBOX, -1, terminal.envelope)

    outcome = poll_controller_terminal_result(
        repository,
        _cursor(),
        correlation_id=terminal.envelope.to_dict()["correlation_id"],
        expected_identity=terminal.envelope.execution_identity,
        expected_source_digest=terminal.envelope.execution_identity["source_digest"],
        active_lease=None,
        lease_now=_NOW,
    )

    assert outcome.status == POLL_NO_NEW_RESULT
    assert outcome.terminal_result is None
    assert outcome.ignored_reasons == ("ACTIVE_FENCE_MISSING",)
    assert outcome.cursor.last_event_seq == 0


def test_controller_poll_resumes_only_with_matching_active_fence() -> None:
    repository = InMemoryMailboxRepository()
    terminal = _terminal()
    repository.write(_MAILBOX, -1, terminal.envelope)

    outcome = poll_controller_terminal_result(
        repository,
        _cursor(),
        correlation_id=terminal.envelope.to_dict()["correlation_id"],
        expected_identity=terminal.envelope.execution_identity,
        expected_source_digest=terminal.envelope.execution_identity["source_digest"],
        active_lease=_lease(),
        lease_now=_NOW,
    )

    assert outcome.status == POLL_RESULT_AVAILABLE
    assert outcome.terminal_result == terminal
    assert outcome.ignored_event_ids == ()


def test_controller_poll_rejects_expired_active_fence_as_evidence_only() -> None:
    repository = InMemoryMailboxRepository()
    terminal = _terminal()
    repository.write(_MAILBOX, -1, terminal.envelope)

    outcome = poll_controller_terminal_result(
        repository,
        _cursor(),
        correlation_id=terminal.envelope.to_dict()["correlation_id"],
        expected_identity=terminal.envelope.execution_identity,
        expected_source_digest=terminal.envelope.execution_identity["source_digest"],
        active_lease=_lease(),
        lease_now="2026-09-11T01:00:00+07:00",
    )

    assert outcome.status == POLL_NO_NEW_RESULT
    assert outcome.terminal_result is None
    assert outcome.ignored_reasons == ("ACTIVE_FENCE_EXPIRED",)
