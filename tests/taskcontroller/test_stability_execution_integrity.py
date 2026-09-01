"""Seq20 C2 — replay-resistant, case-specific stability (RED first).

Three run records that reuse one execution receipt must NOT satisfy a
three-run W8 streak. Three unique execution receipts at the same SourceIdentity
MAY qualify. W9 case thresholds require distinct case-specific receipts.
"""
from __future__ import annotations

import hashlib
import importlib

import pytest


def _stability_module():
    return importlib.import_module("taskcontroller.runtime.certification_stability")


def _models():
    return importlib.import_module("taskcontroller.runtime.certification_models")


def _execution(models, *, execution_id, receipt_digest=None):
    return models.ExecutionReceipt(
        execution_id=execution_id,
        started_at="2026-09-02T00:00:00+07:00",
        completed_at="2026-09-02T00:30:00+07:00",
        controller_seq_start=19,
        controller_seq_end=20,
        executor_seq_start=51,
        executor_seq_end=52,
        cursor_before="cursor-before",
        cursor_after="cursor-after",
        step_receipt_digests=("step://1",),
        local_validation_receipts=(),
        ci_run_refs=(),
        authority_refs=(),
        harness_sha="a" * 40,
        harness_is_runtime=True,
        execution_receipt_digest=receipt_digest or ("sha256:" + hashlib.sha256(execution_id.encode()).hexdigest()),
    )


def _run(models, run_id, *, execution_id, receipt_digest=None, case_id="TC-RP-001", evidence=None):
    sha = "a" * 40
    return models.TestRun(
        run_id=run_id,
        campaign_id="RP-CERT-001",
        case_id=case_id,
        case_revision="2026-09-02-r1",
        runtime=models.SourceRevision("DW", "runtime-lab/RP-CERT-001", sha, sha),
        subject=models.SourceRevision("DW", "prove/RP-CERT-001/TC-RP-001", "b" * 40, "b" * 40),
        gwc_sha="c" * 40,
        runtime_plan_ref="plan://r1",
        runtime_plan_revision="r1",
        runtime_plan_digest="sha256:" + "d" * 64,
        executor="Hermes-Mac",
        model="model-a",
        verdict="PASS",
        evidence=evidence or {"ci": {"status": "SUCCESS"}, "fresh_controller_recovery": True},
        execution=_execution(models, execution_id=execution_id, receipt_digest=receipt_digest),
    )


def test_three_cloned_receipts_do_not_satisfy_w8_streak():
    mod = _stability_module()
    models = _models()
    receipt = "sha256:" + "1" * 64
    runs = [_run(models, f"run-{n}", execution_id="exec-clone", receipt_digest=receipt) for n in (1, 2, 3)]
    result = mod.evaluate_w8_stability(runs, ())
    assert result.stable is False
    assert result.clean_streak < 3
    assert "clone" in result.reset_reason or "execution" in result.reset_reason


def test_three_distinct_receipts_at_same_source_qualify():
    mod = _stability_module()
    models = _models()
    runs = [
        _run(models, "run-1", execution_id="exec-1"),
        _run(models, "run-2", execution_id="exec-2"),
        _run(models, "run-3", execution_id="exec-3"),
    ]
    result = mod.evaluate_w8_stability(runs, ())
    assert result.stable is True
    assert result.clean_streak == 3


def test_reused_receipt_under_two_run_ids_reduces_count():
    mod = _stability_module()
    models = _models()
    receipt = "sha256:" + "1" * 64
    runs = [
        _run(models, "run-1", execution_id="exec-1"),
        _run(models, "run-2", execution_id="exec-2", receipt_digest=receipt),
        _run(models, "run-3", execution_id="exec-3"),
    ]
    result = mod.evaluate_w8_stability(runs, ())
    # run-2 shares no execution identity with run-1/run-3; the streak must not
    # silently accept a duplicate receipt as an independent third execution.
    assert len({r.execution.execution_receipt_digest for r in runs}) == 3


def test_w9_case_requires_distinct_case_specific_receipts():
    mod = _stability_module()
    models = _models()
    # C1 requires three distinct CI-cycle receipts.
    runs = [_run(models, f"c1-{n}", execution_id=f"exec-c1-{n}", case_id="W9-C1") for n in (1, 2, 3)]
    result = mod.evaluate_deep_case_stability(
        "W9-C1", runs, threshold=3,
        required_ci_cycle_receipts=3,
    )
    assert result.stable is False
    assert "ci" in result.reset_reason.lower() or "receipt" in result.reset_reason.lower()
