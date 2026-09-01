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


def _base_qualifies(run: TestRun) -> tuple[bool, str]:
    if run.verdict.upper() != "PASS":
        return False, "verdict"
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

    Replay-resistance: a run whose execution receipt duplicates one already
    inside the streak does not extend the streak (cloned evidence counts one
    or zero, never three).
    """
    if required_streak < 1:
        raise ValueError("required_streak must be positive")

    target_sha = expected_runtime_sha or (runs[-1].runtime.end_sha if runs else None)
    streak: list[TestRun] = []
    streak_receipts: set[str] = set()
    previous_identity: tuple[str, str, str, str, str] | None = None
    reset_reason = ""

    for run in runs:
        if target_sha is not None and run.runtime.end_sha != target_sha:
            streak = []
            streak_receipts = set()
            previous_identity = None
            reset_reason = "runtime SHA mismatch or stale run"
            continue
        qualifies, reason = _base_qualifies(run)
        if not qualifies:
            streak = []
            streak_receipts = set()
            previous_identity = None
            reset_reason = f"non-qualifying evidence: {reason}"
            continue
        identity = _runtime_identity(run)
        if previous_identity is not None and identity != previous_identity:
            streak = []
            streak_receipts = set()
            reset_reason = "runtime/source identity changed"
        if run.execution is None or run.execution.execution_receipt_digest in streak_receipts:
            # Cloned / synthetic execution receipt does not extend the streak.
            streak = []
            streak_receipts = set()
            previous_identity = None
            reset_reason = "cloned execution identity (receipt not independently distinct)"
            continue
        streak.append(run)
        streak_receipts.add(run.execution.execution_receipt_digest)
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
    if not recovery_seen and streak:
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
    required_ci_cycle_receipts: int = 0,
) -> DeepCaseStabilityResult:
    """Apply one W9 case's explicit repetition and diversity requirements."""
    if threshold < 1 or minimum_identities < 1:
        raise ValueError("threshold and minimum_identities must be positive")
    selected = [run for run in runs if run.case_id == case_id]
    qualifying: list[TestRun] = []
    last_reason = ""
    for run in selected:
        okay, reason = _base_qualifies(run)
        if not okay:
            last_reason = f"non-qualifying evidence: {reason}"
            continue
        if not _matrix_is_green(run, required_matrix_rows):
            last_reason = "injection matrix incomplete"
            continue
        qualifying.append(run)
    identity_count = len({(run.executor, run.model) for run in qualifying})
    # Replay-resistance: distinct execution receipts are mandatory; a stored
    # boolean such as ci_recovery=true is insufficient for case thresholds.
    receipt_digests = {
        run.execution.execution_receipt_digest
        for run in qualifying
        if run.execution is not None
    }
    execution_ids = {run.execution.execution_id for run in qualifying if run.execution is not None}
    cloned = len(receipt_digests) != len(qualifying) or len(execution_ids) != len(qualifying)
    if cloned:
        last_reason = "cloned execution identity in case receipts"
        qualifying = []
        receipt_digests = set()
        execution_ids = set()
    if required_ci_cycle_receipts > 0:
        ci_cycle_receipts = {
            receipt
            for run in qualifying
            if run.execution is not None
            for receipt in run.execution.ci_run_refs
        }
        if len(ci_cycle_receipts) < required_ci_cycle_receipts:
            last_reason = "insufficient live CI-cycle receipts"
    stable = (
        len(qualifying) >= threshold
        and identity_count >= minimum_identities
        and (
            required_ci_cycle_receipts == 0
            or (
                len(
                    {
                        receipt
                        for run in qualifying
                        if run.execution is not None
                        for receipt in run.execution.ci_run_refs
                    }
                )
                >= required_ci_cycle_receipts
            )
        )
    )
    if identity_count < minimum_identities:
        last_reason = "insufficient executor/model identities"
    if len(receipt_digests) < threshold and not cloned:
        last_reason = "insufficient distinct execution receipts"
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
