"""TC-MBX-602: capability-based review-lens registry."""

from __future__ import annotations

import pytest

from taskcontroller.execution.errors import ExecutionFabricError
from taskcontroller.execution.lens_registry import (
    BUILTIN_LENS_IDS,
    ReviewLens,
    build_default_lens_registry,
)


def test_default_registry_exposes_required_review_lenses() -> None:
    registry = build_default_lens_registry()

    assert registry.lens_ids() == BUILTIN_LENS_IDS
    assert registry.select(capabilities=("review",))[0].lens_id == "architecture"
    assert registry.resolve("testing-evidence").capabilities == (
        "evidence",
        "review",
        "testing",
    )
    assert registry.resolve("security-reliability").capabilities == (
        "reliability",
        "review",
        "security",
    )


def test_capability_lookup_requires_all_requested_capabilities() -> None:
    registry = build_default_lens_registry()

    selected = registry.select(capabilities=("review", "evidence"))

    assert [lens.lens_id for lens in selected] == ["testing-evidence"]
    assert registry.select(capabilities=("review", "missing")) == ()


def test_task_specific_lens_registers_without_kernel_change() -> None:
    base = build_default_lens_registry()
    custom = base.register(
        ReviewLens(
            lens_id="task:payments-api",
            capabilities=("api", "review", "task-specific"),
            task_specific=True,
        )
    )

    assert "task:payments-api" not in base.lens_ids()
    assert custom.resolve("task:payments-api").task_specific is True
    assert [lens.lens_id for lens in custom.select(capabilities=("api", "review"))] == [
        "task:payments-api"
    ]


def test_registry_snapshot_and_lens_are_immutable() -> None:
    registry = build_default_lens_registry()
    lens = registry.resolve("architecture")

    with pytest.raises(Exception):
        registry.lenses["new"] = lens  # type: ignore[index]
    with pytest.raises(Exception):
        lens.lens_id = "mutated"  # type: ignore[misc]


def test_duplicate_identical_registration_is_idempotent() -> None:
    registry = build_default_lens_registry()
    lens = ReviewLens("task:payments-api", ("api", "review"), task_specific=True)

    once = registry.register(lens)
    twice = once.register(lens)

    assert twice.to_dict() == once.to_dict()
    assert twice.digest == once.digest


def test_duplicate_conflicting_registration_fails_closed() -> None:
    registry = build_default_lens_registry().register(
        ReviewLens("task:payments-api", ("api", "review"), task_specific=True)
    )

    with pytest.raises(ExecutionFabricError, match="duplicate lens_id"):
        registry.register(
            ReviewLens(
                "task:payments-api",
                ("api", "review", "security"),
                task_specific=True,
            )
        )


def test_digest_is_order_independent_for_capabilities() -> None:
    a = build_default_lens_registry().register(
        ReviewLens("task:payments-api", ("review", "api"), task_specific=True)
    )
    b = build_default_lens_registry().register(
        ReviewLens("task:payments-api", ("api", "review"), task_specific=True)
    )

    assert a.digest == b.digest


def test_invalid_lens_definition_fails_closed() -> None:
    with pytest.raises(ExecutionFabricError, match="lens_id"):
        ReviewLens("", ("review",))
    with pytest.raises(ExecutionFabricError, match="capabilit"):
        ReviewLens("task:bad", ("",))
