from __future__ import annotations

from typing import Protocol, Sequence

from .model import ControlDecision, ControllerContract, ExecutorReport, RootSnapshot


class TaskBackend(Protocol):
    """Optional task-system adapter (Jira, GitHub, Linear, custom, etc.)."""

    def read_task(self, task_ref: str) -> dict: ...

    def publish_controller_state(self, task_ref: str, state: dict) -> None: ...


class ExecutorAdapter(Protocol):
    """Dispatch/observe/control an executor without constraining its runtime."""

    def dispatch(self, contract: ControllerContract) -> None: ...

    def read_reports(self, run_id: str, cursor: str | None = None) -> tuple[Sequence[ExecutorReport], str | None]: ...

    def command(self, run_id: str, decision: ControlDecision) -> None: ...


class VisibilitySurface(Protocol):
    """Optional human-facing projection such as Slack, terminal, or web UI."""

    def upsert_root(self, snapshot: RootSnapshot) -> None: ...

    def publish_report(self, report: ExecutorReport, decision: ControlDecision) -> None: ...
