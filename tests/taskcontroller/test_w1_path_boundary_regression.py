from __future__ import annotations

from pathlib import Path

import pytest

from taskcontroller.domain.runtime_plan import (
    BindingErrorCode,
    FilePlanStore,
    RuntimePlan,
    RuntimePlanStep,
)
from taskcontroller.errors import TaskControllerValidationError


def test_file_plan_store_rejects_sibling_prefix_escape(tmp_path: Path) -> None:
    """A sibling whose name starts with the store name is still outside root."""
    store_root = tmp_path / "store"
    escaped_root = tmp_path / "store-escape"
    store = FilePlanStore(store_root)
    plan = RuntimePlan(
        runtime_plan_ref="../store-escape/plan",
        revision="r1",
        steps={
            "STEP-001": RuntimePlanStep(
                step_id="STEP-001",
                semantic_action="inspect",
            )
        },
    )

    with pytest.raises(TaskControllerValidationError) as exc:
        store.put(plan)

    assert str(exc.value).startswith(BindingErrorCode.PATH_TRAVERSAL)
    assert not (escaped_root / "plan.json").exists()
