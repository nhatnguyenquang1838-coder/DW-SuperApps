from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest


def _workspace_module():
    try:
        return importlib.import_module("taskcontroller.runtime.proving_workspace")
    except ModuleNotFoundError as exc:
        pytest.fail(f"proving_workspace is not implemented yet: {exc}")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _repo(tmp_path: Path, name: str = "repo") -> tuple[Path, str]:
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("source\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "initial")
    _git(root, "remote", "add", "origin", "git@github.com:nhatnguyenquang1838-coder/gwc.git")
    return root, _git(root, "rev-parse", "HEAD")


def _binding(mod, root: Path, sha: str):
    return mod.ExactCheckout(
        repository="nhatnguyenquang1838-coder/gwc",
        branch="auto/test",
        sha=sha,
        root=root,
    )


def test_verify_exact_checkout_binds_remote_head_and_clean_content(tmp_path):
    mod = _workspace_module()
    root, sha = _repo(tmp_path)
    mod.verify_exact_checkout(_binding(mod, root, sha), "git@github.com:nhatnguyenquang1838-coder/gwc.git")


def test_verify_exact_checkout_rejects_wrong_remote_head_and_missing_root(tmp_path):
    mod = _workspace_module()
    root, sha = _repo(tmp_path)
    with pytest.raises(ValueError, match="remote"):
        mod.verify_exact_checkout(_binding(mod, root, sha), "git@github.com:other/repo.git")
    with pytest.raises(ValueError, match="HEAD|SHA"):
        mod.verify_exact_checkout(_binding(mod, root, "f" * 40), "git@github.com:nhatnguyenquang1838-coder/gwc.git")
    missing = _binding(mod, tmp_path / "missing", sha)
    with pytest.raises(ValueError, match="checkout|root"):
        mod.verify_exact_checkout(missing, "git@github.com:nhatnguyenquang1838-coder/gwc.git")


def test_verify_exact_checkout_rejects_real_dirty_content_but_allows_eol_only(tmp_path):
    mod = _workspace_module()
    root, sha = _repo(tmp_path)
    (root / "README.md").write_text("changed semantic content\n", encoding="utf-8")
    with pytest.raises(ValueError, match="dirty|drift"):
        mod.verify_exact_checkout(_binding(mod, root, sha), "git@github.com:nhatnguyenquang1838-coder/gwc.git")


def test_runtime_and_subject_must_use_distinct_roots(tmp_path):
    mod = _workspace_module()
    root, sha = _repo(tmp_path)
    runtime = _binding(mod, root, sha)
    subject = _binding(mod, root, sha)
    with pytest.raises(ValueError, match="distinct|same root"):
        mod.verify_distinct_workspace(runtime, subject)


def test_distinct_exact_workspaces_are_accepted(tmp_path):
    mod = _workspace_module()
    runtime_root, runtime_sha = _repo(tmp_path, "runtime")
    subject_root, subject_sha = _repo(tmp_path, "subject")
    runtime = _binding(mod, runtime_root, runtime_sha)
    subject = _binding(mod, subject_root, subject_sha)
    mod.verify_distinct_workspace(runtime, subject)
