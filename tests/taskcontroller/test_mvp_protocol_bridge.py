"""Tests for the MVP protocol bridge (R4B contract proofs).

Each test maps to a numbered R4B requirement. The bridge must translate the
active current-main MVP protocol vocabulary without owning state, without a
second engine/schema, and without granting authority.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import inspect
from pathlib import Path

import pytest

from taskcontroller.domain.enums import NodeStatus, RunStatus
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.kernel.transitions import is_node_terminal
from taskcontroller.mvp import protocol_bridge as pb
from taskcontroller.mvp.protocol_bridge import (
    CONTINUE,
    INTERCEPT,
    PROTOCOL_VERDICTS,
    TERMINAL,
    WAIT_CONTROLLER,
    ContractedSubtask,
    ExecutorReport,
    InterceptReason,
    ProtocolVerdict,
    classify_report,
)

BRIDGE_SOURCE = Path(pb.__file__)


def _report(**overrides):
    base = dict(subtask_id="S1", status="RUNNING", after=CONTINUE)
    base.update(overrides)
    return ExecutorReport(**base)


# ---------------------------------------------------------------- 1
class TestExactLiterals:
    """R4B-1: exactly four output literals, no aliases."""

    def test_protocol_verdicts_are_exactly_four_literals(self):
        assert PROTOCOL_VERDICTS == (
            "CONTINUE",
            "WAIT_CONTROLLER",
            "TERMINAL",
            "INTERCEPT",
        )
        assert len(set(PROTOCOL_VERDICTS)) == 4

    def test_no_alias_or_case_variant_accepted(self):
        for bad in ("continue", "Continue", "WAIT", "wait_controller", "DONE",
                    "COMPLETE", "ESCALATE", "APPROVE", "MERGE", "TERMINATE", ""):
            with pytest.raises(TaskControllerValidationError):
                ProtocolVerdict(verdict=bad, detail="x", subtask_id="S1")

    def test_verdicts_disjoint_from_runtime_state_vocabulary(self):
        """R4B-5: verdicts are never RunStatus/NodeStatus members."""
        runtime_vocab = {m.value for m in RunStatus} | {m.value for m in NodeStatus}
        assert not (set(PROTOCOL_VERDICTS) & runtime_vocab)

    def test_every_verdict_emitted_is_in_the_four(self):
        cases = [
            (ContractedSubtask("S1", CONTINUE), _report()),
            (ContractedSubtask("S1", WAIT_CONTROLLER), _report(after=WAIT_CONTROLLER)),
            (ContractedSubtask("S1", TERMINAL), _report(after=TERMINAL)),
            (ContractedSubtask("S1", CONTINUE), _report(subtask_id="S9")),
            (ContractedSubtask("S1", CONTINUE), _report(status="BLOCKED")),
        ]
        for contracted, report in cases:
            assert classify_report(contracted, report).verdict in PROTOCOL_VERDICTS


# ---------------------------------------------------------------- 2
class TestNormalMilestone:
    """R4B-2: normal milestone -> contracted CONTINUE."""

    def test_normal_milestone_continues(self):
        v = classify_report(ContractedSubtask("S1", CONTINUE), _report())
        assert v.verdict == CONTINUE
        assert v.intercept_reason is None
        assert v.subtask_id == "S1"

    def test_done_status_at_continue_boundary_still_continues(self):
        v = classify_report(ContractedSubtask("S2", CONTINUE),
                            _report(subtask_id="S2", status="DONE"))
        assert v.verdict == CONTINUE


# ---------------------------------------------------------------- 3
class TestWaitController:
    """R4B-3: contracted wait -> WAIT_CONTROLLER, zero state mutation."""

    def test_contracted_wait_returns_wait_controller(self):
        v = classify_report(ContractedSubtask("S3", WAIT_CONTROLLER),
                            _report(subtask_id="S3", after=WAIT_CONTROLLER))
        assert v.verdict == WAIT_CONTROLLER
        assert v.runtime_mutated is False

    def test_wait_controller_is_not_a_runtime_status(self):
        assert WAIT_CONTROLLER not in {m.value for m in RunStatus}
        assert WAIT_CONTROLLER not in {m.value for m in NodeStatus}


# ---------------------------------------------------------------- 4
class TestTerminalIsNotDone:
    """R4B-4: terminal report -> TERMINAL as control-segment result, not runtime DONE."""

    def test_contracted_terminal_returns_terminal(self):
        v = classify_report(ContractedSubtask("S5", TERMINAL),
                            _report(subtask_id="S5", after=TERMINAL))
        assert v.verdict == TERMINAL
        assert "no DONE" in v.detail or "grants no" in v.detail

    def test_blocked_and_failed_end_segment_without_done(self):
        for status in ("BLOCKED", "FAILED"):
            v = classify_report(ContractedSubtask("S5", CONTINUE),
                                _report(subtask_id="S5", status=status))
            assert v.verdict == TERMINAL
            assert v.verdict != NodeStatus.DONE.value

    def test_terminal_verdict_is_not_done_and_done_stays_terminal_in_engine(self):
        assert TERMINAL != NodeStatus.DONE.value
        assert is_node_terminal(NodeStatus.DONE.value) is True

    def test_bridge_exposes_no_transition_capability(self):
        """R4B: DONE immutable — the bridge has no transition function at all."""
        names = {n for n, _ in inspect.getmembers(pb, callable)}
        for forbidden in ("transition", "advance", "apply", "commit", "mutate",
                          "set_status", "reopen", "assert_node_transition"):
            assert forbidden not in names


# ---------------------------------------------------------------- 5
class TestFiveInterceptConditions:
    """R4B-5: each of the 5 drift conditions -> INTERCEPT."""

    def test_only_five_intercept_reasons_exist(self):
        assert len(InterceptReason.ALL) == 5
        assert set(InterceptReason.ALL) == {
            "scope_drift", "authority_drift", "plan_drift",
            "evidence_conflict", "material_finding",
        }

    def test_scope_drift(self):
        v = classify_report(ContractedSubtask("S1", CONTINUE), _report(subtask_id="S7"))
        assert v.verdict == INTERCEPT
        assert v.intercept_reason == InterceptReason.SCOPE_DRIFT

    def test_authority_drift(self):
        v = classify_report(ContractedSubtask("S1", CONTINUE),
                            _report(authority_required=True))
        assert v.verdict == INTERCEPT
        assert v.intercept_reason == InterceptReason.AUTHORITY_DRIFT

    def test_plan_drift(self):
        v = classify_report(ContractedSubtask("S1", CONTINUE),
                            _report(after=TERMINAL))
        assert v.verdict == INTERCEPT
        assert v.intercept_reason == InterceptReason.PLAN_DRIFT

    def test_evidence_conflict(self):
        v = classify_report(ContractedSubtask("S1", CONTINUE),
                            _report(evidence_conflict=True))
        assert v.verdict == INTERCEPT
        assert v.intercept_reason == InterceptReason.EVIDENCE_CONFLICT

    def test_material_finding(self):
        v = classify_report(ContractedSubtask("S1", CONTINUE),
                            _report(material_finding=True))
        assert v.verdict == INTERCEPT
        assert v.intercept_reason == InterceptReason.MATERIAL_FINDING

    def test_explicit_drift_flags_intercept(self):
        v = classify_report(ContractedSubtask("S1", CONTINUE),
                            _report(drift=("plan invalidated",)))
        assert v.verdict == INTERCEPT
        assert "plan invalidated" in v.detail

    def test_intercept_requires_a_known_reason(self):
        with pytest.raises(TaskControllerValidationError):
            ProtocolVerdict(verdict=INTERCEPT, detail="x", subtask_id="S1")
        with pytest.raises(TaskControllerValidationError):
            ProtocolVerdict(verdict=INTERCEPT, detail="x", subtask_id="S1",
                            intercept_reason="made_up")

    def test_non_intercept_verdict_rejects_a_reason(self):
        with pytest.raises(TaskControllerValidationError):
            ProtocolVerdict(verdict=CONTINUE, detail="x", subtask_id="S1",
                            intercept_reason=InterceptReason.SCOPE_DRIFT)

    def test_scope_drift_takes_precedence_over_everything(self):
        v = classify_report(
            ContractedSubtask("S1", CONTINUE),
            _report(subtask_id="S9", status="BLOCKED", authority_required=True,
                    material_finding=True),
        )
        assert v.intercept_reason == InterceptReason.SCOPE_DRIFT


# ---------------------------------------------------------------- 6
class TestFailClosed:
    """R4B-6: mismatched subtask / after-report fail closed."""

    def test_mismatched_subtask_never_continues(self):
        v = classify_report(ContractedSubtask("S1", CONTINUE), _report(subtask_id="S2"))
        assert v.verdict != CONTINUE

    def test_mismatched_after_never_continues(self):
        v = classify_report(ContractedSubtask("S1", WAIT_CONTROLLER),
                            _report(after=CONTINUE))
        assert v.verdict != CONTINUE
        assert v.intercept_reason == InterceptReason.PLAN_DRIFT

    def test_invalid_after_value_rejected(self):
        for bad in ("INTERCEPT", "DONE", "COMPLETE", "wait", ""):
            with pytest.raises(TaskControllerValidationError):
                ExecutorReport(subtask_id="S1", status="RUNNING", after=bad)

    def test_intercept_is_not_a_plannable_boundary(self):
        with pytest.raises(TaskControllerValidationError):
            ContractedSubtask("S1", INTERCEPT)

    def test_invalid_status_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            ExecutorReport(subtask_id="S1", status="MAYBE", after=CONTINUE)

    def test_empty_subtask_id_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            ExecutorReport(subtask_id="", status="RUNNING", after=CONTINUE)
        with pytest.raises(TaskControllerValidationError):
            ContractedSubtask("", CONTINUE)

    def test_non_mapping_payload_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            ExecutorReport.from_payload(["not", "a", "mapping"])

    def test_wrong_contracted_type_rejected(self):
        with pytest.raises(TaskControllerValidationError):
            classify_report({"subtask_id": "S1"}, _report())


# ---------------------------------------------------------------- 7
class TestAuthorityCannotBeGranted:
    """R4B-7: authority path cannot approve/merge or mutate runtime."""

    def test_authority_required_intercepts_never_approves(self):
        v = classify_report(ContractedSubtask("S1", TERMINAL),
                            _report(after=TERMINAL, authority_required=True))
        assert v.verdict == INTERCEPT
        assert v.intercept_reason == InterceptReason.AUTHORITY_DRIFT
        assert v.runtime_mutated is False
        assert "not approved" in v.detail and "not merged" in v.detail

    def test_no_approve_or_merge_verdict_can_be_produced(self):
        assert "APPROVE" not in PROTOCOL_VERDICTS
        assert "MERGE" not in PROTOCOL_VERDICTS

    def test_verdict_cannot_self_report_a_mutation(self):
        with pytest.raises(TaskControllerValidationError):
            ProtocolVerdict(verdict=CONTINUE, detail="x", subtask_id="S1",
                            runtime_mutated=True)

    def test_bridge_source_mentions_no_approve_merge_execution(self):
        src = BRIDGE_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(src)
        called = {
            n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        for forbidden in ("approve", "merge", "commit", "put_run", "grant", "dispatch"):
            assert forbidden not in called


# ---------------------------------------------------------------- 8
class TestInputImmutability:
    """R4B-8: immutable input state before/after byte-equivalent."""

    def test_inputs_are_frozen_dataclasses(self):
        for cls in (ContractedSubtask, ExecutorReport, ProtocolVerdict):
            assert dataclasses.is_dataclass(cls)
            assert cls.__dataclass_params__.frozen is True

    def test_frozen_inputs_reject_assignment(self):
        c = ContractedSubtask("S1", CONTINUE)
        r = _report()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.after_report = TERMINAL
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.status = "FAILED"

    def test_inputs_byte_equivalent_before_and_after(self):
        c = ContractedSubtask("S1", CONTINUE)
        r = _report(evidence=("e1",), drift=())
        before = (copy.deepcopy(dataclasses.asdict(c)), copy.deepcopy(dataclasses.asdict(r)))
        classify_report(c, r)
        after = (dataclasses.asdict(c), dataclasses.asdict(r))
        assert before == after

    def test_classification_is_deterministic(self):
        c = ContractedSubtask("S1", WAIT_CONTROLLER)
        r = _report(after=WAIT_CONTROLLER)
        results = {classify_report(c, r).to_dict()["verdict"] for _ in range(25)}
        assert results == {WAIT_CONTROLLER}


# ---------------------------------------------------------------- 9
class TestNoForbiddenRuntimeCoupling:
    """R4B-9: source import scan proves deferred runtime modules absent."""

    FORBIDDEN_MODULES = (
        "taskcontroller.runtime.store",
        "taskcontroller.runtime.lease",
        "taskcontroller.runtime.journal",
        "taskcontroller.runtime.checkpoint",
        "taskcontroller.runtime.recovery",
        "taskcontroller.runtime.event_router",
        "taskcontroller.packs.host_pack",
        "taskcontroller.packs.host_state",
        "taskcontroller.execution.dispatch",
        "taskcontroller.controlplane.engine",
        "taskcontroller.controlplane.orchestrator",
    )
    FORBIDDEN_NAMES = (
        "SlackTaskControllerPack", "LeaseManager", "EventRouter",
        "RunStore", "Journal", "Checkpoint",
    )
    FORBIDDEN_STDLIB = (
        "socket", "urllib", "requests", "httpx", "subprocess",
        "time", "datetime", "random", "secrets", "os", "slack_sdk", "threading",
    )

    def _imports(self):
        tree = ast.parse(BRIDGE_SOURCE.read_text(encoding="utf-8"))
        mods, names = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    mods.add(a.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mods.add(node.module)
                for a in node.names:
                    names.add(a.name)
        return mods, names

    def test_no_forbidden_runtime_modules_imported(self):
        mods, _ = self._imports()
        for bad in self.FORBIDDEN_MODULES:
            assert bad not in mods, f"bridge must not import {bad}"

    def test_no_forbidden_runtime_names_imported(self):
        _, names = self._imports()
        for bad in self.FORBIDDEN_NAMES:
            assert bad not in names, f"bridge must not import {bad}"

    def test_no_io_clock_or_randomness_imported(self):
        mods, _ = self._imports()
        for bad in self.FORBIDDEN_STDLIB:
            assert bad not in mods, f"bridge must not import {bad}"

    def test_bridge_defines_no_json_schema(self):
        src = BRIDGE_SOURCE.read_text(encoding="utf-8")
        assert "$schema" not in src
        assert ".schema.json" not in src
        assert "jsonschema" not in src

    def test_bridge_imports_stay_minimal(self):
        mods, _ = self._imports()
        assert mods <= {"__future__", "dataclasses", "typing", "taskcontroller.errors"}

    def test_module_defines_no_engine_class(self):
        tree = ast.parse(BRIDGE_SOURCE.read_text(encoding="utf-8"))
        classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        for forbidden in ("TaskController", "ControllerRun", "TaskPlan", "Subtask",
                          "GPTTaskController", "ControlPlane", "Engine"):
            assert forbidden not in classes
