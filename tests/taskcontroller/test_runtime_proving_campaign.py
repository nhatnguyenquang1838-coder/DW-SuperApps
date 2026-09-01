from __future__ import annotations

import importlib

import pytest


def _harness_module():
    return importlib.import_module("taskcontroller.runtime.live_certification_harness")


def _models():
    return importlib.import_module("taskcontroller.runtime.certification_models")


def _case(models):
    return models.TestCase(
        case_id="TC-RP-001",
        revision="2026-09-02-r1",
        scenario="DW Observatory Login UX",
        acceptance="local login validation",
        declared_paths=("projects/dw-observation/app/login/page.tsx",),
    )


def _campaign(models, campaign_id="RP-CERT-001"):
    return models.CertificationCampaign(
        campaign_id=campaign_id,
        mode="RUNTIME_PROVING_LAB",
        runtime_branch="runtime-lab/" + campaign_id,
        proving_branch="prove/" + campaign_id + "/TC-RP-001",
        test_case_id="TC-RP-001",
        test_case_revision="2026-09-02-r1",
        baseline_runtime_sha="a" * 40,
        baseline_subject_sha="b" * 40,
        gwc_sha="c" * 40,
        status="ACTIVE",
    )


def _revision(models, branch, start, end, repository="nhatnguyenquang1838-coder/DW-SuperApps"):
    return models.SourceRevision(repository, branch, start * 40 if len(start) == 1 else start, end * 40 if len(end) == 1 else end)


def _start(harness, models, *, campaign_id="RP-CERT-001", run_id=None, end="d", subject_branch=None):
    return harness.start_run(
        campaign_id=campaign_id,
        case_id="TC-RP-001",
        runtime=_revision(models, "runtime-lab/" + campaign_id, "a", end),
        subject=_revision(models, subject_branch or "prove/" + campaign_id + "/TC-RP-001", "b", end),
        gwc_sha="c" * 40,
        executor="Hermes-Mac",
        model="current-hermes-model",
        run_id=run_id,
        runtime_plan_ref="plan://" + campaign_id + "/r1",
        runtime_plan_revision="r1",
        runtime_plan_digest="sha256:" + "e" * 64,
    )


def test_same_campaign_reuses_proving_branch_with_new_exact_run():
    mod = _harness_module()
    models = _models()
    harness = mod.LiveCertificationHarness()
    campaign = _campaign(models)
    harness.create_campaign(campaign)
    harness.register_case(_case(models))

    first = _start(harness, models, end="d")
    harness.record_verdict(first.run_id, "PASS", {"ci": {"status": "SUCCESS"}})
    second = _start(harness, models, end="f")

    assert second.run_id != first.run_id
    assert second.subject.branch == first.subject.branch
    assert second.subject.end_sha != first.subject.end_sha


def test_cross_campaign_branch_reuse_fails_closed():
    mod = _harness_module()
    models = _models()
    harness = mod.LiveCertificationHarness()
    harness.create_campaign(_campaign(models, "RP-CERT-001"))
    harness.create_campaign(_campaign(models, "RP-CERT-002"))
    harness.register_case(_case(models))
    _start(harness, models, campaign_id="RP-CERT-001", end="d")
    with pytest.raises(mod.LiveCertificationError, match="campaign|branch"):
        _start(harness, models, campaign_id="RP-CERT-002", end="f", subject_branch="prove/RP-CERT-001/TC-RP-001")


def test_duplicate_run_identity_and_exact_source_tuple_are_rejected():
    mod = _harness_module()
    models = _models()
    harness = mod.LiveCertificationHarness()
    harness.create_campaign(_campaign(models))
    harness.register_case(_case(models))
    _start(harness, models, run_id="run-fixed", end="d")
    with pytest.raises(mod.LiveCertificationError, match="duplicate|identity"):
        _start(harness, models, run_id="run-fixed", end="f")
    with pytest.raises(mod.LiveCertificationError, match="duplicate|source"):
        _start(harness, models, run_id="run-other", end="d")


def test_terminal_run_and_evidence_remain_immutable_after_correction():
    mod = _harness_module()
    models = _models()
    harness = mod.LiveCertificationHarness()
    harness.create_campaign(_campaign(models))
    harness.register_case(_case(models))
    run = _start(harness, models, end="d")
    harness.record_verdict(run.run_id, "FAIL", {"failure": {"kind": "runtime"}})
    finding = harness.record_finding(
        campaign_id="RP-CERT-001",
        discovered_by_run_id=run.run_id,
        invariant_id="W8-PLAN-BOUND",
        severity="P1",
        expected="bound",
        actual="bypass",
        reproduction_refs=("test://run-fixed",),
    )
    correction = harness.record_correction(
        correction_id="correction-001",
        finding_ids=(finding.finding_id,),
        runtime_sha="f" * 40,
        regression_evidence=("test://regression",),
        successor_run_ids=("run-successor",),
    )
    stored = harness.get_run(run.run_id)
    assert stored.verdict == "FAIL"
    assert stored.evidence["failure"]["kind"] == "runtime"
    assert correction.runtime_sha == "f" * 40
    assert harness.get_finding(finding.finding_id).status == "RESOLVED"


def test_restart_replays_campaign_runs_and_branch_ownership(tmp_path):
    mod = _harness_module()
    models = _models()
    path = tmp_path / "campaign.events.jsonl"
    harness = mod.LiveCertificationHarness(store=path)
    harness.create_campaign(_campaign(models))
    harness.register_case(_case(models))
    run = _start(harness, models, end="d")
    harness.record_verdict(run.run_id, "PASS", {"ci": {"status": "SUCCESS"}})

    restored = mod.LiveCertificationHarness(store=path)
    assert restored.get_campaign("RP-CERT-001").status == "ACTIVE"
    assert restored.get_run(run.run_id).verdict == "PASS"
    with pytest.raises(mod.LiveCertificationError, match="duplicate|source"):
        _start(restored, models, run_id="new-run", end="d")
