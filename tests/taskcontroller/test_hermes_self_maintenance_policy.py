"""Contract tests for Hermes executor self-maintenance boundaries."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_taskcontroller_allows_bounded_hermes_self_maintenance():
    registry = (ROOT / "controllers" / "taskcontroller.yaml").read_text(encoding="utf-8")

    assert "executor_self_maintenance:" in registry
    assert "own_runtime_skills: allowed" in registry
    assert "own_agent_instructions: allowed" in registry
    assert "must_not_expand_authority: true" in registry
    assert "must_not_change_controller_contract: true" in registry
    assert "self_modify_agent_instructions_without_explicit_scope: forbidden" not in registry


def test_hermes_self_maintenance_does_not_create_authority():
    overlay = (ROOT / "agents" / "hermes" / "agent-instructions.md").read_text(
        encoding="utf-8"
    )

    assert "may self-maintain its own runtime skills" in overlay
    assert "does not require the current task to explicitly target those files" in overlay
    assert "MUST NOT use self-maintenance to expand authority" in overlay
    assert "alter the TaskController selected plan or contract" in overlay
    assert "change approval, merge, deploy, or production authority semantics" in overlay
    assert "local host skill edits are not canonical authority" in overlay
