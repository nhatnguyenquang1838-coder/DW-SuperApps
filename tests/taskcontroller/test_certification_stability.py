from __future__ import annotations

import importlib

import pytest


def _stability_module():
    try:
        return importlib.import_module("taskcontroller.runtime.certification_stability")
    except ModuleNotFoundError as exc:
        pytest.fail(f"certification_stability is not implemented yet: {exc}")


def _models():
    return importlib.import_module("taskcontroller.runtime.certification_models")


def _run(models, run_id: str, runtime_sha: str = "a", case_id: str = "TC-RP-001", executor: str = "Hermes-Mac", model: str = "model-a", evidence=None):
    sha = runtime_sha * 40 if len(runtime_sha) == 1 else runtime_sha
    receipt = models.ExecutionReceipt(
        execution_id=f"exec-{run_id}",
        started_at="2026-09-03T12:00:00Z",
        ended_at="2026-09-03T12:00:30Z",
        controller_seq_start=1,
        controller_seq_end=2,
        executor_seq_start=1,
        executor_seq_end=2,
        cursor_before=f"{run_id}-before",
        cursor_after=f"{run_id}-after",
        semantic_step_receipt_digests=("sha256:" + "e" * 64,),
        local_validation_receipts=(f"pytest://{run_id}",),
        github_workflow_receipts=(
            {"run_id": 1001, "run_attempt": 1, "head_sha": sha, "conclusion": "SUCCESS"},
        ),
        authority_receipt_refs=(f"authority://{run_id}",),
    )
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
        executor=executor,
        model=model,
        verdict="PASS",
        execution_receipt=receipt,
        evidence=evidence or {"ci": {"status": "SUCCESS"}, "fresh_controller_recovery": True},
    )


def test_w8_requires_three_consecutive_clean_runs_and_recovery():
    mod = _stability_module()
    models = _models()
    runs = [_run(models, f"run-{n}") for n in (1, 2)]
    result = mod.evaluate_w8_stability(runs, ())
    assert result.stable is False
    assert result.clean_streak == 2
    assert result.qualifying_run_ids == ("run-1", "run-2")

    runs.append(_run(models, "run-3", evidence={"ci": {"status": "SUCCESS"}, "fresh_controller_recovery": False}))
    result = mod.evaluate_w8_stability(runs, ())
    assert result.stable is True
    assert result.clean_streak == 3


def test_w8_runtime_sha_change_resets_clean_streak():
    mod = _stability_module()
    models = _models()
    runs = [_run(models, "run-1"), _run(models, "run-2"), _run(models, "run-3", runtime_sha="f")]
    result = mod.evaluate_w8_stability(runs, ())
    assert result.stable is False
    assert result.clean_streak == 1
    assert "runtime" in result.reset_reason


def test_w8_unresolved_p1_and_stale_pass_cannot_qualify():
    mod = _stability_module()
    models = _models()
    runs = [_run(models, f"run-{n}") for n in (1, 2, 3)]
    finding = models.RuntimeFinding(
        finding_id="finding-1",
        campaign_id="RP-CERT-001",
        discovered_by_run_id="run-1",
        invariant_id="W8-RUNTIME",
        severity="P1",
        expected="safe",
        actual="unsafe",
        reproduction_refs=("test://finding-1",),
        status="OPEN",
    )
    result = mod.evaluate_w8_stability(runs, (finding,))
    assert result.stable is False
    assert "finding" in result.reset_reason

    result = mod.evaluate_w8_stability(runs, (), expected_runtime_sha="f" * 40)
    assert result.stable is False
    assert result.clean_streak == 0
    assert "runtime" in result.reset_reason


def test_deep_case_thresholds_require_distinct_identities_when_requested():
    mod = _stability_module()
    models = _models()
    runs = [
        _run(models, "c1", case_id="W9-C3", executor="Hermes-Mac", model="model-a"),
        _run(models, "c2", case_id="W9-C3", executor="Hermes-Mac", model="model-a"),
        _run(models, "c3", case_id="W9-C3", executor="Hermes-Mac", model="model-a"),
    ]
    result = mod.evaluate_deep_case_stability("W9-C3", runs, threshold=3, minimum_identities=2)
    assert result.stable is False
    assert result.qualifying_count == 3

    runs[-1] = _run(models, "c3", case_id="W9-C3", executor="Hermes-Cloud", model="model-b")
    result = mod.evaluate_deep_case_stability("W9-C3", runs, threshold=3, minimum_identities=2)
    assert result.stable is True


def test_deep_case_matrix_requires_all_rows():
    mod = _stability_module()
    models = _models()
    run = _run(
        models,
        "inj-1",
        case_id="W9-C5",
        evidence={
            "ci": {"status": "SUCCESS"},
            "injection_matrix": {
                "undeclared_outcome": "PASS",
                "undeclared_action": "PASS",
                "authority_claim": "FAIL",
            },
        },
    )
    result = mod.evaluate_deep_case_stability(
        "W9-C5", (run,), threshold=1,
        required_matrix_rows=("undeclared_outcome", "undeclared_action", "authority_claim"),
    )
    assert result.stable is False

    run = _run(
        models,
        "inj-2",
        case_id="W9-C5",
        evidence={
            "ci": {"status": "SUCCESS"},
            "injection_matrix": {
                "undeclared_outcome": "PASS",
                "undeclared_action": "PASS",
                "authority_claim": "PASS",
            },
        },
    )
    result = mod.evaluate_deep_case_stability(
        "W9-C5", (run,), threshold=1,
        required_matrix_rows=("undeclared_outcome", "undeclared_action", "authority_claim"),
    )
    assert result.stable is True


def test_campaign_certified_requires_w8_all_deep_and_no_p0_p1():
    mod = _stability_module()
    w8 = mod.W8StabilityResult(True, 3, ("r1", "r2", "r3"), "")
    deep = (mod.DeepCaseStabilityResult("W9-C1", True, 3, ("c1", "c2", "c3")),)
    assert mod.evaluate_campaign_certified(w8, deep, ()) is True
