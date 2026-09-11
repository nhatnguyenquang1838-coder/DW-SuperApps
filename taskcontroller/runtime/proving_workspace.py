"""Exact source identity and workspace guards for certification runs."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


_SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")


class ProvingWorkspaceError(ValueError):
    """Raised when a certification workspace binding is not exact and safe."""


def _run_git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise ProvingWorkspaceError(f"git checkout probe failed: {detail.strip()}") from exc
    return result.stdout.strip()


@dataclass(frozen=True)
class ExactCheckout:
    repository: str
    branch: str
    sha: str
    root: Path

    def __post_init__(self) -> None:
        if not isinstance(self.repository, str) or not self.repository.strip():
            raise ProvingWorkspaceError("repository is required")
        if not isinstance(self.branch, str) or not self.branch.strip():
            raise ProvingWorkspaceError("branch is required")
        if not isinstance(self.sha, str) or _SHA40.fullmatch(self.sha) is None:
            raise ProvingWorkspaceError("sha must be an exact 40-hex value")
        root = Path(self.root).expanduser()
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "sha", self.sha.lower())


def _allow_eol_only_drift(root: Path) -> bool:
    unstaged = subprocess.run(
        ["git", "diff", "--quiet", "--ignore-space-at-eol"],
        cwd=root,
        check=False,
    ).returncode
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--ignore-space-at-eol"],
        cwd=root,
        check=False,
    ).returncode
    return unstaged == 0 and staged == 0


def verify_exact_checkout(binding: ExactCheckout, canonical_remote: str) -> None:
    """Verify a checkout's remote, exact HEAD, and content cleanliness."""
    root = binding.root
    if not root.exists() or not root.is_dir():
        raise ProvingWorkspaceError(f"checkout root is missing: {root}")
    if not canonical_remote or not canonical_remote.strip():
        raise ProvingWorkspaceError("canonical remote is required")
    if _run_git(root, "rev-parse", "--is-inside-work-tree") != "true":
        raise ProvingWorkspaceError(f"path is not a Git checkout: {root}")
    actual_remote = _run_git(root, "remote", "get-url", "origin")
    if actual_remote != canonical_remote:
        raise ProvingWorkspaceError(
            f"remote mismatch: expected {canonical_remote!r}, got {actual_remote!r}"
        )
    actual_head = _run_git(root, "rev-parse", "HEAD").lower()
    if actual_head != binding.sha:
        raise ProvingWorkspaceError(
            f"HEAD/SHA mismatch: expected {binding.sha}, got {actual_head}"
        )
    status = _run_git(root, "status", "--porcelain")
    if status:
        lines = status.splitlines()
        if any(line.startswith("??") for line in lines) or not _allow_eol_only_drift(root):
            raise ProvingWorkspaceError(
                f"checkout has dirty content drift outside allowed EOL normalization: {status}"
            )


def verify_distinct_workspace(runtime: ExactCheckout, subject: ExactCheckout) -> None:
    """Require separate filesystem roots for runtime and proving subject."""
    if runtime.root.resolve() == subject.root.resolve():
        raise ProvingWorkspaceError(
            "runtime and subject must use distinct workspace roots"
        )


__all__ = [
    "ExactCheckout",
    "ProvingWorkspaceError",
    "verify_distinct_workspace",
    "verify_exact_checkout",
]
