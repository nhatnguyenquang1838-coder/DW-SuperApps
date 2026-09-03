from __future__ import annotations

import importlib
import subprocess

import pytest


def _init_real_git_repo(path):
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), check=True, capture_output=True)


def _models():
    return importlib.import_module("taskcontroller.runtime.certification_models")


def _harness_module():
    return importlib.import_module("taskcontroller.runtime.live_certification_harness")


def _evidence_module():
    try:
        return importlib.import_module("taskcontroller.runtime.certification_evidence")
    except ModuleNotFoundError as exc:
        pytest.fail(f"GitHub-backed certification evidence is not implemented yet: {exc}")


def _campaign(models):
    return models.CertificationCampaign(
        campaign_id="RP-CERT-001",
        mode="RUNTIME_PROVING_LAB",
        runtime_branch="runtime-lab/RP-CERT-001",
        proving_branch="prove/RP-CERT-001/TC-RP-001",
        test_case_id="TC-RP-001",
        test_case_revision="2026-09-02-r1",
        baseline_runtime_sha="a" * 40,
        baseline_subject_sha="b" * 40,
        gwc_sha="c" * 40,
        status="ACTIVE",
    )


def _case(models):
    return models.TestCase(
        case_id="TC-RP-001",
        revision="2026-09-02-r1",
        scenario="DW Observatory Login UX",
        acceptance="runtime proving",
        declared_paths=("taskcontroller/runtime",),
    )


def _receipt(models, execution_id: str):
    return models.ExecutionReceipt(
        execution_id=execution_id,
        started_at="2026-09-03T12:00:00Z",
        ended_at="2026-09-03T12:00:30Z",
        controller_seq_start=1,
        controller_seq_end=2,
        executor_seq_start=1,
        executor_seq_end=2,
        cursor_before=f"{execution_id}-before",
        cursor_after=f"{execution_id}-after",
        semantic_step_receipt_digests=("sha256:" + "d" * 64,),
        local_validation_receipts=(f"pytest://{execution_id}",),
        github_workflow_receipts=(
            {
                "run_id": 33758028821,
                "run_attempt": 1,
                "head_sha": "a" * 40,
                "conclusion": "SUCCESS",
            },
        ),
        authority_receipt_refs=(f"authority://{execution_id}",),
    )


def _start_run(harness, models, run_id: str):
    return harness.start_run(
        campaign_id="RP-CERT-001",
        case_id="TC-RP-001",
        runtime=models.SourceRevision(
            "nhatnguyenquang1838-coder/DW-SuperApps",
            "runtime-lab/RP-CERT-001",
            "a" * 40,
            "a" * 40,
        ),
        subject=models.SourceRevision(
            "nhatnguyenquang1838-coder/DW-SuperApps",
            "prove/RP-CERT-001/TC-RP-001",
            "b" * 40,
            "b" * 40,
        ),
        gwc_sha="c" * 40,
        executor="Hermes-Mac",
        model="model-a",
        run_id=run_id,
        runtime_plan_ref="plan://RP-CERT-001/r1",
        runtime_plan_revision="r1",
        runtime_plan_digest="sha256:" + "e" * 64,
        blueprint_ref="blueprint://RP-CERT-001/r1",
        blueprint_digest="sha256:" + "f" * 64,
        harness_sha="a" * 40,
    )


def test_github_backed_bundle_fresh_verifier_survives_original_store_removal(tmp_path):
    models = _models()
    harness_mod = _harness_module()
    evidence = _evidence_module()
    original = tmp_path / "working" / "campaign.events.jsonl"
    harness = harness_mod.LiveCertificationHarness(store=original)
    harness.create_campaign(_campaign(models))
    harness.register_case(_case(models))

    for index in range(1, 4):
        run = _start_run(harness, models, f"run-{index}")
        harness.record_verdict(
            run.run_id,
            "PASS",
            {
                "ci": {"status": "SUCCESS"},
                "fresh_controller_recovery": index == 1,
            },
            execution_receipt=_receipt(models, f"exec-{index}"),
        )

    bundle = tmp_path / "fresh-checkout" / "evidence" / "RP-CERT-001"
    binding = evidence.GitHubEvidenceBinding(
        repository="nhatnguyenquang1838-coder/DW-SuperApps",
        ref="evidence/RP-CERT-001",
        path="evidence/RP-CERT-001",
    )
    evidence.export_github_backed_evidence(original, bundle, binding)
    original.unlink()

    # SCRUM-725 GREEN: attestation is mandatory for qualifying evidence
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    _init_real_git_repo(repo)
    evidence_dest = repo / "evidence" / "RP-CERT-001"
    evidence_dest.mkdir(parents=True)
    for f in ["manifest.json", "campaign.events.jsonl"]:
        (evidence_dest / f).write_bytes((bundle / f).read_bytes())
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "Add evidence bundle"],
        check=True, capture_output=True,
    )
    actual_head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    attestation = evidence.GitHubRetainingCommitAttestation(
        repository="nhatnguyenquang1838-coder/DW-SuperApps",
        ref="evidence/RP-CERT-001",
        commit_sha=actual_head,
        path="evidence/RP-CERT-001",
    )
    verified = evidence.fresh_verify_campaign(bundle, "RP-CERT-001", attestation, git_repo_root=repo)
    assert verified.binding == binding
    assert verified.attestation == attestation
    assert verified.campaign.campaign_id == "RP-CERT-001"
    assert verified.run_ids == ("run-1", "run-2", "run-3")
    assert verified.execution_ids == ("exec-1", "exec-2", "exec-3")
    assert verified.branch_ownership["prove/RP-CERT-001/TC-RP-001"] == "RP-CERT-001"
    assert verified.w8_stability.stable is True


def test_campaign_status_update_is_durable_and_replayed(tmp_path):
    models = _models()
    harness_mod = _harness_module()
    path = tmp_path / "campaign.events.jsonl"
    harness = harness_mod.LiveCertificationHarness(store=path)
    harness.create_campaign(_campaign(models))
    harness.update_campaign_status("RP-CERT-001", "VERIFYING")

    restored = harness_mod.LiveCertificationHarness(store=path)
    assert restored.get_campaign("RP-CERT-001").status == "VERIFYING"


def test_runtime_correction_requires_existing_terminal_successor_execution():
    models = _models()
    harness_mod = _harness_module()
    harness = harness_mod.LiveCertificationHarness()
    harness.create_campaign(_campaign(models))
    harness.register_case(_case(models))
    failed = _start_run(harness, models, "run-fail")
    harness.record_verdict(
        failed.run_id,
        "FAIL",
        {"failure": {"kind": "runtime"}},
        execution_receipt=_receipt(models, "exec-fail"),
    )
    finding = harness.record_finding(
        campaign_id="RP-CERT-001",
        discovered_by_run_id=failed.run_id,
        invariant_id="W7-SUCCESSOR-PROOF",
        severity="P1",
        expected="successor execution exists",
        actual="missing",
        reproduction_refs=("test://run-fail",),
    )

    with pytest.raises(harness_mod.LiveCertificationError, match="successor"):
        harness.record_correction(
            correction_id="correction-invalid",
            finding_ids=(finding.finding_id,),
            runtime_sha="f" * 40,
            regression_evidence=("pytest://red-regression",),
            successor_run_ids=("run-does-not-exist",),
        )
