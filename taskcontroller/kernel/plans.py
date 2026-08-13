"""WP1 plan/version guards (both axes: plan_version and run_version)."""

from __future__ import annotations

from taskcontroller.kernel.errors import VersionConflict


def check_version(run_state, obj) -> None:
    """Fail closed: reject stale plan_version AND/OR run_version.

    Applies to any WP0 object carrying plan_version and run_version that
    enters kernel decision-making (ExecutionRequest, ReviewResult,
    ControllerDecision, and TaskContract mutations).

    An empty string for plan_version/run_version on the object means "no
    constraint" and never triggers a conflict (even if the run has a version
    set). Only when the object carries a non-empty value that differs from
    the run's does it raise VersionConflict.
    """
    cv = _get_plan_version(run_state)
    rv = _get_run_version(run_state)

    obj_pv = getattr(obj, "plan_version", None)
    obj_rv = getattr(obj, "run_version", None)

    # Empty string means "not set" — no constraint, never conflicts.
    if obj_pv and obj_pv != cv:
        raise VersionConflict(field="plan_version", expected=cv, actual=obj_pv)
    if obj_rv and obj_rv != rv:
        raise VersionConflict(field="run_version", expected=rv, actual=obj_rv)


def _get_plan_version(run_state) -> str:
    return getattr(run_state, "plan_version", "") or ""


def _get_run_version(run_state) -> str:
    return getattr(run_state, "run_version", "") or ""