"""TC-MBX-803 hardening: deterministic reusable-child evidence policy."""

from __future__ import annotations

from typing import Any

import pytest

from taskcontroller.execution.reuse_policy import (
    ChildEvidenceRecord,
    ReuseDisposition,
    ReusePolicy,
    evaluate_child_evidence_reuse,
)


_DIGESTS = {
    "child": "sha256:" + "1" * 64,
    "parent": "sha256:" + "2" * 64,
    "source": "sha256:" + "3" * 64,
    "standards": "sha256:" + "4" * 64,
    "result": "sha256:" + "5" * 64,
}


def _record(**changes: Any) -> ChildEvidenceRecord:
    values: dict[str, Any] = {
        "child_id": "child-803",
        "child_contract_digest": _DIGESTS["child"],
        "parent_contract_id": "contract-803",
        "parent_contract_digest": _DIGESTS["parent"],
        "plan_version": "plan-803",
        "source_digest": _DIGESTS["source"],
        "standards_digest": _DIGESTS["standards"],
        "parent_attempt_id": "attempt-803-parent",
        "lease_generation": 4,
        "status": "SUCCEEDED",
        "result_ref": "github://child/803/result-1",
        "result_digest": _DIGESTS["result"],
        "reuse_policy": ReusePolicy.REUSE_IF_COMPATIBLE,
    }
    values.update(changes)
    return ChildEvidenceRecord(**values)


def _takeover_target(**changes: Any) -> ChildEvidenceRecord:
    values = {
        "lease_generation": 5,
        "status": "PLANNED",
        "result_ref": None,
        "result_digest": None,
    }
    values.update(changes)
    return _record(**values)


def test_compatible_takeover_reuse_is_deterministic_and_preserves_result_ref() -> None:
    prior = _record()
    target = _takeover_target()

    first = evaluate_child_evidence_reuse(prior, target)
    second = evaluate_child_evidence_reuse(prior, target)

    assert first == second
    assert first.disposition is ReuseDisposition.REUSE
    assert first.failed_checks == ()
    assert first.reused_result_ref == prior.result_ref
    assert first.reused_result_digest == prior.result_digest
    assert first.to_dict() == {
        "child_id": "child-803",
        "disposition": "REUSE",
        "failed_checks": [],
        "reused_result_ref": "github://child/803/result-1",
        "reused_result_digest": _DIGESTS["result"],
    }


@pytest.mark.parametrize(
    ("field", "value", "failed_check"),
    (
        ("parent_contract_id", "contract-other", "parent_contract_id"),
        ("parent_contract_digest", "sha256:" + "9" * 64, "parent_contract_digest"),
        ("plan_version", "plan-other", "plan_version"),
        ("child_contract_digest", "sha256:" + "9" * 64, "child_contract_digest"),
        ("source_digest", "sha256:" + "9" * 64, "source_digest"),
        ("standards_digest", "sha256:" + "9" * 64, "standards_digest"),
        ("parent_attempt_id", "attempt-other", "parent_attempt_id"),
        ("lease_generation", 4, "lease_generation"),
        ("reuse_policy", ReusePolicy.RERUN_REQUIRED, "reuse_policy"),
    ),
)
def test_incompatible_takeover_forces_rerun(
    field: str,
    value: Any,
    failed_check: str,
) -> None:
    prior = _record()
    target = _takeover_target(**{field: value})

    decision = evaluate_child_evidence_reuse(prior, target)

    assert decision.disposition is ReuseDisposition.RERUN
    assert failed_check in decision.failed_checks
    assert decision.reused_result_ref is None
    assert decision.reused_result_digest is None


@pytest.mark.parametrize(
    ("status", "result_ref", "result_digest", "failed_check"),
    (
        ("FAILED", _DIGESTS["result"], _DIGESTS["result"], "status"),
        ("SUCCEEDED", None, _DIGESTS["result"], "result_ref"),
        ("SUCCEEDED", "github://child/803/result-1", None, "result_digest"),
    ),
)
def test_non_reusable_terminal_evidence_forces_rerun(
    status: str,
    result_ref: str | None,
    result_digest: str | None,
    failed_check: str,
) -> None:
    prior = _record(status=status, result_ref=result_ref, result_digest=result_digest)

    decision = evaluate_child_evidence_reuse(prior, _takeover_target())

    assert decision.disposition is ReuseDisposition.RERUN
    assert failed_check in decision.failed_checks


def test_reuse_record_round_trip_is_canonical_and_does_not_mutate_inputs() -> None:
    prior = _record()
    target = _takeover_target()
    prior_before = prior.to_dict()
    target_before = target.to_dict()

    decision = evaluate_child_evidence_reuse(prior, target)
    restored = ChildEvidenceRecord.from_dict(prior.to_dict())

    assert restored == prior
    assert decision.disposition is ReuseDisposition.REUSE
    assert prior.to_dict() == prior_before
    assert target.to_dict() == target_before


def test_explicit_rerun_policy_is_fail_closed_even_when_all_digests_match() -> None:
    prior = _record(reuse_policy=ReusePolicy.RERUN_REQUIRED)
    target = _takeover_target(reuse_policy=ReusePolicy.RERUN_REQUIRED)

    decision = evaluate_child_evidence_reuse(prior, target)

    assert decision.disposition is ReuseDisposition.RERUN
    assert decision.failed_checks == ("reuse_policy",)
