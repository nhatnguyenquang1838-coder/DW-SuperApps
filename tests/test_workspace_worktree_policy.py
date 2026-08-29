from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_workspace_worktree_policy.py"
SPEC = importlib.util.spec_from_file_location("validate_workspace_worktree_policy", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


class WorkspaceWorktreePolicyTests(unittest.TestCase):
    def test_static_policy_contract_is_valid(self) -> None:
        errors, projects = POLICY.validate_static()
        self.assertEqual([], errors)
        self.assertGreater(len(projects), 0)

    def test_worktree_template_is_repository_execution_unit_scoped(self) -> None:
        workspace = POLICY.load_yaml(POLICY.WORKSPACE)
        development = workspace["development"]
        self.assertEqual("worktrees/{project}/{execution_unit}", development["worktreeTemplate"])
        self.assertTrue(development["executionUnit"]["oneWorktree"])
        self.assertTrue(development["executionUnit"]["oneBranch"])
        self.assertTrue(development["executionUnit"]["oneWriter"])
        self.assertEqual(
            "lease-or-binding-not-branch",
            development["executionUnit"]["agentIdentity"],
        )

    def test_runtime_rejects_linked_worktree_outside_workspace_root(self) -> None:
        projects = [{"id": "gwc", "path": "projects/gwc"}]
        fake_anchor = POLICY.ROOT / "projects" / "gwc"
        fake_git = fake_anchor / ".git"

        with mock.patch.object(Path, "exists", autospec=True) as exists, mock.patch.object(
            POLICY, "run_git"
        ) as run_git, mock.patch.object(
            POLICY, "parse_worktree_paths", return_value=[fake_anchor.resolve(), Path("/tmp/gwc-task")]
        ):
            exists.side_effect = lambda path: path == fake_git
            run_git.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            errors = POLICY.validate_runtime(projects)

        self.assertTrue(any("outside DW-SuperApps/worktrees" in error for error in errors))

    def test_runtime_accepts_project_scoped_execution_unit_path(self) -> None:
        projects = [{"id": "gwc", "path": "projects/gwc"}]
        fake_anchor = POLICY.ROOT / "projects" / "gwc"
        fake_git = fake_anchor / ".git"
        valid = POLICY.ROOT / "worktrees" / "gwc" / "SCRUM-555" / "M5-G6"

        with mock.patch.object(Path, "exists", autospec=True) as exists, mock.patch.object(
            POLICY, "run_git"
        ) as run_git, mock.patch.object(
            POLICY, "parse_worktree_paths", return_value=[fake_anchor.resolve(), valid.resolve()]
        ):
            exists.side_effect = lambda path: path == fake_git
            run_git.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            errors = POLICY.validate_runtime(projects)

        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
