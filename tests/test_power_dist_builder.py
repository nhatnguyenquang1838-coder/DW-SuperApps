from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("power_dist", ROOT / "scripts" / "power_dist.py")
assert SPEC is not None and SPEC.loader is not None
power_dist = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(power_dist)


class PowerDistributionBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        (self.source / "skills/demo").mkdir(parents=True)
        (self.source / "skills/demo/SKILL.md").write_text("# Demo\n", encoding="utf-8")
        (self.source / "README.md").write_text("demo\n", encoding="utf-8")
        self.recipe = yaml.safe_load(
            (
                ROOT
                / "tests"
                / "fixtures"
                / "power-distribution"
                / "valid-recipe.yaml"
            ).read_text(encoding="utf-8")
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, output: str) -> dict[str, str]:
        args = type(
            "Args",
            (),
            {
                "recipe": str(
                    ROOT
                    / "tests"
                    / "fixtures"
                    / "power-distribution"
                    / "valid-recipe.yaml"
                ),
                "source": str(self.source),
                "output": str(self.root / output),
                "version": "power-v1.0.0",
                "source_repository": "example/demo",
                "source_ref": "main",
                "source_sha": "abcdef0123456789",
                "source_date_epoch": 1700000000,
                "templates_root": str(ROOT / "templates" / "power-runtime"),
            },
        )()
        return power_dist.build_command(args)

    def test_build_is_deterministic_and_verifiable(self) -> None:
        first = self.build("first")
        second = self.build("second")
        self.assertEqual(first["sha256"], second["sha256"])
        manifest = power_dist.verify_package(Path(first["staging_root"]))
        self.assertEqual("demo", manifest["metadata"]["powerId"])
        paths = {entry["path"] for entry in manifest["files"]}
        self.assertIn("skills/demo/SKILL.md", paths)
        self.assertIn("bin/install", paths)
        self.assertIn("lib/power_runtime.py", paths)
        self.assertIn("AGENT_GUIDANCE.md", paths)
        self.assertEqual("AGENT_GUIDANCE.md", manifest["spec"]["agentGuidance"])
        guidance = (Path(first["staging_root"]) / "AGENT_GUIDANCE.md").read_text(encoding="utf-8")
        self.assertIn("static distribution guidance", guidance)
        self.assertNotIn("dw power prompt", guidance)

    def test_ua_guidance_teaches_graph_first_lookup(self) -> None:
        recipe = dict(self.recipe)
        recipe["metadata"] = dict(recipe["metadata"])
        recipe["metadata"]["id"] = "ua"
        recipe["spec"] = dict(recipe["spec"])
        recipe["spec"]["runtime"] = dict(recipe["spec"]["runtime"])
        recipe["spec"]["runtime"]["dataRoot"] = ".ua"
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "package"
            power_dist.build_staging_tree(
                recipe,
                self.source,
                package,
                version="ua-v1",
                source_repository="example/ua",
                source_ref="main",
                source_sha="abcdef0123456789",
                source_date_epoch=1700000000,
                templates_root=ROOT / "templates" / "power-runtime",
            )
            guidance = (package / "AGENT_GUIDANCE.md").read_text(encoding="utf-8")
            self.assertIn("## UA task routing", guidance)
            self.assertIn("do not rebuild it, browse the web, or invent edges", guidance)
            self.assertIn("exact matching node IDs", guidance)

    def test_runtime_data_is_forbidden(self) -> None:
        (self.source / ".demo").mkdir()
        (self.source / ".demo/state.json").write_text("{}", encoding="utf-8")
        self.recipe["spec"]["include"].append(".demo/**")
        with self.assertRaises(power_dist.DistributionError):
            power_dist.collect_files(self.recipe, self.source)

    def test_dashboard_is_forbidden(self) -> None:
        (self.source / "dashboard").mkdir()
        (self.source / "dashboard/index.html").write_text("x", encoding="utf-8")
        self.recipe["spec"]["include"].append("dashboard/**")
        with self.assertRaises(power_dist.DistributionError):
            power_dist.collect_files(self.recipe, self.source)

    def test_secret_content_is_forbidden(self) -> None:
        (self.source / "README.md").write_text(
            "-----BEGIN PRIVATE KEY-----\n", encoding="utf-8"
        )
        with self.assertRaises(power_dist.DistributionError):
            power_dist.collect_files(self.recipe, self.source)

    @unittest.skipIf(os.name == "nt", "symlink creation requires elevated Windows privileges")
    def test_external_symlink_is_rejected(self) -> None:
        external = self.root / "external.txt"
        external.write_text("outside", encoding="utf-8")
        (self.source / "skills/demo/external.txt").symlink_to(external)
        with self.assertRaises(power_dist.DistributionError):
            power_dist.collect_files(self.recipe, self.source)

    @unittest.skipIf(os.name == "nt", "symlink creation requires elevated Windows privileges")
    def test_excluded_symlink_is_ignored(self) -> None:
        excluded = self.source / "node_modules"
        excluded.mkdir()
        target = self.root / "external-node-module.txt"
        target.write_text("excluded", encoding="utf-8")
        (excluded / "package.txt").symlink_to(target)
        recipe = dict(self.recipe)
        recipe["spec"] = dict(self.recipe["spec"])
        recipe["spec"]["include"] = ["**/*"]
        recipe["spec"]["exclude"] = ["node_modules/**"]
        selected = power_dist.collect_files(recipe, self.source)
        self.assertNotIn(excluded / "package.txt", selected)

    def test_manifest_detects_tampering(self) -> None:
        result = self.build("tamper")
        skill = Path(result["staging_root"]) / "skills/demo/SKILL.md"
        skill.write_text("changed", encoding="utf-8")
        with self.assertRaises(power_dist.DistributionError):
            power_dist.verify_package(Path(result["staging_root"]))


if __name__ == "__main__":
    unittest.main()
