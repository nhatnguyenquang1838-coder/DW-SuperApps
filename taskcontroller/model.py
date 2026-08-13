from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class AfterReport(str, Enum):
    CONTINUE = "CONTINUE"
    WAIT_CONTROLLER = "WAIT_CONTROLLER"
    TERMINAL = "TERMINAL"


class ReportStatus(str, Enum):
    RUNNING = "RUNNING"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class RunStatus(str, Enum):
    PLANNING = "PLANNING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    WAITING_CONTROLLER = "WAITING_CONTROLLER"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class DriftKind(str, Enum):
    SCOPE = "scope_drift"
    AUTHORITY = "authority_drift"
    PLAN = "plan_drift"
    EVIDENCE = "evidence_conflict"
    MATERIAL_FINDING = "material_finding"


class DecisionKind(str, Enum):
    CONTINUE = "CONTINUE"
    WAIT_CONTROLLER = "WAIT_CONTROLLER"
    INTERCEPT = "INTERCEPT"
    TERMINAL = "TERMINAL"


@dataclass(frozen=True)
class ExecutorTarget:
    """Logical executor identity independent of transport.

    ``kind`` may identify a runtime family (for example ``hermes`` or ``codex``)
    while ``location`` identifies an optional deployment target (for example
    ``cloud`` or ``mac``). Neither value has special meaning to the core.
    """

    id: str
    kind: str
    location: str | None = None
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubtaskContract:
    id: str
    objective: str
    allowed_work: str
    expected_output: str
    report_requirement: str
    after_report: AfterReport = AfterReport.CONTINUE


@dataclass(frozen=True)
class ControllerContract:
    run_id: str
    task: str
    controller_id: str
    executor: ExecutorTarget
    subtasks: tuple[SubtaskContract, ...]
    task_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControllerPolicy:
    """Behavior knobs so pilot constraints do not become core assumptions."""

    min_subtasks: int = 1
    max_subtasks: int = 20
    intercept_on: frozenset[DriftKind] = frozenset(
        {
            DriftKind.SCOPE,
            DriftKind.AUTHORITY,
            DriftKind.PLAN,
            DriftKind.EVIDENCE,
            DriftKind.MATERIAL_FINDING,
        }
    )
    wait_on_blocked: bool = True
    terminal_on_failed: bool = True


@dataclass(frozen=True)
class ExecutorReport:
    run_id: str
    subtask_id: str
    status: ReportStatus
    completed: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    finding_or_risk: tuple[str, ...] = ()
    next_action: str | None = None
    drift: DriftKind | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlDecision:
    kind: DecisionKind
    reason: str
    subtask_id: str | None = None
    required_action: str | None = None


@dataclass
class RunState:
    run_id: str
    status: RunStatus = RunStatus.PLANNING
    active_subtask_id: str | None = None
    completed_subtasks: list[str] = field(default_factory=list)
    last_decision: ControlDecision | None = None
    exact_head: str | None = None
    branch: str | None = None
    pr: str | None = None
    ci: str | None = None
    risk_or_blocker: str | None = None
    last_material_update: str | None = None


@dataclass(frozen=True)
class RootSnapshot:
    """Surface-neutral view model for Slack, console, UI, etc."""

    run_id: str
    human_owner: str | None
    controller: str
    executor: str
    executor_model: str | None
    token_usage: str | None
    cost: str
    active_subtask: str | None
    progress: str
    branch: str | None
    pr: str | None
    exact_head: str | None
    ci: str | None
    risk_or_blocker: str | None
    now: str | None
    next_action: str | None
    last_material_update: str | None
    metadata: Mapping[str, Any] = field(default_factory=dict)
