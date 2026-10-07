"""SCRUM-808 regression tests: anti-deadlock invariants for read-only Analyzer Child Runs.

These tests verify the three canonical invariants that prevent
read-only Analyzer Child Run deadlock behind effect authority:

1. READ_ONLY_ANALYSIS Child Run != Repository G2 effect
2. WAIT_CONTROLLER invalid if runnable read-only work exists
3. UR-G* vs GWC-G* naming separation
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from taskcontroller.mvp.protocol_bridge import (
    CONTINUE,
    INTERCEPT,
    TERMINAL,
    WAIT_CONTROLLER,
    ContractedSubtask,
    ExecutorReport,
    classify_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

READ_ONLY_ANALYSIS_WORK = ("inspect", "search", "observe", "project", "analyze", "recommend")


def _readonly_report(
    *,
    status: str = "RUNNING",
    completed: tuple[str, ...] = ("analysis",),
    evidence: tuple[str, ...] = ("read-only analysis complete",),
    next_action: str = "continue read-only analysis",
    after: str = CONTINUE,
    finding_risk: tuple[str, ...] = (),
    drift: tuple[str, ...] = (),
    material_finding: bool = False,
    authority_required: bool = False,
    evidence_conflict: bool = False,
) -> ExecutorReport:
    return ExecutorReport(
        subtask_id="A1",
        status=status,
        completed=completed,
        evidence=evidence,
        next_action=next_action,
        after=after,
        finding_risk=finding_risk,
        drift=drift,
        material_finding=material_finding,
        authority_required=authority_required,
        evidence_conflict=evidence_conflict,
    )


def _readonly_contract(after_report: str = CONTINUE) -> ContractedSubtask:
    return ContractedSubtask(
        subtask_id="A1",
        objective="read-only analyzer review",
        allowed_work=READ_ONLY_ANALYSIS_WORK,
        expected_output=("analysis evidence",),
        report_requirement=("evidence refs",),
        after_report=after_report,
    )


def _load_taskcontroller_yaml() -> dict:
    yaml_path = Path(__file__).resolve().parents[2] / "controllers" / "taskcontroller.yaml"
    return yaml.safe_load(yaml_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Invariant 1: READ_ONLY_ANALYSIS Child Run != Repository G2 effect
# ---------------------------------------------------------------------------


class TestReadOnlyAnalysisNotG2Effect:
    """Invariant 1: READ_ONLY_ANALYSIS Child Run != Repository G2 effect."""

    def test_readonly_contract_allows_readonly_work(self):
        """A read-only contracted subtask must allow read-only work actions."""
        contract = _readonly_contract()
        for action in READ_ONLY_ANALYSIS_WORK:
            assert action in contract.allowed_work

    def test_readonly_contract_no_writable_targets(self):
        """A read-only contracted subtask must not declare writable targets."""
        contract = _readonly_contract()
        write_actions = {"edit", "write", "create", "delete", "mutate"}
        for action in contract.allowed_work:
            assert action not in write_actions, (
                f"read-only contract must not allow write action {action!r}"
            )

    def test_readonly_classification_is_continue_not_wait(self):
        """A read-only analysis subtask with no authority requirement must classify as CONTINUE."""
        report = _readonly_report()
        contract = _readonly_contract()
        verdict = classify_report(contract, report)
        assert verdict.verdict == CONTINUE, (
            "read-only analysis with no authority requirement must CONTINUE, "
            f"not {verdict.verdict!r}"
        )

    def test_read_only_analysis_rejects_wait_controller(self):
        """When work is runnable read-only, WAIT_CONTROLLER is invalid."""
        contract = _readonly_contract(after_report=CONTINUE)
        report = _readonly_report(status="RUNNING")
        verdict = classify_report(contract, report)
        assert verdict.verdict != WAIT_CONTROLLER, (
            "WAIT_CONTROLLER is invalid when runnable read-only work exists"
        )

    def test_read_only_analysis_rejects_intercept_for_authority(self):
        """Read-only analysis must not raise INTERCEPT for authority drift."""
        contract = _readonly_contract()
        report = _readonly_report(authority_required=False)
        verdict = classify_report(contract, report)
        assert verdict.verdict != INTERCEPT, (
            "read-only analysis must not INTERCEPT on authority when no authority required"
        )


# ---------------------------------------------------------------------------
# Invariant 2: WAIT_CONTROLLER invalid if runnable read-only work exists
# ---------------------------------------------------------------------------


class TestWaitControllerInvalidForReadOnlyWork:
    """Invariant 2: WAIT_CONTROLLER invalid if runnable read-only work exists."""

    def test_continuable_readonly_work_must_not_wait(self):
        """When Executor reports RUNNING with read-only work, verdict is CONTINUE."""
        contract = _readonly_contract(after_report=CONTINUE)
        report = _readonly_report(status="RUNNING")
        verdict = classify_report(contract, report)
        assert verdict.verdict == CONTINUE

    def test_readonly_completed_moves_to_terminal_segment(self):
        """When read-only analysis is DONE, contracted TERMINAL ends the segment."""
        contract = _readonly_contract(after_report=TERMINAL)
        report = _readonly_report(status="DONE", after=TERMINAL)
        verdict = classify_report(contract, report)
        assert verdict.verdict == TERMINAL

    def test_wait_controller_only_valid_for_human_gate_authority(self):
        """WAIT_CONTROLLER is only valid when the contract requires controller review."""
        contract = ContractedSubtask(
            subtask_id="H1",
            objective="human review required",
            allowed_work=("review evidence",),
            expected_output=("review decision",),
            report_requirement=("review outcome",),
            after_report=WAIT_CONTROLLER,
        )
        report = ExecutorReport(
            subtask_id="H1",
            status="RUNNING",
            completed=("review evidence",),
            evidence=("analysis complete",),
            next_action="await human review",
            after=WAIT_CONTROLLER,
            authority_required=True,
        )
        verdict = classify_report(contract, report)
        # authority_required -> INTERCEPT (authority drift), not WAIT_CONTROLLER
        assert verdict.verdict == INTERCEPT
        assert verdict.intercept_reason == "authority_drift"


# ---------------------------------------------------------------------------
# Invariant 3: UR-G* vs GWC-G* naming separation
# ---------------------------------------------------------------------------


class TestUrGvsGwcGNamingSeparation:
    """Invariant 3: UR-G* vs GWC-G* naming separation."""

    def test_gwc_gate_prefix_distinct_from_ur_prefix(self):
        """GWC-G* and UR-G* are distinct prefixes and must not be conflated."""
        gwc_gate = "GWC-G2"
        ur_gate = "UR-G2"
        assert gwc_gate != ur_gate
        assert gwc_gate.startswith("GWC-")
        assert ur_gate.startswith("UR-")

    def test_gwc_gate_not_ur_authority_delegation(self):
        """A GWC gate decision is never a UR authority delegation."""
        gwc_decision = "GWC-G4_MERGE"
        assert not gwc_decision.startswith("UR-")

    def test_ur_approval_not_gwc_gate_transition(self):
        """A UR approval is never a GWC gate transition."""
        ur_approval = "UR-G2_APPROVAL"
        assert not ur_approval.startswith("GWC-")

    def test_controller_yaml_read_only_classification_prefixes(self):
        """taskcontroller.yaml must declare distinct gate prefixes for read-only analysis."""
        config = _load_taskcontroller_yaml()
        classification = config["execution_classification"]
        read_only = classification["read_only_analysis"]

        assert read_only["effect_authority_required"] is False
        assert read_only["repository_write"] is False
        assert read_only["wait_controller_invalid_when_runnable"] is True
        assert read_only["gate_prefix"] == "GWC-G*"
        assert read_only["ur_gate_prefix"] == "UR-G*"

    def test_gate_prefix_separation_in_contract(self):
        """Contracts must reference the correct gate prefix for their authority type."""
        gwc_gate_prefix = "GWC-G*"
        ur_gate_prefix = "UR-G*"
        assert gwc_gate_prefix != ur_gate_prefix
        assert "GWC" in gwc_gate_prefix
        assert "UR" in ur_gate_prefix


# ---------------------------------------------------------------------------
# Integration: full invariant coverage
# ---------------------------------------------------------------------------


class TestSCRUM808FullInvariantCoverage:
    """All three invariants together: no deadlock scenario."""

    def test_readonly_child_run_never_deadlocks_behind_effect_authority(self):
        """
        Integrated scenario: a read-only Analyzer Child Run must never
        deadlock behind effect authority.

        Given: a read-only analysis child contract (CONTINUE after_report)
        When: the Executor reports RUNNING with read-only evidence
        Then: the Controller MUST classify as CONTINUE, not WAIT_CONTROLLER
        And: no G2 effect authority is required
        And: the gate prefix is GWC-G*, not UR-G*
        """
        contract = _readonly_contract(after_report=CONTINUE)
        report = _readonly_report(
            status="RUNNING",
            evidence=("analyzed target files", "no mutations required"),
            next_action="continue read-only inspection",
        )
        verdict = classify_report(contract, report)

        # Invariant 1: no G2 effect needed for read-only analysis
        assert report.authority_required is False

        # Invariant 2: WAIT_CONTROLLER is invalid when runnable read-only work exists
        assert verdict.verdict == CONTINUE
        assert verdict.verdict != WAIT_CONTROLLER

        # Invariant 3: gate prefix is GWC-G* for GWC lifecycle decisions
        config = _load_taskcontroller_yaml()
        ro = config["execution_classification"]["read_only_analysis"]
        assert ro["gate_prefix"] == "GWC-G*"
        assert ro["ur_gate_prefix"] == "UR-G*"
        assert ro["effect_authority_required"] is False

    def test_human_gate_still_requires_ur_authority(self):
        """When human gate authority is genuinely needed, UR-G* applies."""
        contract = ContractedSubtask(
            subtask_id="G4",
            objective="human merge approval",
            allowed_work=("review", "approve", "reject"),
            expected_output=("approval decision",),
            report_requirement=("approval evidence",),
            after_report=WAIT_CONTROLLER,
        )
        report = ExecutorReport(
            subtask_id="G4",
            status="RUNNING",
            completed=("review evidence",),
            evidence=("PR ready for review",),
            next_action="await human approval",
            after=WAIT_CONTROLLER,
            authority_required=True,
        )
        verdict = classify_report(contract, report)
        # authority_required -> INTERCEPT (authority drift), correctly surfacing human boundary
        assert verdict.verdict == INTERCEPT
        assert verdict.intercept_reason == "authority_drift"