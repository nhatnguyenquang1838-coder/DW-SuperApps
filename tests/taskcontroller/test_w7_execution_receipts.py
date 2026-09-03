from __future__ import annotations

import pytest

from taskcontroller.runtime.certification_models import (
    CertificationCampaign,
    ExecutionReceipt,
    SourceRevision,
    TestCase,
    TestRun,
)
from taskcontroller.runtime.certification_stability import evaluate_w8_stability
from taskcontroller.runtime.live_certification_harness import (
    LiveCertificationError,
    LiveCertificationHarness,
)


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
DIGEST = "sha256:" + "d" * 64


def _receipt(execution_id: str, seq: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        execution_id=execution_id,
        started_at=f"2026-09-03T12:0{seq}:00Z",
        ended_at=f"2026-09-03T12:0{seq}:30Z",
        controller_seq_start=seq * 10,
        controller_seq_end=seq * 10 + 1,
        executor_seq_start=seq * 20,
        executor_seq_end=seq * 20 + 1,
        cursor_before=f"cursor-{seq}-before",
        cursor_after=f"cursor-{seq}-after",
        semantic_step_receipt_digests=("sha256:" + f"{seq:x}" * 64,) if seq < 16 else ("sha256:" + "e" * 64,),
        local_validation_receipts=(f"pytest://run-{seq}",),
        github_workflow_receipts=({"run_id": 1000 + seq, "run_attempt": 1, "head_sha": SHA_A, "conclusion": "SUCCESS"},),
        authority_receipt_refs=(f"authority://{seq}",),
    )


def _run(run_id: str, receipt: ExecutionReceipt, *, recovery: bool = True) -> TestRun:
    return TestRun(
        run_id=run_id,
        campaign_id="RP-CERT-001",
        case_id="TC-RP-001",
        case_revision="2026-09-02-r1",
        runtime=SourceRevision("DW", "runtime-lab/RP-CERT-001", SHA_A, SHA_A),
        subject=SourceRevision("DW", "prove/RP-CERT-001/TC-RP-001", SHA_B, SHA_B),
        gwc_sha=SHA_C,
        runtime_plan_ref="plan://RP-CERT-001/r1",
        runtime_plan_revision="r1",
        runtime_plan_digest=DIGEST,
        executor="Hermes-Mac",
        model="model-a",
        verdict="PASS",
        execution_receipt=receipt,
        evidence={"ci": {"status": "SUCCESS"}, "fresh_controller_recovery": recovery},
    )


def _campaign() -> CertificationCampaign:
    return CertificationCampaign(
        campaign_id="RP-CERT-001",
        mode="RUNTIME_PROVING_LAB",
        runtime_branch="runtime-lab/RP-CERT-001",
        proving_branch="prove/RP-CERT-001/TC-RP-001",
        test_case_id="TC-RP-001",
        test_case_revision="2026-09-02-r1",
        baseline_runtime_sha=SHA_A,
        baseline_subject_sha=SHA_B,
        gwc_sha=SHA_C,
        status="ACTIVE",
    )


def _start(harness: LiveCertificationHarness, run_id: str):
    return harness.start_run(
        campaign_id="RP-CERT-001",
        case_id="TC-RP-001",
        runtime=SourceRevision("DW", "runtime-lab/RP-CERT-001", SHA_A, SHA_A),
        subject=SourceRevision("DW", "prove/RP-CERT-001/TC-RP-001", SHA_B, SHA_B),
        gwc_sha=SHA_C,
        executor="Hermes-Mac",
        model="model-a",
        run_id=run_id,
        runtime_plan_ref="plan://RP-CERT-001/r1",
        runtime_plan_revision="r1",
        runtime_plan_digest=DIGEST,
    )


def test_execution_receipt_has_stable_unique_digest_and_is_immutable():
    receipt = _receipt("exec-001", 1)
    before = receipt.execution_receipt_digest
    assert before.startswith("sha256:")
    assert receipt.to_dict()["execution_receipt_digest"] == before
    with pytest.raises((AttributeError, TypeError)):
        receipt.execution_id = "changed"
    assert receipt.execution_receipt_digest == before


def test_replayed_execution_receipt_cannot_satisfy_w8_stability():
    cloned = _receipt("exec-cloned", 1)
    runs = [_run(f"run-{n}", cloned, recovery=(n == 1)) for n in (1, 2, 3)]
    result = evaluate_w8_stability(runs, ())
    assert result.stable is False
    assert result.clean_streak < 3
    assert "execution" in result.reset_reason.lower() or "receipt" in result.reset_reason.lower()


def test_three_distinct_execution_receipts_can_satisfy_same_source_stability():
    runs = [
        _run("run-1", _receipt("exec-1", 1), recovery=True),
        _run("run-2", _receipt("exec-2", 2), recovery=False),
        _run("run-3", _receipt("exec-3", 3), recovery=False),
    ]
    result = evaluate_w8_stability(runs, ())
    assert result.stable is True
    assert result.clean_streak == 3


def test_harness_rejects_receipt_replay_under_another_run_id():
    harness = LiveCertificationHarness()
    harness.create_campaign(_campaign())
    harness.register_case(TestCase("TC-RP-001", "2026-09-02-r1", "login", "pass", ("taskcontroller",)))
    first = _start(harness, "run-1")
    second = _start(harness, "run-2")
    receipt = _receipt("exec-shared", 1)

    harness.record_verdict(
        first.run_id,
        "PASS",
        {"ci": {"status": "SUCCESS"}},
        execution_receipt=receipt,
    )
    with pytest.raises(LiveCertificationError, match="execution|receipt|replay"):
        harness.record_verdict(
            second.run_id,
            "PASS",
            {"ci": {"status": "SUCCESS"}},
            execution_receipt=receipt,
        )
