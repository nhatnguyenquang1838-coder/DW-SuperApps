"""Seq20 C1 — SourceIdentity vs ExecutionIdentity separation (RED first).

The same exact SourceIdentity MAY repeat across TestRuns, but every TestRun
must carry a distinct, immutable ExecutionIdentity bound to unique
``execution_id`` and ``execution_receipt_digest`` values, plus an exact
runtime/harness self-hosting binding that fails closed on mismatch.
"""
from __future__ import annotations

import importlib
import json

import pytest


def _models():
    return importlib.import_module("taskcontroller.runtime.certification_models")


def _revision(models, *, sha: str = "a" * 40, branch: str = "runtime-lab/RP-CERT-001"):
    return models.SourceRevision(
        repository="nhatnguyenquang1838-coder/DW-SuperApps",
        branch=branch,
        start_sha=sha,
        end_sha=sha,
    )


def _receipt(models, *, execution_id="exec-001", receipt_digest=None, harness_sha="a" * 40):
    digest = receipt_digest or "sha256:" + "1" * 64
    return models.ExecutionReceipt(
        execution_id=execution_id,
        started_at="2026-09-02T04:00:00+07:00",
        completed_at="2026-09-02T04:30:00+07:00",
        controller_seq_start=19,
        controller_seq_end=20,
        executor_seq_start=51,
        executor_seq_end=52,
        cursor_before="cursor-before-1",
        cursor_after="cursor-after-1",
        step_receipt_digests=("step://1",),
        local_validation_receipts=("pnpm-test://sha256:" + "2" * 64,),
        ci_run_refs=(),
        authority_refs=(),
        harness_sha=harness_sha,
        harness_is_runtime=True,
        execution_receipt_digest=digest,
    )


def test_execution_receipt_is_deeply_immutable_and_digest_stable():
    models = _models()
    receipt = _receipt(models)
    before = receipt.execution_receipt_digest
    with pytest.raises((AttributeError, TypeError)):
        receipt.execution_id = "changed"
    with pytest.raises(TypeError):
        receipt.step_receipt_digests[0] = "mutated"
    assert receipt.execution_receipt_digest == before


def test_duplicate_execution_id_and_digest_fail_closed_on_run_binding():
    models = _models()
    run_a = models.TestRun(
        run_id="run-1",
        campaign_id="RP-CERT-001",
        case_id="TC-RP-001",
        case_revision="2026-09-02-r1",
        runtime=_revision(models),
        subject=_revision(models, sha="b" * 40, branch="prove/RP-CERT-001/TC-RP-001"),
        gwc_sha="c" * 40,
        runtime_plan_ref="plan://RP-CERT-001/r1",
        runtime_plan_revision="r1",
        runtime_plan_digest="sha256:" + "d" * 64,
        executor="Hermes-Mac",
        model="model-a",
        verdict="PASS",
        evidence={"ci": {"status": "SUCCESS"}},
        execution=_receipt(models, execution_id="exec-1", receipt_digest="sha256:" + "1" * 64),
    )
    assert run_a.digest
    # same source identity, distinct execution id+digest is allowed at model level
    run_b = models.TestRun(
        run_id="run-2",
        campaign_id="RP-CERT-001",
        case_id="TC-RP-001",
        case_revision="2026-09-02-r1",
        runtime=_revision(models),
        subject=_revision(models, sha="b" * 40, branch="prove/RP-CERT-001/TC-RP-001"),
        gwc_sha="c" * 40,
        runtime_plan_ref="plan://RP-CERT-001/r1",
        runtime_plan_revision="r1",
        runtime_plan_digest="sha256:" + "d" * 64,
        executor="Hermes-Mac",
        model="model-a",
        verdict="PASS",
        evidence={"ci": {"status": "SUCCESS"}},
        execution=_receipt(models, execution_id="exec-2", receipt_digest="sha256:" + "2" * 64),
    )
    assert run_b.digest != run_a.digest
    with pytest.raises(ValueError, match="started_at"):
        models.ExecutionReceipt(
            execution_id="exec-1",
            started_at="",
            completed_at="",
            controller_seq_start=19,
            controller_seq_end=20,
            executor_seq_start=51,
            executor_seq_end=52,
            cursor_before="",
            cursor_after="",
            step_receipt_digests=(),
            local_validation_receipts=(),
            ci_run_refs=(),
            authority_refs=(),
            harness_sha="a" * 40,
            harness_is_runtime=True,
            execution_receipt_digest="sha256:" + "1" * 64,
        )


def test_runtime_harness_self_hosting_fails_closed_on_mismatch():
    models = _models()
    with pytest.raises(ValueError, match="harness|runtime"):
        models.TestRun(
            run_id="run-mismatch",
            campaign_id="RP-CERT-001",
            case_id="TC-RP-001",
            case_revision="2026-09-02-r1",
            runtime=_revision(models),  # runtime end_sha = a*40
            subject=_revision(models, sha="b" * 40, branch="prove/RP-CERT-001/TC-RP-001"),
            gwc_sha="c" * 40,
            runtime_plan_ref="plan://RP-CERT-001/r1",
            runtime_plan_revision="r1",
            runtime_plan_digest="sha256:" + "d" * 64,
            executor="Hermes-Mac",
            model="model-a",
            verdict="PASS",
            evidence={"ci": {"status": "SUCCESS"}},
            execution=_receipt(models, harness_sha="f" * 40),
        )


def test_testrun_requires_execution_identity():
    models = _models()
    with pytest.raises((ValueError, TypeError), match="execution"):
        models.TestRun(
            run_id="run-n",
            campaign_id="RP-CERT-001",
            case_id="TC-RP-001",
            case_revision="2026-09-02-r1",
            runtime=_revision(models),
            subject=_revision(models, sha="b" * 40, branch="prove/RP-CERT-001/TC-RP-001"),
            gwc_sha="c" * 40,
            runtime_plan_ref="plan://RP-CERT-001/r1",
            runtime_plan_revision="r1",
            runtime_plan_digest="sha256:" + "d" * 64,
            executor="Hermes-Mac",
            model="model-a",
            verdict="PASS",
            evidence={"ci": {"status": "SUCCESS"}},
        )


def test_execution_receipt_serialization_is_detached_json():
    models = _models()
    receipt = _receipt(models)
    data = receipt.to_dict()
    assert isinstance(data["step_receipt_digests"], list)
    data["step_receipt_digests"].append("mutated")
    json.dumps(data)
    assert receipt.step_receipt_digests == ("step://1",)
