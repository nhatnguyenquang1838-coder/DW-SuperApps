from __future__ import annotations

import hashlib
import subprocess

import pytest

from taskcontroller.runtime.certification_models import (
    CertificationCampaign,
    SourceRevision,
    TestCase,
)
from taskcontroller.runtime.live_certification_harness import LiveCertificationError, LiveCertificationHarness
from taskcontroller.runtime.proving_workspace import ExactCheckout


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


def _git_repo(path, remote, content):
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    (path / "tracked.txt").write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "initial"], check=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def _campaign(gwc_sha=SHA_C):
    return CertificationCampaign(
        campaign_id="RP-CERT-001",
        mode="STANDARD_REAL_RUN",
        runtime_branch="runtime-lab/RP-CERT-001",
        proving_branch="prove/RP-CERT-001/TC-RP-001",
        test_case_id="TC-RP-001",
        test_case_revision="2026-09-02-r1",
        baseline_runtime_sha=SHA_A,
        baseline_subject_sha=SHA_B,
        gwc_sha=gwc_sha,
        status="ACTIVE",
    )


def _execution(harness_sha: str) -> object:
    from taskcontroller.runtime.certification_models import ExecutionReceipt
    return ExecutionReceipt(
        execution_id="exec-w7-" + harness_sha[:8],
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
        harness_sha=harness_sha,
        harness_is_runtime=True,
        execution_receipt_digest="sha256:" + hashlib.sha256(harness_sha.encode()).hexdigest(),
    )


def test_start_run_verifies_all_exact_checkouts_before_persisting(tmp_path):
    remote = "git@github.com:nhatnguyenquang1838-coder/DW-SuperApps.git"
    gwc_remote = "git@github.com:nhatnguyenquang1838-coder/gwc.git"
    runtime_root = tmp_path / "runtime"
    subject_root = tmp_path / "subject"
    gwc_root = tmp_path / "gwc"
    runtime_sha = _git_repo(runtime_root, remote, "runtime")
    subject_sha = _git_repo(subject_root, remote, "subject")
    gwc_sha = _git_repo(gwc_root, gwc_remote, "gwc")

    harness = LiveCertificationHarness()
    harness.create_campaign(_campaign(gwc_sha))
    harness.register_case(TestCase("TC-RP-001", "2026-09-02-r1", "runtime", "pass", ("taskcontroller",)))
    run = harness.start_run(
        campaign_id="RP-CERT-001",
        case_id="TC-RP-001",
        runtime=SourceRevision("DW", "runtime-lab/RP-CERT-001", runtime_sha, runtime_sha),
        subject=SourceRevision("DW", "prove/RP-CERT-001/TC-RP-001", subject_sha, subject_sha),
        gwc_sha=gwc_sha,
        executor="Hermes-Mac",
        model="model-a",
        runtime_plan_ref="plan://r1",
        runtime_plan_revision="r1",
        runtime_plan_digest="sha256:" + "d" * 64,
        runtime_checkout=ExactCheckout("nhatnguyenquang1838-coder/DW-SuperApps", "runtime-lab/RP-CERT-001", runtime_sha, runtime_root),
        subject_checkout=ExactCheckout("nhatnguyenquang1838-coder/DW-SuperApps", "prove/RP-CERT-001/TC-RP-001", subject_sha, subject_root),
        gwc_checkout=ExactCheckout("nhatnguyenquang1838-coder/gwc", "correction", gwc_sha, gwc_root),
        canonical_runtime_remote=remote,
        canonical_subject_remote=remote,
        canonical_gwc_remote=gwc_remote,
        execution=_execution(runtime_sha),
    )
    assert run.runtime.end_sha == runtime_sha


def test_start_run_rejects_missing_or_mismatched_workspace_binding(tmp_path):
    remote = "git@github.com:nhatnguyenquang1838-coder/DW-SuperApps.git"
    runtime_root = tmp_path / "runtime"
    subject_root = tmp_path / "subject"
    runtime_sha = _git_repo(runtime_root, remote, "runtime")
    subject_sha = _git_repo(subject_root, remote, "subject")
    harness = LiveCertificationHarness()
    harness.create_campaign(_campaign())
    harness.register_case(TestCase("TC-RP-001", "2026-09-02-r1", "runtime", "pass", ("taskcontroller",)))
    with pytest.raises(LiveCertificationError, match="workspace binding"):
        harness.start_run(
            campaign_id="RP-CERT-001",
            case_id="TC-RP-001",
            runtime=SourceRevision("DW", "runtime-lab/RP-CERT-001", runtime_sha, runtime_sha),
            subject=SourceRevision("DW", "prove/RP-CERT-001/TC-RP-001", subject_sha, subject_sha),
            gwc_sha=SHA_C,
            executor="Hermes-Mac",
            model="model-a",
            runtime_plan_ref="plan://r1",
            runtime_plan_revision="r1",
            runtime_plan_digest="sha256:" + "d" * 64,
            runtime_checkout=ExactCheckout("DW", "runtime", runtime_sha, runtime_root),
            subject_checkout=ExactCheckout("DW", "subject", subject_sha, subject_root),
            execution=_execution(runtime_sha),
        )
