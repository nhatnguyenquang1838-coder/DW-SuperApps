"""Lightweight durable live-certification harness (M5).

Records stable Test Cases separately from per-execution Test Runs.  Keeps
every PASS/FAIL branch/PR as reproducible evidence — certification branches
are NEVER deleted.  Verdicts are immutable once recorded.  The run registry
is persisted to a JSONL store so certification evidence survives process
restart (M5 durability).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
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
    runtime_plan_digest: str = ""
    mode: str = RunMode.STANDARD_REAL_RUN
    verdict: str = TestRunVerdict.PENDING
    evidence: dict[str, Any] = field(default_factory=dict)
    expected: str = ""
    actual: str = ""
    branch_deleted: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Durable JSON projection (M5: restart reconstruct)."""
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "scenario": self.scenario,
            "acceptance": self.acceptance,
            "branch": self.branch,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "executor": self.executor,
            "model": self.model,
            "pr_id": self.pr_id,
            "runtime_plan_ref": self.runtime_plan_ref,
            "runtime_plan_digest": self.runtime_plan_digest,
            "mode": self.mode,
            "verdict": self.verdict,
            "evidence": dict(self.evidence),
            "expected": self.expected,
            "actual": self.actual,
            "branch_deleted": self.branch_deleted,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TestRun":
        return cls(
            run_id=payload["run_id"],
            case_id=payload["case_id"],
            scenario=payload["scenario"],
            acceptance=payload["acceptance"],
            branch=payload["branch"],
            base_sha=payload["base_sha"],
            head_sha=payload["head_sha"],
            executor=payload["executor"],
            model=payload["model"],
            pr_id=payload.get("pr_id", ""),
            runtime_plan_ref=payload.get("runtime_plan_ref", ""),
            runtime_plan_digest=payload.get("runtime_plan_digest", ""),
            mode=payload.get("mode", RunMode.STANDARD_REAL_RUN),
            verdict=payload.get("verdict", TestRunVerdict.PENDING),
            evidence=dict(payload.get("evidence", {})),
            expected=payload.get("expected", ""),
            actual=payload.get("actual", ""),
            branch_deleted=bool(payload.get("branch_deleted", False)),
        )


class LiveCertificationHarness:
    """Durable live-certification harness.

    Records stable Test Cases separately from per-execution Test Runs.
    Keeps every PASS/FAIL branch/PR as reproducible evidence.  Verdicts are
    immutable once recorded.  Optionally persists the registry to a JSONL
    store so evidence survives process restart.
    """

    def __init__(self, store: str | Path | None = None) -> None:
        self._runs: dict[str, TestRun] = {}
        self._branches: dict[str, str] = {}  # branch -> run_id
        self._store = Path(store) if store else None
        if self._store is not None:
            self._load()

    def _load(self) -> None:
        """Reconstruct the registry from the durable JSONL store (M5)."""
        if self._store is None or not self._store.exists():
            return
        for line in self._store.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = TestRun.from_dict(json.loads(line))
            self._runs[record.run_id] = record
            self._branches[record.branch] = record.run_id

    def _append(self, run: TestRun) -> None:
        """Append one immutable record to the durable store (M5)."""
        if self._store is None:
            return
        self._store.parent.mkdir(parents=True, exist_ok=True)
        with self._store.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(run.to_dict(), sort_keys=True) + "\n")

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
        runtime_plan_digest: str = "",
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
            runtime_plan_digest=runtime_plan_digest,
            mode=mode,
        )
        self._runs[run_id] = run
        self._branches[branch] = run_id
        self._append(run)
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
        """Record PASS/FAIL verdict with exact refs/evidence — immutable once recorded."""
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

        # M5: immutable once recorded — a verdict must never be overwritten.
        if run.verdict != TestRunVerdict.PENDING:
            raise LiveCertificationError(
                f"verdict for run {run_id!r} is immutable (already recorded: {run.verdict})"
            )

        run.verdict = verdict
        run.evidence = dict(evidence)
        run.expected = expected
        run.actual = actual
        self._append(run)

    def get_run(self, run_id: str) -> TestRun:
        """Get a test run by ID."""
        run = self._runs.get(run_id)
        if run is None:
            raise LiveCertificationError(f"run {run_id!r} not found")
        return run

    def delete_branch(self, *, run_id: str) -> None:
        """Branch deletion/cleanup: REJECTED for every certification run.

        M5: certification branches for PASS, FAIL and PENDING runs are all
        retained as reproducible evidence — the "never delete PASS/FAIL
        certification branches" invariant holds for every verdict.
        """
        run = self._runs.get(run_id)
        if run is None:
            raise LiveCertificationError(f"run {run_id!r} not found")

        # Branch and PR retained for PASS, FAIL and PENDING.
        raise LiveCertificationError(
            f"branch {run.branch!r} retained for certification run {run_id} (verdict {run.verdict})"
        )

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
