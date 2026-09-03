from __future__ import annotations

import pytest

from taskcontroller.runtime.live_certification_harness import (
    LiveCertificationError,
    LiveCertificationHarness,
    TestCase,
    TestRun,
    TestRunVerdict,
    RunMode,
)


def _case(*, case_id: str = "TC-RP-001", scenario: str = "standard_real_run", acceptance: str = "login works") -> TestCase:
    return TestCase(case_id=case_id, scenario=scenario, acceptance=acceptance)


def test_rejects_run_without_case_identity():
    """Run without case identity must be rejected."""
    harness = LiveCertificationHarness()
    with pytest.raises(LiveCertificationError, match="case"):
        harness.start_run(
            case=None,
            branch="feature/test",
            base_sha="0" * 40,
            head_sha="1" * 40,
            executor="Hermes",
            model="gpt",
        )


def test_rejects_verdict_without_exact_refs():
    """PASS/FAIL verdict without exact refs/evidence must be rejected."""
    harness = LiveCertificationHarness()
    case = _case()
    run = harness.start_run(
        case=case,
        branch="feature/test",
        base_sha="0" * 40,
        head_sha="1" * 40,
        executor="Hermes",
        model="gpt",
    )
    with pytest.raises(LiveCertificationError, match="evidence"):
        harness.record_verdict(run_id=run.run_id, verdict="PASS", evidence={})


def test_rejects_reused_branch_identity():
    """Reused branch identity for a new run must be rejected."""
    harness = LiveCertificationHarness()
    case = _case()
    run1 = harness.start_run(
        case=case,
        branch="feature/test",
        base_sha="0" * 40,
        head_sha="1" * 40,
        executor="Hermes",
        model="gpt",
    )
    harness.record_verdict(run_id=run1.run_id, verdict="PASS", evidence={"ci": "pass"})
    with pytest.raises(LiveCertificationError, match="branch"):
        harness.start_run(
            case=case,
            branch="feature/test",
            base_sha="0" * 40,
            head_sha="2" * 40,
            executor="Hermes",
            model="gpt",
        )


def test_rejects_missing_executor_identity():
    """Missing executor/model identity must be rejected."""
    harness = LiveCertificationHarness()
    case = _case()
    with pytest.raises(LiveCertificationError, match="executor"):
        harness.start_run(
            case=case,
            branch="feature/test",
            base_sha="0" * 40,
            head_sha="1" * 40,
            executor="",
            model="gpt",
        )


def test_rejects_branch_deletion_for_passed_run():
    """Branch deletion/cleanup for passed run must be rejected."""
    harness = LiveCertificationHarness()
    case = _case()
    run = harness.start_run(
        case=case,
        branch="feature/test",
        base_sha="0" * 40,
        head_sha="1" * 40,
        executor="Hermes",
        model="gpt",
    )
    harness.record_verdict(run_id=run.run_id, verdict="PASS", evidence={"ci": "pass"})
    with pytest.raises(LiveCertificationError, match="retained"):
        harness.delete_branch(run_id=run.run_id)


def test_rejects_notion_slash_as_machine_truth():
    """Notion/Slack data being treated as machine truth must be rejected."""
    harness = LiveCertificationHarness()
    case = _case()
    run = harness.start_run(
        case=case,
        branch="feature/test",
        base_sha="0" * 40,
        head_sha="1" * 40,
        executor="Hermes",
        model="gpt",
    )
    with pytest.raises(LiveCertificationError, match="machine truth"):
        harness.record_verdict(
            run_id=run.run_id,
            verdict="PASS",
            evidence={"ci": "pass"},
            notion_data={"status": "approved"},
        )


def test_fresh_branch_per_live_run():
    """Fresh branch per live run must be enforced."""
    harness = LiveCertificationHarness()
    case = _case()
    run1 = harness.start_run(
        case=case,
        branch="feature/test-1",
        base_sha="0" * 40,
        head_sha="1" * 40,
        executor="Hermes",
        model="gpt",
    )
    run2 = harness.start_run(
        case=case,
        branch="feature/test-2",
        base_sha="0" * 40,
        head_sha="2" * 40,
        executor="Hermes",
        model="gpt",
    )
    assert run1.run_id != run2.run_id
    assert run1.branch != run2.branch


def test_branch_and_pr_retained_for_pass_and_fail():
    """Branch and PR retained for PASS and FAIL."""
    harness = LiveCertificationHarness()
    case = _case()
    run_pass = harness.start_run(
        case=case,
        branch="feature/pass",
        base_sha="0" * 40,
        head_sha="1" * 40,
        executor="Hermes",
        model="gpt",
    )
    harness.record_verdict(run_id=run_pass.run_id, verdict="PASS", evidence={"ci": "pass"})
    run_fail = harness.start_run(
        case=case,
        branch="feature/fail",
        base_sha="0" * 40,
        head_sha="2" * 40,
        executor="Hermes",
        model="gpt",
    )
    harness.record_verdict(run_id=run_fail.run_id, verdict="FAIL", evidence={"ci": "fail"})
    stored_pass = harness.get_run(run_pass.run_id)
    stored_fail = harness.get_run(run_fail.run_id)
    assert stored_pass.verdict == TestRunVerdict.PASS
    assert stored_fail.verdict == TestRunVerdict.FAIL
    assert stored_pass.branch == "feature/pass"
    assert stored_fail.branch == "feature/fail"


def test_testrun_records_exact_pointers():
    """TestRun records exact expected/actual/verdict pointers."""
    harness = LiveCertificationHarness()
    case = _case()
    run = harness.start_run(
        case=case,
        branch="feature/test",
        base_sha="0" * 40,
        head_sha="1" * 40,
        executor="Hermes",
        model="gpt",
        pr_id="PR-123",
        runtime_plan_ref="plan.test/r1",
    )
    harness.record_verdict(
        run_id=run.run_id,
        verdict="PASS",
        evidence={"ci": "pass", "sha": "abc123"},
        expected="login succeeds",
        actual="login succeeds",
    )
    stored = harness.get_run(run.run_id)
    assert stored.case_id == "TC-RP-001"
    assert stored.base_sha == "0" * 40
    assert stored.head_sha == "1" * 40
    assert stored.branch == "feature/test"
    assert stored.pr_id == "PR-123"
    assert stored.runtime_plan_ref == "plan.test/r1"
    assert stored.executor == "Hermes"
    assert stored.model == "gpt"
    assert stored.verdict == TestRunVerdict.PASS
    assert stored.evidence["ci"] == "pass"
    assert stored.expected == "login succeeds"
    assert stored.actual == "login succeeds"


def test_no_scan_of_historical_branches():
    """No scan of historical branches is required to determine current machine state."""
    harness = LiveCertificationHarness()
    case = _case()
    run = harness.start_run(
        case=case,
        branch="feature/test",
        base_sha="0" * 40,
        head_sha="1" * 40,
        executor="Hermes",
        model="gpt",
    )
    harness.record_verdict(run_id=run.run_id, verdict="PASS", evidence={"ci": "pass"})
    # Current state is determined by run_id, not branch scan
    current = harness.get_current_state(run_id=run.run_id)
    assert current["run_id"] == run.run_id
    assert current["verdict"] == "PASS"


def test_standard_real_run_and_deep_certification_are_separate_modes():
    """Standard Real Run and Deep Certification are separate modes."""
    harness = LiveCertificationHarness()
    case = _case()
    run_standard = harness.start_run(
        case=case,
        branch="feature/standard",
        base_sha="0" * 40,
        head_sha="1" * 40,
        executor="Hermes",
        model="gpt",
        mode=RunMode.STANDARD_REAL_RUN,
    )
    run_deep = harness.start_run(
        case=case,
        branch="feature/deep",
        base_sha="0" * 40,
        head_sha="2" * 40,
        executor="Hermes",
        model="gpt",
        mode=RunMode.DEEP_CERTIFICATION,
    )
    stored_standard = harness.get_run(run_standard.run_id)
    stored_deep = harness.get_run(run_deep.run_id)
    assert stored_standard.mode == RunMode.STANDARD_REAL_RUN
    assert stored_deep.mode == RunMode.DEEP_CERTIFICATION
