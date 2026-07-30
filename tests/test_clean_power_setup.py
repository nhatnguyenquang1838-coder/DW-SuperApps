from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "clean_power_setup", ROOT / "scripts" / "clean_power_setup.py"
)
assert SPEC is not None and SPEC.loader is not None
cleanup_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup_module)


class CleanPowerSetupTests(unittest.TestCase):
    def workspace(self, root: Path) -> None:
        (root / "workspace.yaml").write_text(
            """distribution:
  storeRoot: .dw/powers
  inboxRoot: .dw/inbox/powers
  cacheRoot: .dw/cache
  historyRoot: .dw/history/powers
bindingsRoot: .dw/bindings
projects:
  - id: demo
    path: systems/demo
    source: example/demo
    roles:
      - product
data_ownership:
  roots:
    gwc: .gwc
    ua: .ua
""",
            encoding="utf-8",
        )
        (root / "systems/demo").mkdir(parents=True)

    def test_dry_run_preserves_power_setup_and_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.workspace(root)
            package = root / ".dw/powers/gwc"
            package.mkdir(parents=True)
            (package / "MANIFEST.json").write_text("{}\n", encoding="utf-8")
            runtime = root / "systems/demo/.gwc"
            runtime.mkdir(parents=True)
            result = cleanup_module.cleanup(yes=False, include_runtime=False, root=root)
            self.assertEqual("DRY_RUN", result["status"])
            self.assertTrue(package.exists())
            self.assertTrue(runtime.exists())

    def test_cleanup_removes_distribution_setup_but_preserves_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.workspace(root)
            for relative in (
                ".dw/powers/gwc",
                ".dw/inbox/powers/gwc",
                ".dw/cache",
                ".dw/history/powers/gwc",
                ".dw/history/offline-releases",
                ".dw/bindings/demo",
                ".dw/distributions",
            ):
                (root / relative).mkdir(parents=True)
            runtime = root / "systems/demo/.gwc"
            runtime.mkdir(parents=True)
            result = cleanup_module.cleanup(yes=True, include_runtime=False, root=root)
            self.assertEqual("CLEANED", result["status"])
            self.assertFalse((root / ".dw/powers").exists())
            self.assertFalse((root / ".dw/distributions").exists())
            self.assertFalse((root / ".dw/history/offline-releases").exists())
            self.assertTrue(runtime.exists())

    def test_runtime_cleanup_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.workspace(root)
            runtime = root / "systems/demo/.gwc"
            runtime.mkdir(parents=True)
            with self.assertRaises(cleanup_module.CleanupError):
                cleanup_module.cleanup(yes=False, include_runtime=True, root=root)
            cleanup_module.cleanup(yes=True, include_runtime=True, root=root)
            self.assertFalse(runtime.exists())

    def test_external_distribution_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.workspace(root)
            (root / "workspace.yaml").write_text(
                "distribution:\n  storeRoot: /tmp/external-powers\n", encoding="utf-8"
            )
            with self.assertRaises(cleanup_module.CleanupError):
                cleanup_module.build_plan(include_runtime=False, root=root)


if __name__ == "__main__":
    unittest.main()
