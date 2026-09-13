"""TC-MBX-802: MIXING lease expiry and takeover generation hardening."""

from __future__ import annotations

from dataclasses import replace

import pytest

from test_mixer_input_manifest import _ledger_and_outcomes
from test_takeover import (
    _NOW,
    _lease,
    _registry,
    _replacement_lease,
    _replacement_request,
    _request,
    _seed,
    _stored,
)
from taskcontroller.domain.enums import LeaseStatus, NodeStatus
from taskcontroller.controlplane.takeover import (
    TakeoverValidationError,
    takeover_bounded_mailbox_request,
)
from taskcontroller.execution.mixer_input_manifest import MixerInputManifest
from taskcontroller.kernel.errors import TransitionRejected
from taskcontroller.kernel.transitions import validate_node_transition


def test_mixing_is_an_expirable_node_state_and_takeover_recovery_is_legal() -> None:
    assert NodeStatus.MIXING.value == "MIXING"
    validate_node_transition(NodeStatus.REVIEWING.value, NodeStatus.MIXING.value)
    validate_node_transition(NodeStatus.MIXING.value, NodeStatus.LEASE_EXPIRED.value)
    validate_node_transition(NodeStatus.LEASE_EXPIRED.value, NodeStatus.RETRY_READY.value)

    with pytest.raises(TransitionRejected):
        validate_node_transition(NodeStatus.MIXING.value, NodeStatus.RUNNING.value)


def test_current_lease_expiry_during_mixer_marks_node_lease_expired() -> None:
    old_lease = _lease()
    manager, store, current = _seed(old_lease)
    node = replace(current.state.nodes["node-804"], status=NodeStatus.MIXING.value)
    mixed_state = replace(
        current,
        state=replace(current.state, nodes={"node-804": node}),
        version=current.version + 1,
    )
    store.put_run(mixed_state, current.version)
    current = _stored(store)

    expired = manager.expire(
        old_lease.lease_id,
        current.version,
        current,
        now=_NOW,
    )

    assert expired.state.nodes["node-804"].status == NodeStatus.LEASE_EXPIRED.value
    assert expired.meta.leases.leases[old_lease.lease_id].status == LeaseStatus.EXPIRED.value
    assert expired.meta.attempt_registry[old_lease.attempt_id].current_lease_id is None


def test_takeover_binds_replacement_work_lease_generation_to_request() -> None:
    old_request = _request()
    old_lease = _lease()
    replacement_request = _replacement_request()
    replacement_lease = _replacement_lease()
    manager, store, current = _seed(old_lease)
    mixing_node = replace(current.state.nodes["node-804"], status=NodeStatus.MIXING.value)
    store.put_run(
        replace(
            current,
            state=replace(current.state, nodes={"node-804": mixing_node}),
            version=current.version + 1,
        ),
        current.version,
    )
    current = _stored(store)

    result = takeover_bounded_mailbox_request(
        _registry(),
        old_request,
        old_lease,
        replacement_request,
        replacement_lease,
        lease_manager=manager,
        current_state=current,
        expected_version=current.version,
        retirement="REVOKE",
        now=_NOW,
        receipt_id="receipt-802-takeover",
        accepted_at=_NOW,
    )

    assert result.replacement_lease.lease_generation == replacement_request.lease_generation
    stored = _stored(store)
    assert stored.meta.attempt_registry[old_lease.attempt_id].lease_generation == replacement_request.lease_generation
    assert stored.meta.leases.leases[replacement_lease.lease_id].lease_generation == replacement_request.lease_generation
    assert stored.state.nodes["node-804"].status == NodeStatus.MIXING.value
    assert stored.state.nodes["node-804"].lease_ref == replacement_lease.lease_id


def test_takeover_rejects_conflicting_explicit_replacement_generation() -> None:
    old_lease = _lease()
    replacement_request = _replacement_request()
    replacement_lease = replace(_replacement_lease(), lease_generation=4)
    manager, _store, current = _seed(old_lease)

    with pytest.raises(TakeoverValidationError) as caught:
        takeover_bounded_mailbox_request(
            _registry(),
            _request(),
            old_lease,
            replacement_request,
            replacement_lease,
            lease_manager=manager,
            current_state=current,
            expected_version=current.version,
            retirement="REVOKE",
            now=_NOW,
            receipt_id="receipt-802-generation-mismatch",
            accepted_at=_NOW,
        )

    assert caught.value.code == "TAKEOVER_GENERATION_MISMATCH"
    assert caught.value.failed_checks == ("lease_generation",)


def test_prior_generation_mixer_result_is_evidence_only_after_takeover() -> None:
    ledger, outcomes, _ = _ledger_and_outcomes()
    current = MixerInputManifest.from_receipt_ledger(
        ledger,
        outcomes,
        parent_attempt_id="attempt-603",
        lease_generation=2,
        fencing_token="fence-802-current",
    )
    prior = replace(
        current,
        lease_generation=1,
        fencing_token="fence-802-old",
    )

    decision = prior.generation_decision(current.generation_identity())

    assert decision.disposition == "STALE_RESULT"
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks == ("lease_generation", "fencing_token")
