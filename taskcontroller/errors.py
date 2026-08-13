"""WP0 TaskController domain errors (NO GWC, framework-neutral)."""

from __future__ import annotations


class TaskControllerValidationError(Exception):
    """Raised when a domain model or JSON payload fails validation."""

    def __init__(self, message: str, *, errors=None):
        super().__init__(message)
        self.message = message
        self.errors = errors
