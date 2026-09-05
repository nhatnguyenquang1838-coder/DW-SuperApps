from __future__ import annotations

import importlib
import json
from types import MappingProxyType

import pytest


def _models():
    try:
        return importlib.import_module("taskcontroller.runtime.certification_models")
    except ModuleNotFoundError as exc:  # RED until the model module exists.
        pytest.fail(f"certification_models is not implemented yet: {exc}")


def _revision(models, *, sha: str = "a" * 40):
    return models.SourceRevision(
        repository="nhatnguyenquang1838-coder/DW-SuperApps",
        branch="runtime-lab/RP-CERT-001",
        start_sha=sha,
        end_sha=sha,
    )


def _case(models):
    return models.TestCase(
        case_id="TC-RP-001",
        revision="2026-09-02-r1",
        scenario="DW Observatory Login UX",
        acceptance="local validation and loading feedback",
        declared_paths=(
            "projects/dw-observation/app/login/page.tsx",
            "projects/dw-observation/app/login/page.test.tsx",
        ),
    )


def _run(models, evidence=None):
    revision = _revision(models)
    return models.TestRun(
        run_id="run-001",
        campaign_id="RP-CERT-001",
        case_id="TC-RP-001",
        case_revision="2026-09-02-r1",
        runtime=revision,
        subject=_revision(models, sha="b" * 40),
        gwc_sha="c" * 40,
        runtime_plan_ref="plan://RP-CERT-001/r1",
        runtime_plan_revision="r1",
        runtime_plan_digest="sha256:" + "d" * 64,
        executor="Hermes-Mac",
        model="current-hermes-model",
        verdict="PASS",
        evidence=evidence or {"ci": {"runs": [33544981514], "status": "SUCCESS"}},
    )


def test_source_revision_rejects_non_exact_sha():
    models = _models()
    with pytest.raises(ValueError, match="40-hex"):
        _revision(models, sha="not-a-sha")


def test_test_case_requires_revision_and_declared_paths():
    models = _models()
    with pytest.raises(ValueError, match="revision"):
        models.TestCase(
            case_id="TC-RP-001",
            revision="",
            scenario="login",
            acceptance="works",
            declared_paths=("projects/dw-observation/app/login/page.tsx",),
        )
    with pytest.raises(ValueError, match="declared_paths"):
        models.TestCase(
            case_id="TC-RP-001",
            revision="2026-09-02-r1",
            scenario="login",
            acceptance="works",
            declared_paths=(),
        )


def test_test_run_deep_freezes_nested_evidence_and_digest():
    models = _models()
    evidence = {"nested": {"items": ["before"]}}
    run = _run(models, evidence=evidence)
    before = run.digest

    evidence["nested"]["items"].append("outside")
    assert run.evidence["nested"]["items"] == ("before",)
    assert run.digest == before
    assert isinstance(run.evidence, MappingProxyType)
    with pytest.raises(TypeError):
        run.evidence["new"] = "mutation"


def test_test_run_serialization_is_detached_plain_data():
    models = _models()
    run = _run(models)
    serialized = run.to_dict()
    assert isinstance(serialized, dict)
    assert isinstance(serialized["evidence"], dict)
    serialized["evidence"]["ci"]["runs"].append(999)
    assert 999 not in run.evidence["ci"]["runs"]
    json.dumps(serialized)


def test_test_case_and_campaign_are_frozen():
    models = _models()
    case = _case(models)
    with pytest.raises((AttributeError, TypeError)):
        case.revision = "changed"

    campaign = models.CertificationCampaign(
        campaign_id="RP-CERT-001",
        mode="RUNTIME_PROVING_LAB",
        runtime_branch="runtime-lab/RP-CERT-001",
        proving_branch="prove/RP-CERT-001/TC-RP-001",
        test_case_id=case.case_id,
        test_case_revision=case.revision,
        baseline_runtime_sha="a" * 40,
        baseline_subject_sha="b" * 40,
        gwc_sha="c" * 40,
        status="ACTIVE",
    )
    with pytest.raises((AttributeError, TypeError)):
        campaign.status = "CERTIFIED"


def test_runtime_finding_cannot_be_resolved_without_correction_evidence():
    models = _models()
    with pytest.raises(ValueError, match="RuntimeCorrection"):
        models.RuntimeFinding(
            finding_id="finding-001",
            campaign_id="RP-CERT-001",
            discovered_by_run_id="run-001",
            invariant_id="W8-IMMUTABLE-EVIDENCE",
            severity="P1",
            expected="immutable",
            actual="mutable",
            reproduction_refs=("test://run-001",),
            status="RESOLVED",
        )

    correction = models.RuntimeCorrection(
        correction_id="correction-001",
        finding_ids=("finding-001",),
        runtime_sha="e" * 40,
        regression_evidence=("tests/taskcontroller/test_certification_models.py::test_test_run_deep_freezes_nested_evidence_and_digest",),
        successor_run_ids=("run-002",),
    )
    finding = models.RuntimeFinding(
        finding_id="finding-001",
        campaign_id="RP-CERT-001",
        discovered_by_run_id="run-001",
        invariant_id="W8-IMMUTABLE-EVIDENCE",
        severity="P1",
        expected="immutable",
        actual="mutable",
        reproduction_refs=("test://run-001",),
        status="RESOLVED",
        correction_id=correction.correction_id,
        correction_sha=correction.runtime_sha,
        regression_evidence=correction.regression_evidence,
        successor_run_ids=correction.successor_run_ids,
    )
    assert finding.status == "RESOLVED"
