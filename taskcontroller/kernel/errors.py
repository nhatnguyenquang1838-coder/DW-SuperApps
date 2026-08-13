"""WP1 deterministic kernel errors (NO GWC, framework-neutral)."""

from __future__ import annotations


class KernelError(Exception):
    """Base for all WP1 kernel errors."""

    pass


class TransitionRejected(KernelError):
    """A requested run/node transition is not legal."""

    def __init__(self, reason: str, current: str | None = None, target: str | None = None) -> None:
        msg = f"transition rejected: {reason}"
        if current is not None and target is not None:
            msg = f"transition rejected: {current} → {target}: {reason}"
        elif current is not None:
            msg = f"transition rejected: {reason} (current={current})"
        super().__init__(msg)


class VersionConflict(KernelError):
    """An object's plan_version and/or run_version is stale."""

    def __init__(self, field: str, expected: str | None, actual: str) -> None:
        msg = f"version conflict on {field}: expected {expected!r}, got {actual!r}"
        super().__init__(msg)


class UnknownDependencyError(KernelError):
    """A TaskContract references a dependency (run_id, node_id) not present."""

    def __init__(self, missing: tuple[str, str]) -> None:
        super().__init__(f"unknown dependency: run {missing[0]}, node {missing[1]}")


class CycleDetectedError(KernelError):
    """The dependency graph contains a cycle."""

    def __init__(self) -> None:
        super().__init__("dependency graph contains a cycle")


class ReviewNotBinding(KernelError):
    """A REVIEWING → DONE request has no exact-binding PASS review for the target."""

    pass


class ReplanPreconditionError(KernelError):
    """replan() precondition on run status not met."""