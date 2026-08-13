"""WP0 TaskController domain contracts (NO GWC).

Public API: models, enums, value objects, identifiers, errors, JSON
round-trip (``to_dict``) / ``from_dict``, and JSON Schema validation.

Canonical, language-neutral contracts live in ``taskcontroller/schemas``.
This Python package is the MVP implementation; later languages should be
generated from / validated against the schemas.
"""

from __future__ import annotations

from taskcontroller.domain import enums, ids, models, values
from taskcontroller.domain.enums import *  # noqa: F401,F403
from taskcontroller.domain.ids import *  # noqa: F401,F403
from taskcontroller.domain.models import *  # noqa: F401,F403
from taskcontroller.domain.serialization import from_dict, to_dict
from taskcontroller.domain.values import *  # noqa: F401,F403
from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.validation import model_names, validate

__all__ = [
    "enums",
    "ids",
    "models",
    "values",
    "to_dict",
    "from_dict",
    "validate",
    "model_names",
    "TaskControllerValidationError",
]
