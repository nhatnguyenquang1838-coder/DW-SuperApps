from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping


class LiveCertificationError(Exception):
    """Raised when a live certification operation violates the contract."""


@dataclass
class TestCase:
    """Stable scenario/acceptance definition."""
    case_id: str
    scenario: str
    acceptance: str


@dataclass
class TestRunVerdict:
    """Verdict constants."""
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"


@dataclass
class RunMode:
    """Run mode constants."""
    STANDARD_REAL_RUN = "STANDARD_REAL_RUN"
    DEEP_CERTIFICATION = "DEEP_CERTIFICATION"


@dataclass
class TestRun:
    """One execution with base/head SHA, branch, PR, RuntimePlan identity, executor/model, CI evidence, actual result and verdict."""
    run_id: str
    case_id: str
    scenario: str
    acceptance: str
    branch: str
    base_sha: str
    head_sha: str
    executor: str
    model: str
    pr_id: str = ""
    runtime_plan_ref: str = ""
    mode: str = RunMode.STANDARD_REAL_RUN
    verdict: str = TestRunVerdict.PENDING
    evidence: dict[str, Any] = field(default_factory=dict)
    expected: str = ""
    actual: str = ""
    branch_deleted: bool = False


class LiveCertificationHarness:
    """Lightweight live-certification harness.

    Records stable Test Cases separately from per-execution Test Runs.
    Keeps every PASS/FAIL branch/PR as reproducible evidence.
    """

    def __init__(self) -> None:
        self._runs: dict[str, TestRun] = {}
        self._branches: dict[str, str] = {}  # branch -> run_id

    def start_run(
        self,
        *,
        case: TestCase | None,
        branch: str,
        base_sha: str,
        head_sha: str,
        executor: str,
        model: str,
        pr_id: str = "",
        runtime_plan_ref: str = "",
        mode: str = RunMode.STANDARD_REAL_RUN,
    ) -> TestRun:
        """Start a new test run. Requires case identity and fresh branch."""
        # 1. Reject run without case identity.
        if case is None:
            raise LiveCertificationError("case identity required")

        # 2. Reject missing executor/model identity.
        if not executor:
            raise LiveCertificationError("executor identity required")
        if not model:
            raise LiveCertificationError("model identity required")

        # 3. Reject reused branch identity for a new run.
        if branch in self._branches:
            raise LiveCertificationError(f"branch {branch!r} already used by run {self._branches[branch]}")

        run_id = f"run-{uuid.uuid4().hex[:8]}"
        run = TestRun(
            run_id=run_id,
            case_id=case.case_id,
            scenario=case.scenario,
            acceptance=case.acceptance,
            branch=branch,
            base_sha=base_sha,
            head_sha=head_sha,
            executor=executor,
            model=model,
            pr_id=pr_id,
            runtime_plan_ref=runtime_plan_ref,
            mode=mode,
        )
        self._runs[run_id] = run
        self._branches[branch] = run_id
        return run

    def record_verdict(
        self,
        *,
        run_id: str,
        verdict: str,
        evidence: dict[str, Any],
        expected: str = "",
        actual: str = "",
        notion_data: dict[str, Any] | None = None,
    ) -> None:
        """Record PASS/FAIL verdict with exact refs/evidence."""
        # 4. Reject Notion/Slack data being treated as machine truth.
        if notion_data is not None:
            raise LiveCertificationError(
                "Notion/Slack data must not be treated as machine truth"
            )

        run = self._runs.get(run_id)
        if run is None:
            raise LiveCertificationError(f"run {run_id!r} not found")

        # 5. Reject verdict without exact refs/evidence.
        if not evidence:
            raise LiveCertificationError("verdict requires exact refs/evidence")

        run.verdict = verdict
        run.evidence = dict(evidence)
        run.expected = expected
        run.actual = actual

    def get_run(self, run_id: str) -> TestRun:
        """Get a test run by ID."""
        run = self._runs.get(run_id)
        if run is None:
            raise LiveCertificationError(f"run {run_id!r} not found")
        return run

    def delete_branch(self, *, run_id: str) -> None:
        """Branch deletion/cleanup behavior: reject for passed runs."""
        run = self._runs.get(run_id)
        if run is None:
            raise LiveCertificationError(f"run {run_id!r} not found")

        # Branch and PR retained for PASS and FAIL.
        if run.verdict == TestRunVerdict.PASS:
            raise LiveCertificationError(
                f"branch {run.branch!r} retained for PASS run {run_id}"
            )

        run.branch_deleted = True
        self._branches.pop(run.branch, None)

    def get_current_state(self, *, run_id: str) -> dict[str, Any]:
        """Get current machine state by run_id (no branch scan required)."""
        run = self._runs.get(run_id)
        if run is None:
            raise LiveCertificationError(f"run {run_id!r} not found")
        return {
            "run_id": run.run_id,
            "case_id": run.case_id,
            "verdict": run.verdict,
            "branch": run.branch,
            "head_sha": run.head_sha,
        }
