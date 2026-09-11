"""SCRUM-725 GREEN regression — GitHub-backed evidence binding with mandatory external attestation.

Tests the corrected contract:
  - manifest binding: repository + ref + path + intrinsic hashes (NO commit_sha)
  - external attestation: GitHubRetainingCommitAttestation(repository/ref/commit_sha/path)
  - fresh_verify_campaign requires attestation + git_repo_root; fail-closed on mismatch
  - negative tests: wrong SHA, wrong ref/path/repo, tampered bundle hashes
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from taskcontroller.runtime.certification_models import (
    CertificationCampaign,
    ExecutionReceipt,
    SourceRevision,
    TestCase,
)
from taskcontroller.runtime.live_certification_harness import (
    LiveCertificationHarness,
    LiveCertificationError,
)
from taskcontroller.runtime.certification_evidence import (
    CertificationEvidenceError,
    GitHubEvidenceBinding,
    GitHubRetainingCommitAttestation,
    export_github_backed_evidence,
    fresh_verify_campaign,
    verify_retaining_commit_attestation,
)


def _campaign():
    return CertificationCampaign(
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


def _case():
    return TestCase(
        case_id="TC-RP-001",
        revision="2026-09-02-r1",
        scenario="DW Observatory Login UX",
        acceptance="runtime proving",
        declared_paths=("taskcontroller/runtime",),
    )


def _init_real_git_repo(path: Path):
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), check=True, capture_output=True)


def _commit_bundle(bundle: Path, repo: Path) -> str:
    """Copy exported bundle into real Git repo and commit; return actual HEAD."""
    evidence_dest = repo / "evidence" / "RP-CERT-001"
    evidence_dest.mkdir(parents=True)
    for f in ["manifest.json", "campaign.events.jsonl"]:
        (evidence_dest / f).write_bytes((bundle / f).read_bytes())
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "Add evidence bundle"],
        check=True, capture_output=True,
    )
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _export_bundle(tmp_path):
    """Export a valid evidence bundle using W7 public APIs with a terminal TestRun."""
    working_store = tmp_path / "working" / "campaign.events.jsonl"
    working_store.parent.mkdir(parents=True)
    harness = LiveCertificationHarness(store=working_store)
    harness.create_campaign(_campaign())
    harness.register_case(_case())

    # Start + record terminal PASS so fresh_verify_campaign finds a qualifying run
    run = harness.start_run(
        campaign_id="RP-CERT-001",
        case_id="TC-RP-001",
        runtime=SourceRevision(
            "nhatnguyenquang1838-coder/DW-SuperApps",
            "runtime-lab/RP-CERT-001",
            "a" * 40,
            "a" * 40,
        ),
        subject=SourceRevision(
            "nhatnguyenquang1838-coder/DW-SuperApps",
            "prove/RP-CERT-001/TC-RP-001",
            "b" * 40,
            "b" * 40,
        ),
        gwc_sha="c" * 40,
        executor="Hermes-Cloud",
        model="test-model",
        run_id="W8-R3-01",
        runtime_plan_ref="plan://RP-CERT-001/r1",
        runtime_plan_revision="r1",
        runtime_plan_digest="sha256:" + "d" * 64,
        blueprint_ref="blueprint://RP-CERT-001/r1",
        blueprint_digest="sha256:" + "e" * 64,
        harness_sha="f" * 40,
    )
    receipt = ExecutionReceipt(
        execution_id="exec-W8-R3-01",
        started_at="2026-09-03T12:00:00Z",
        ended_at="2026-09-03T12:00:30Z",
        controller_seq_start=1,
        controller_seq_end=1,
        executor_seq_start=1,
        executor_seq_end=1,
        cursor_before="exec-W8-R3-01-before",
        cursor_after="exec-W8-R3-01-after",
        semantic_step_receipt_digests=("sha256:" + "10" * 32,),
        local_validation_receipts=("pytest://W8-R3-01",),
        github_workflow_receipts=(
            {
                "run_id": 99999999999,
                "run_attempt": 1,
                "head_sha": "a" * 40,
                "conclusion": "SUCCESS",
            },
        ),
        authority_receipt_refs=(),
    )
    harness.record_verdict(run.run_id, "PASS", {"ci": {"status": "SUCCESS"}}, execution_receipt=receipt)

    bundle = tmp_path / "bundle" / "evidence" / "RP-CERT-001"
    binding = GitHubEvidenceBinding(
        repository="nhatnguyenquang1838-coder/DW-SuperApps",
        ref="evidence/RP-CERT-001",
        path="evidence/RP-CERT-001",
    )
    export_github_backed_evidence(working_store, bundle, binding)
    return bundle


class TestSCRUM725EvidenceBindingGreen:
    """SCRUM-725 GREEN: two-identity evidence binding with mandatory external attestation."""

    def test_fresh_verify_succeeds_with_correct_attestation(self, tmp_path):
        """GREEN: fresh_verify_campaign succeeds when attestation + git_repo_root are valid."""
        bundle = _export_bundle(tmp_path)
        repo = tmp_path / "gitrepo"
        repo.mkdir()
        _init_real_git_repo(repo)
        actual_head = _commit_bundle(bundle, repo)

        attestation = GitHubRetainingCommitAttestation(
            repository="nhatnguyenquang1838-coder/DW-SuperApps",
            ref="evidence/RP-CERT-001",
            commit_sha=actual_head,
            path="evidence/RP-CERT-001",
        )
        result = fresh_verify_campaign(bundle, "RP-CERT-001", attestation, git_repo_root=repo)
        assert result.campaign.campaign_id == "RP-CERT-001"
        assert result.binding.repository == "nhatnguyenquang1838-coder/DW-SuperApps"
        assert result.attestation.commit_sha == actual_head

    def test_manifest_has_no_commit_sha(self, tmp_path):
        """GREEN: manifest binding must not contain commit_sha (SCRUM-725)."""
        bundle = _export_bundle(tmp_path)
        manifest = json.loads((bundle / "manifest.json").read_text())
        assert "commit_sha" not in manifest["binding"]
        assert manifest["binding"]["repository"] == "nhatnguyenquang1838-coder/DW-SuperApps"
        assert manifest["binding"]["path"] == "evidence/RP-CERT-001"
        assert "events_sha256" in manifest
        assert "manifest_digest" in manifest

    def test_missing_git_repo_root_is_rejected(self, tmp_path):
        """Negative: fresh_verify_campaign requires git_repo_root; fail-closed."""
        bundle = _export_bundle(tmp_path)
        attestation = GitHubRetainingCommitAttestation(
            repository="nhatnguyenquang1838-coder/DW-SuperApps",
            ref="evidence/RP-CERT-001",
            commit_sha="a" * 40,
            path="evidence/RP-CERT-001",
        )
        with pytest.raises(CertificationEvidenceError, match="qualifying verification requires git_repo_root"):
            fresh_verify_campaign(bundle, "RP-CERT-001", attestation, git_repo_root="/nonexistent")

    def test_wrong_commit_sha_rejected(self, tmp_path):
        """Negative: attestation with wrong commit_sha raises CertificationEvidenceError."""
        bundle = _export_bundle(tmp_path)
        repo = tmp_path / "gitrepo"
        repo.mkdir()
        _init_real_git_repo(repo)
        actual_head = _commit_bundle(bundle, repo)

        wrong_sha = "f" * 40
        if wrong_sha == actual_head:
            wrong_sha = "e" * 40

        attestation = GitHubRetainingCommitAttestation(
            repository="nhatnguyenquang1838-coder/DW-SuperApps",
            ref="evidence/RP-CERT-001",
            commit_sha=wrong_sha,
            path="evidence/RP-CERT-001",
        )
        with pytest.raises(CertificationEvidenceError, match="not found|not a commit"):
            fresh_verify_campaign(bundle, "RP-CERT-001", attestation, git_repo_root=repo)

    def test_wrong_path_rejected(self, tmp_path):
        """Negative: attestation with wrong path raises error."""
        bundle = _export_bundle(tmp_path)
        repo = tmp_path / "gitrepo"
        repo.mkdir()
        _init_real_git_repo(repo)
        actual_head = _commit_bundle(bundle, repo)

        attestation = GitHubRetainingCommitAttestation(
            repository="nhatnguyenquang1838-coder/DW-SuperApps",
            ref="evidence/RP-CERT-001",
            commit_sha=actual_head,
            path="evidence/WRONG-PATH",
        )
        with pytest.raises(CertificationEvidenceError, match="missing expected files"):
            fresh_verify_campaign(bundle, "RP-CERT-001", attestation, git_repo_root=repo)

    def test_wrong_repository_rejected(self, tmp_path):
        """Negative: attestation with wrong repository still passes tree check but fails cross-check."""
        bundle = _export_bundle(tmp_path)
        repo = tmp_path / "gitrepo"
        repo.mkdir()
        _init_real_git_repo(repo)
        actual_head = _commit_bundle(bundle, repo)

        attestation = GitHubRetainingCommitAttestation(
            repository="wrong/repo",
            ref="evidence/RP-CERT-001",
            commit_sha=actual_head,
            path="evidence/RP-CERT-001",
        )
        with pytest.raises(CertificationEvidenceError, match="does not match manifest binding"):
            fresh_verify_campaign(bundle, "RP-CERT-001", attestation, git_repo_root=repo)

    def test_tampered_manifest_rejected_by_external_attestation(self, tmp_path):
        """Negative: tampered manifest is detected by external tree verification."""
        bundle = _export_bundle(tmp_path)
        repo = tmp_path / "gitrepo"
        repo.mkdir()
        _init_real_git_repo(repo)
        actual_head = _commit_bundle(bundle, repo)

        # Tamper with the manifest in the committed tree
        manifest_path = repo / "evidence" / "RP-CERT-001" / "manifest.json"
        tampered = json.loads(manifest_path.read_text())
        tampered["binding"]["repository"] = "tampered/repo"
        manifest_path.write_text(json.dumps(tampered, indent=2))
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-am", "tamper"],
            check=True, capture_output=True,
        )
        tampered_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

        # Re-read the original (untampered) bundle's manifest for attestation
        # The committed manifest differs from the exported manifest
        attestation = GitHubRetainingCommitAttestation(
            repository="nhatnguyenquang1838-coder/DW-SuperApps",
            ref="evidence/RP-CERT-001",
            commit_sha=tampered_head,
            path="evidence/RP-CERT-001",
        )
        with pytest.raises(CertificationEvidenceError, match="does not match the exported manifest"):
            fresh_verify_campaign(bundle, "RP-CERT-001", attestation, git_repo_root=repo)

    def test_tampered_events_sha256_rejected(self, tmp_path):
        """Negative: tampering events_sha256 in manifest is rejected by internal digest check."""
        bundle = _export_bundle(tmp_path)
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["events_sha256"] = "sha256:" + "0" * 64
        manifest_path.write_text(json.dumps(manifest) + "\n")

        repo = tmp_path / "gitrepo"
        repo.mkdir()
        _init_real_git_repo(repo)
        actual_head = _commit_bundle(bundle, repo)

        attestation = GitHubRetainingCommitAttestation(
            repository="nhatnguyenquang1838-coder/DW-SuperApps",
            ref="evidence/RP-CERT-001",
            commit_sha=actual_head,
            path="evidence/RP-CERT-001",
        )
        with pytest.raises(CertificationEvidenceError, match="SHA256 mismatch|manifest digest mismatch"):
            fresh_verify_campaign(bundle, "RP-CERT-001", attestation, git_repo_root=repo)
