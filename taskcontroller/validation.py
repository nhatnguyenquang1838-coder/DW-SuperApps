"""WP0 TaskController validation: JSON Schema loading + instance validation.

The canonical, language-neutral contracts are the JSON Schema documents under
``taskcontroller/schemas``. This module loads them and validates Python
dict instances (typically produced by ``to_dict``) against the matching schema.

No Slack / Hermes / OpenAI ADK / GWC / product imports are used here.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from taskcontroller.errors import TaskControllerValidationError

_SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"

# model_name -> schema filename
_SCHEMA_FILES = {
    "controller_host_profile": "controller_host_profile.schema.json",
    "capability_card": "capability_card.schema.json",
    "execution_provider_card": "execution_provider_card.schema.json",
    "task_contract": "task_contract.schema.json",
    "execution_request": "execution_request.schema.json",
    "execution_receipt": "execution_receipt.schema.json",
    "agent_event": "agent_event.schema.json",
    "artifact": "artifact.schema.json",
    "review_result": "review_result.schema.json",
    "work_lease": "work_lease.schema.json",
    "team_run_state": "team_run_state.schema.json",
    "controller_decision": "controller_decision.schema.json",
}


@lru_cache(maxsize=None)
def _load_registry() -> Registry:
    """Load common schema + all model schemas into a $ref registry."""
    resources = {}
    schema_dir = _SCHEMAS_DIR
    for path in schema_dir.glob("*.schema.json"):
        doc = json.loads(path.read_text())
        uri = doc.get("$id")
        if uri:
            resources[uri] = Resource.from_contents(doc)
    registry = Registry().with_resources(list(resources.items()))
    return registry


def get_schema(name: str) -> dict:
    if name not in _SCHEMA_FILES:
        raise KeyError(f"unknown schema: {name!r}")
    text = (_SCHEMAS_DIR / _SCHEMA_FILES[name]).read_text()
    return json.loads(text)


def validate(name: str, instance: dict) -> None:
    """Validate ``instance`` (a dict) against the named model schema.

    Raises TaskControllerValidationError on failure aggregating all issues.
    """
    schema = get_schema(name)
    registry = _load_registry()
    validator = Draft202012Validator(schema, registry=registry)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        messages = [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
        raise TaskControllerValidationError(
            f"schema validation failed for {name}", errors=messages
        )


def model_names() -> list[str]:
    return list(_SCHEMA_FILES.keys())
