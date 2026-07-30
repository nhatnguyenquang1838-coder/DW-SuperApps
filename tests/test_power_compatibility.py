from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

SPEC = importlib.util.spec_from_file_location("power_dist_compat", SCRIPTS / "power_dist.py")
assert SPEC is not None and SPEC.loader is not None
power_dist = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(power_dist)

import sys
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from dw_power_store.compatibility import compatibility_lock, validate_lock  # noqa: E402


class PowerCompatibilityTests(unittest.TestCase):
    def test_lock_matches_all_power_manifests(self) -> None:
        result = validate_lock()
        self.assertEqual(4, result["power_count"])
        self.assertEqual("PASS", result["status"])
        self.assertEqual([], result["warnings"])

    def test_current_published_contracts_are_locked(self) -> None:
        powers = compatibility_lock()["powers"]
        for power_id in ("gwc", "ua", "task-me", "bmad"):
            with self.subTest(power_id=power_id):
                manifest = yaml.safe_load(
                    (ROOT / "manifests" / "powers" / f"{power_id}.yaml").read_text(
                        encoding="utf-8"
                    )
                )
                # The root gitlink is the immutable integration pin. The
                # nested provider checkout may be intentionally ahead or
                # dirty during workspace maintenance.
                gitlink = subprocess.check_output(
                    ["git", "ls-tree", "HEAD", manifest["spec"]["path"]],
                    cwd=ROOT,
                    text=True,
                ).strip().split()
                self.assertGreaterEqual(len(gitlink), 3)
                self.assertEqual("160000", gitlink[0])
                expected = gitlink[2]
                self.assertEqual(expected, powers[power_id]["publishedSourceSha"])

    def test_new_package_contains_static_agent_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "skills/demo").mkdir(parents=True)
            (source / "skills/demo/SKILL.md").write_text("# Demo\n", encoding="utf-8")
            (source / "README.md").write_text("demo\n", encoding="utf-8")
            recipe = yaml.safe_load(
                (ROOT / "tests/fixtures/power-distribution/valid-recipe.yaml").read_text(
                    encoding="utf-8"
                )
            )
            package = root / "package"
            power_dist.build_staging_tree(
                recipe,
                source,
                package,
                version="demo-v1",
                source_repository="example/demo",
                source_ref="main",
                source_sha="abcdef0123456789",
                source_date_epoch=1700000000,
                templates_root=ROOT / "templates/power-runtime",
            )
            manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual("AGENT_GUIDANCE.md", manifest["spec"]["agentGuidance"])
            guidance = (package / "AGENT_GUIDANCE.md").read_text(encoding="utf-8")
            self.assertIn("native alias selects a skill", guidance)
            self.assertNotIn("dw power prompt", guidance)


if __name__ == "__main__":
    unittest.main()
