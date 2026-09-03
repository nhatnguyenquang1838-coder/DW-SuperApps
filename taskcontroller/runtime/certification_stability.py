"""Deterministic W8/W9 stability predicates over immutable TestRun evidence."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .certification_models import RuntimeFinding, TestRun


_GREEN_CI = frozenset({"PASS", "SUCCESS", "GREEN", "OK"})


@dataclass(frozen=True)
class W8StabilityResult:
    stable: bool
    clean_streak: int
    qualifying_run_ids: tuple[str, ...]
    reset_reason: str = ""


@dataclass(frozen=True)
class DeepCaseStabilityResult:
    case_id: str
    stable: bool
    qualifying_count: int
    qualifying_run_ids: tuple[str, ...]
    reset_reason: str = ""


def _truthy_negative(evidence: object, keys: Iterable[str]) -> str | None:
    if not isinstance(evidence, Mapping):
        return None
    for key in keys:
        if evidence.get(key) is True:
            return key
    return None


def _ci_is_green(evidence: object) -> bool:
    if not isinstance(evidence, Mapping):
        return False
    ci = evidence.get("ci")
    if not isinstance(ci, Mapping):
        return False
    return str(ci.get("status", "")).upper() in _GREEN_CI


def _execution_identity(run: TestRun) -> tuple[str, str] | None:
    """Return the first-class physical execution identity for one TestRun."""
    receipt = run.execution_receipt
    if receipt is None:
        return None
    return receipt.execution_id, receipt.execution_receipt_digest


def _base_qualifies(run: TestRun) -> tuple[bool, str]:
    if run.verdict.upper() != "PASS":
        return False, "verdict"
    if _execution_identity(run) is None:
        return False, "execution receipt missing"
    if not _ci_is_green(run.evidence):
        return False, "ci"
    negative = _truthy_negative(
        run.evidence,
        (
            "plan_bypass",
            "unauthorized_effect",
            "stale_sequence_accepted",
            "authority_bypass",
            "human_plane_machine_truth_mismatch",
        ),
    )
    if negative:
        return False, negative
    return True, ""


def _runtime_identity(run: TestRun) -> tuple[str, str, str, str, str]:
    return (
        run.case_revision,
        run.runtime.end_sha,
        run.subject.end_sha,
        run.gwc_sha,
        run.runtime_plan_digest,
    )


def evaluate_w8_stability(
    runs: Sequence[TestRun],
    findings: Sequence[RuntimeFinding],
    *,
    expected_runtime_sha: str | None = None,
    required_streak: int = 3,
) -> W8StabilityResult:
    """Evaluate the final consecutive W8 streak without mutating the runs.

    SourceIdentity may repeat across qualifying runs, but every counted run must
    carry a distinct ExecutionIdentity. Replaying the same execution_id or the
    same execution_receipt_digest anywhere in the evaluated campaign history
    invalidates that occurrence; streak resets never erase replay history.
    """
    if required_streak < 1:
        raise ValueError("required_streak must be positive")

    target_sha = expected_runtime_sha or (runs[-1].runtime.end_sha if runs else None)
    streak: list[TestRun] = []
    previous_identity: tuple[str, str, str, str, str] | None = None
    observed_execution_ids: set[str] = set()
    observed_receipt_digests: set[str] = set()
    reset_reason = ""

    for run in runs:
        execution_identity = _execution_identity(run)
        if execution_identity is not None:
            execution_id, receipt_digest = execution_identity
            if execution_id in observed_execution_ids or receipt_digest in observed_receipt_digests:
                streak = []
                previous_identity = None
                reset_reason = "execution receipt replay or duplicate ExecutionIdentity"
                continue
            observed_execution_ids.add(execution_id)
            observed_receipt_digests.add(receipt_digest)

        if target_sha is not None and run.runtime.end_sha != target_sha:
            streak = []
            previous_identity = None
            reset_reason = "runtime SHA mismatch or stale run"
            continue
        qualifies, reason = _base_qualifies(run)
        if not qualifies:
            streak = []
            previous_identity = None
            reset_reason = f"non-qualifying evidence: {reason}"
            continue
        identity = _runtime_identity(run)
        if previous_identity is not None and identity != previous_identity:
            streak = []
            reset_reason = "runtime/source identity changed"
        streak.append(run)
        previous_identity = identity

    unresolved = [
        finding
        for finding in findings
        if finding.severity.upper() in {"P0", "P1"}
        and finding.status.upper() != "RESOLVED"
    ]
    recovery_seen = any(
        isinstance(run.evidence, Mapping)
        and run.evidence.get("fresh_controller_recovery") is True
        for run in streak
    )
    stable = len(streak) >= required_streak and recovery_seen and not unresolved
    if not recovery_seen and streak and not reset_reason:
        reset_reason = "durable recovery evidence missing"
    if unresolved:
        reset_reason = "unresolved P0/P1 finding"
    if stable:
        reset_reason = ""
    return W8StabilityResult(
        stable=stable,
        clean_streak=len(streak),
        qualifying_run_ids=tuple(run.run_id for run in streak),
        reset_reason=reset_reason,
    )


def _matrix_is_green(run: TestRun, required_rows: Sequence[str]) -> bool:
    if not required_rows:
        return True
    evidence = run.evidence
    if not isinstance(evidence, Mapping):
        return False
    matrix = evidence.get("injection_matrix")
    if not isinstance(matrix, Mapping):
        return False
    return all(str(matrix.get(row, "")).upper() in _GREEN_CI for row in required_rows)


def evaluate_deep_case_stability(
    case_id: str,
    runs: Sequence[TestRun],
    *,
    threshold: int,
    minimum_identities: int = 1,
    required_matrix_rows: Sequence[str] = (),
) -> DeepCaseStabilityResult:
    """Apply one W9 case's explicit repetition and diversity requirements."""
    if threshold < 1 or minimum_identities < 1:
        raise ValueError("threshold and minimum_identities must be positive")
    selected = [run for run in runs if run.case_id == case_id]
    qualifying: list[TestRun] = []
    seen_execution_ids: set[str] = set()
    seen_receipt_digests: set[str] = set()
    last_reason = ""
    for run in selected:
        okay, reason = _base_qualifies(run)
        if not okay:
            last_reason = f"non-qualifying evidence: {reason}"
            continue
        execution_identity = _execution_identity(run)
        assert execution_identity is not None
        execution_id, receipt_digest = execution_identity
        if execution_id in seen_execution_ids or receipt_digest in seen_receipt_digests:
            last_reason = "execution receipt replay or duplicate ExecutionIdentity"
            continue
        if not _matrix_is_green(run, required_matrix_rows):
            last_reason = "injection matrix incomplete"
            continue
        qualifying.append(run)
        seen_execution_ids.add(execution_id)
        seen_receipt_digests.add(receipt_digest)
    identity_count = len({(run.executor, run.model) for run in qualifying})
    stable = len(qualifying) >= threshold and identity_count >= minimum_identities
    if identity_count < minimum_identities:
        last_reason = "insufficient executor/model identities"
    if stable:
        last_reason = ""
    return DeepCaseStabilityResult(
        case_id=case_id,
        stable=stable,
        qualifying_count=len(qualifying),
        qualifying_run_ids=tuple(run.run_id for run in qualifying),
        reset_reason=last_reason,
    )


def evaluate_campaign_certified(
    w8: W8StabilityResult,
    deep_cases: Sequence[DeepCaseStabilityResult],
    findings: Sequence[RuntimeFinding],
) -> bool:
    unresolved = any(
        finding.severity.upper() in {"P0", "P1"}
        and finding.status.upper() != "RESOLVED"
        for finding in findings
    )
    return w8.stable and bool(deep_cases) and all(case.stable for case in deep_cases) and not unresolved
