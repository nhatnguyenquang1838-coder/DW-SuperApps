"""Generic TaskController core for DW-SuperApps.

The package is intentionally host-, executor-, tracker-, and surface-agnostic.
Host skills and adapters translate platform-specific tools into these contracts.
"""

from .core import ContractError, TaskController, evaluate_report, validate_contract
from .model import (
    AfterReport,
    ControlDecision,
    ControllerContract,
    ControllerPolicy,
    DecisionKind,
    DriftKind,
    ExecutorReport,
    ExecutorTarget,
    ReportStatus,
    RootSnapshot,
    RunState,
    RunStatus,
    SubtaskContract,
)

__all__ = [
    "AfterReport",
    "ContractError",
    "ControlDecision",
    "ControllerContract",
    "ControllerPolicy",
    "DecisionKind",
    "DriftKind",
    "ExecutorReport",
    "ExecutorTarget",
    "ReportStatus",
    "RootSnapshot",
    "RunState",
    "RunStatus",
    "SubtaskContract",
    "TaskController",
    "evaluate_report",
    "validate_contract",
]
