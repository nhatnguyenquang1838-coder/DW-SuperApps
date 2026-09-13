"""TC-MBX-801 hardening: authoritative generation/fence acceptance.

These tests are intentionally provider-neutral.  They prove that parent, child,
Fanout Manifest and Mixer state-advancing candidates share one current-generation
predicate and that runtime attempt records persist the authoritative generation.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from dataclasses import replace

import pytest

from taskcontroller.controlplane.generation_fence import (
    GenerationFenceError,
    GenerationFenceDisposition,
    evaluate_generation_fence,
)
from taskcontroller.controlplane.lease_binding import evaluate_result_fence
from taskcontroller.interaction.mailbox_v2 import V2MailboxEnvelope
from taskcontroller.interaction.state_advancement import (
    StateAdvancingDisposition,
    validate_state_advancing_write,
)
from taskcontroller.execution.manifest import ManifestParentIdentity
from taskcontroller.execution.mixer_input_manifest import MixerInputManifest
from taskcontroller.execution.fanout import FanoutCoordinator, FanoutCoordinatorError
from taskcontroller.runtime.runtime_state import AttemptRecord, make_attempt_record
from tests.taskcontroller.test_fanout import _children, _completion, _parent
from tests.taskcontroller.test_lease_c2 import _make_lease, _make_state, _make_store
from tests.taskcontroller.test_lease_binding import _lease, _terminal
from tests.taskcontroller.test_mixer_input_manifest import _ledger_and_outcomes


_FIXTURES = Path(__file__).with_name("fixtures") / "v2_contract_fixtures.json"
_CURRENT = {
    "run_id": "run-801",
    "node_id": "node-801",
    "execution_id": "exec-801",
    "attempt_id": "attempt-801-current",
    "lease_generation": 2,
    "fencing_token": "fence-801-current",
}


def _candidate(**changes: Any) -> dict[str, Any]:
    value = dict(_CURRENT)
    value.update(changes)
    return value


def test_current_generation_fence_accepts_exact_parent_child_and_mixer_identity() -> None:
    for write_kind in ("parent", "child", "mixer"):
        decision = evaluate_generation_fence(
            _candidate(write_kind=write_kind),
            _CURRENT,
        )
        assert decision.disposition == GenerationFenceDisposition.ACCEPTED.value
        assert decision.advances_state is True
        assert decision.evidence_only is False
        assert decision.failed_checks == ()


@pytest.mark.parametrize("field", ("lease_generation", "fencing_token", "attempt_id"))
def test_old_or_foreign_parent_child_mixer_write_is_evidence_only(field: str) -> None:
    candidate = _candidate(**{field: 1 if field == "lease_generation" else f"old-{field}"})

    decision = evaluate_generation_fence(candidate, _CURRENT)

    assert decision.disposition == GenerationFenceDisposition.STALE_RESULT.value
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert field in decision.failed_checks


def test_generation_fence_requires_authoritative_generation_and_fence() -> None:
    incomplete = dict(_CURRENT)
    del incomplete["lease_generation"]
    with pytest.raises(GenerationFenceError) as caught:
        evaluate_generation_fence(incomplete, _CURRENT)
    assert caught.value.code == "SCHEMA_INVALID"

    incomplete = dict(_CURRENT)
    del incomplete["fencing_token"]
    with pytest.raises(GenerationFenceError) as caught:
        evaluate_generation_fence(incomplete, _CURRENT)
    assert caught.value.code == "SCHEMA_INVALID"


def test_generation_fence_does_not_mutate_candidate_or_current_identity() -> None:
    candidate = _candidate()
    current = copy.deepcopy(_CURRENT)

    evaluate_generation_fence(candidate, current)

    assert candidate == _CURRENT
    assert current == _CURRENT


def test_attempt_record_persists_monotonic_generation_and_fence() -> None:
    record = make_attempt_record(
        attempt_id="attempt-801-current",
        run_id="run-801",
        node_id="node-801",
        execution_id="exec-801",
        fencing_token="fence-801-current",
        lease_generation=2,
        current_attempt_number=1,
    )

    assert isinstance(record, AttemptRecord)
    payload = record.to_dict()
    assert payload["lease_generation"] == 2
    assert payload["fencing_token"] == "fence-801-current"
    assert AttemptRecord.from_dict(payload).to_dict() == payload


def test_state_advancing_predicate_rejects_current_generation_fence_mismatch() -> None:
    fixture = json.loads(_FIXTURES.read_text(encoding="utf-8"))["cases"]["terminal_result"]
    envelope = V2MailboxEnvelope.from_dict(fixture)
    current = envelope.execution_identity
    current["fencing_token"] = "fence-authoritative-new"

    decision = validate_state_advancing_write(
        envelope,
        current_identity=current,
        expected_source_digest=envelope.execution_identity["source_digest"],
        actor_cursor=-1,
        write_kind="terminal_result",
    )

    assert decision.disposition == StateAdvancingDisposition.STALE_RESULT.value
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert "fencing_token" in decision.failed_checks


def test_generation_fence_rejects_current_generation_for_wrong_execution_scope() -> None:
    decision = evaluate_generation_fence(
        _candidate(execution_id="exec-other"),
        _CURRENT,
    )

    assert decision.disposition == GenerationFenceDisposition.STALE_RESULT.value
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks == ("execution_id",)


def test_fanout_manifest_parent_identity_rejects_old_generation_as_evidence() -> None:
    identity = ManifestParentIdentity(
        run_id="run-801",
        node_id="node-801",
        plan_version="plan-801",
        contract_id="contract-801",
        contract_digest="sha256:" + "1" * 64,
        boundary_digest="sha256:" + "2" * 64,
        source_manifest_ref="manifest-801",
        source_digest="sha256:" + "3" * 64,
        standards_profile_ref="standards-801",
        standards_profile_digest="sha256:" + "4" * 64,
        attempt_id="attempt-801-current",
        lease_generation=2,
        fencing_token="fence-801-current",
    )
    current = dict(_CURRENT)
    current["lease_generation"] = 3

    decision = identity.generation_decision(current)

    assert decision.disposition == GenerationFenceDisposition.STALE_RESULT.value
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks == ("lease_generation",)


def test_mixer_input_manifest_rejects_old_generation_as_evidence() -> None:
    ledger, outcomes, _ = _ledger_and_outcomes()
    manifest = MixerInputManifest.from_receipt_ledger(
        ledger,
        outcomes,
        parent_attempt_id="attempt-603",
        lease_generation=2,
        fencing_token="fence-603-current",
    )
    current = {
        "run_id": "run-603",
        "node_id": "node-603",
        "attempt_id": "attempt-603",
        "lease_generation": 3,
        "fencing_token": "fence-603-new",
    }

    decision = manifest.generation_decision(current)

    assert decision.disposition == GenerationFenceDisposition.STALE_RESULT.value
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert decision.failed_checks == ("lease_generation", "fencing_token")


def test_bound_fanout_requires_generation_and_retains_prior_generation_completion() -> None:
    children = _children()
    with pytest.raises(FanoutCoordinatorError) as missing:
        FanoutCoordinator.from_children(
            children,
            parent=_parent(),
            parent_attempt_id="parent-801",
        )
    assert missing.value.code == "GENERATION_REQUIRED"

    coordinator = FanoutCoordinator.from_children(
        children,
        parent=_parent(),
        parent_attempt_id="parent-801",
        lease_generation=2,
    )
    stale = replace(
        _completion(children[0]),
        parent_attempt_id="parent-801",
        lease_generation=1,
        plan_version=coordinator.plan.plan_version,
        plan_digest=coordinator.plan.plan_digest,
        attempt_id="child-attempt-1",
        source_digest=children[0].source_digest,
        standards_profile_digest=children[0].standards_profile["digest"],
    )
    updated = coordinator.complete(stale)
    assert updated.completed_child_ids == ()
    assert updated.stale_child_ids == ("child-1",)
    assert updated.evidence_completions[0].evidence_only is True


def test_lease_grant_persists_and_advances_parent_generation() -> None:
    from taskcontroller.runtime.errors import LeaseConflictError
    from taskcontroller.runtime.lease import LeaseManager

    store = _make_store()
    initial = _make_state(lease=None)
    store.put_run(initial, -1)
    manager = LeaseManager(store)

    first = manager.grant(_make_lease(), initial.version, initial)
    first_saved = store.get_run("run.1")
    assert first_saved is not None
    assert first_saved.meta.attempt_registry["att.1"].lease_generation == 1
    assert first_saved.meta.leases.leases["lease.1"].lease_generation == 1

    second = manager.grant(_make_lease(lease_id="lease.2"), first.version, first)
    second_saved = store.get_run("run.1")
    assert second_saved is not None
    assert second_saved.meta.attempt_registry["att.1"].lease_generation == 2
    assert second_saved.meta.leases.leases["lease.2"].lease_generation == 2
    with pytest.raises(LeaseConflictError, match="lease_generation must increase"):
        manager.grant(
            replace(_make_lease(lease_id="lease.3"), lease_generation=2),
            second.version,
            second,
        )


def test_parent_terminal_result_against_prior_lease_generation_is_evidence_only() -> None:
    decision = evaluate_result_fence(
        _terminal().envelope,
        replace(_lease(), lease_generation=2),
        now="2026-09-10T12:00:00+07:00",
    )
    assert decision.disposition == "STALE_RESULT"
    assert decision.advances_state is False
    assert decision.evidence_only is True
    assert "lease_generation" in decision.failed_checks
