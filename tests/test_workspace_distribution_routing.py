from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "dw_workspace_dist",
    Path(__file__).resolve().parents[1] / "scripts" / "dw_workspace_dist.py",
)
assert SPEC is not None and SPEC.loader is not None
routing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(routing)


class WorkspaceDistributionRoutingTests(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        (root / "manifests" / "powers").mkdir(parents=True)
        (root / "projects" / "rental-home").mkdir(parents=True)
        (root / "workspace.yaml").write_text(
            """apiVersion: ai-workspace/v1
kind: Workspace
metadata:
  id: test
  name: Test
hosts:
  - codex
  - kiro
distribution:
  ownership: workspace
  storeRoot: .dw/powers
  inboxRoot: .dw/inbox/powers
  historyRoot: .dw/history/powers
  bindingsRoot: .dw/bindings
systems:
  - id: rental-home
    path: projects/rental-home
    enabled_powers:
      - bmad
""",
            encoding="utf-8",
        )
        (root / "manifests" / "powers" / "bmad.yaml").write_text(
            """apiVersion: dw.superapps/v2
kind: Power
metadata:
  id: bmad
  name: BMAD
  description: Delivery workflows.
spec:
  path: powers/bmad
  runtimeDataRoot: .bmad
  hosts:
    - codex
    - kiro
  entrypoints:
    skillCandidates:
      - SKILL.md
""",
            encoding="utf-8",
        )
        installed = root / ".dw" / "powers" / "bmad"
        (installed / "skill").mkdir(parents=True)
        (installed / "skill" / "SKILL.md").write_text("# Managed BMAD\n", encoding="utf-8")
        (installed / "MANIFEST.json").write_text(
            json.dumps(
                {
                    "metadata": {"powerId": "bmad", "version": "1.0.0"},
                    "spec": {
                        "runtimeDataRoot": ".bmad",
                        "entrypoints": ["skill/SKILL.md"],
                    },
                    "files": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        source = root / "powers" / "bmad"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("# Source BMAD\n", encoding="utf-8")

    @contextlib.contextmanager
    def patched_root(self, root: Path):
        previous = (routing.ROOT, routing.WORKSPACE_PATH, routing.MANIFEST_DIR)
        routing.ROOT = root
        routing.WORKSPACE_PATH = root / "workspace.yaml"
        routing.MANIFEST_DIR = root / "manifests" / "powers"
        try:
            yield
        finally:
            routing.ROOT, routing.WORKSPACE_PATH, routing.MANIFEST_DIR = previous

    def test_host_adapter_prefers_workspace_store_and_stays_out_of_system(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            with self.patched_root(root):
                routing.host_install(argparse.Namespace(host="codex", mode="wrapper"))
                adapter = root / ".codex" / "skills" / "bmad" / "SKILL.md"
                self.assertTrue(adapter.is_file())
                text = adapter.read_text(encoding="utf-8")
                self.assertIn("Resolution mode: `workspace-store`", text)
                self.assertIn(".dw/powers/bmad", text)
                self.assertIn("This Power is already active", text)
                self.assertNotIn("Generate a complete task prompt", text)
                self.assertFalse((root / "projects" / "rental-home" / ".codex").exists())
                self.assertFalse((root / "projects" / "rental-home" / ".dw").exists())
                self.assertFalse((root / "projects" / "rental-home" / "SKILL.md").exists())

    def test_prompt_command_is_removed(self) -> None:
        self.assertFalse(hasattr(routing, "power_prompt"))
        with self.assertRaises(SystemExit) as raised:
            routing.parser().parse_args(
                ["power", "prompt", "bmad", "--system", "rental-home"]
            )
        self.assertNotEqual(raised.exception.code, 0)

    def test_source_submodule_is_only_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            installed = root / ".dw" / "powers" / "bmad"
            for path in sorted(installed.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            installed.rmdir()
            with self.patched_root(root):
                source, mode = routing.resolve_skill_source(
                    "bmad", routing.manifests()["bmad"]
                )
                self.assertEqual("source-submodule-fallback", mode)
                self.assertEqual(root / "powers" / "bmad", source)


if __name__ == "__main__":
    unittest.main()
