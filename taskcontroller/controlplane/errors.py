"""WP5 control-plane errors (NO GWC, framework-neutral)."""

from __future__ import annotations

from taskcontroller.errors import TaskControllerValidationError


class ControlPlaneError(TaskControllerValidationError):
    """Base for WP5 control-plane errors."""


class UnknownIntentError(ControlPlaneError):
    """Typed reject for an unrecognized control intent."""


class TerminalRunError(ControlPlaneError):
    """Control intent rejected because the run is terminal."""


class StaleVersionError(ControlPlaneError):
    """CAS conflict: expected_version does not match the live store version.

    Must never cause partial mutation — the command is rejected wholesale.
    """
