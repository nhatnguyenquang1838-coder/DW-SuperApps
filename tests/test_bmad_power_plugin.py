from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]

POWER_DIST_SPEC = importlib.util.spec_from_file_location(
    "power_dist", ROOT / "scripts" / "power_dist.py"
)
assert POWER_DIST_SPEC is not None and POWER_DIST_SPEC.loader is not None
power_dist = importlib.util.module_from_spec(POWER_DIST_SPEC)
POWER_DIST_SPEC.loader.exec_module(power_dist)

BOOTSTRAP_SPEC = importlib.util.spec_from_file_location(
    "bootstrap_bmad",
    ROOT / "plugins" / "bmad-method" / "overlay" / "distribution" / "lib" / "bootstrap_bmad.py",
)
assert BOOTSTRAP_SPEC is not None and BOOTSTRAP_SPEC.loader is not None
bootstrap_bmad = importlib.util.module_from_spec(BOOTSTRAP_SPEC)
BOOTSTRAP_SPEC.loader.exec_module(bootstrap_bmad)


class BmadPowerPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = ROOT / "plugins" / "bmad-method"
        self.recipe_path = self.plugin / "distribution" / "power-package.yaml"

    def test_source_lock_and_graph_use_same_commit(self) -> None:
        lock = json.loads((self.plugin / "SOURCE.lock.json").read_text(encoding="utf-8"))
        graph = json.loads(
            (self.plugin / "knowledge" / "knowledge-graph.json").read_text(encoding="utf-8")
        )
        self.assertEqual(lock["sourceCommit"], graph["project"]["gitCommitHash"])
        self.assertEqual("6.10.0", lock["sourceVersion"])

    def test_knowledge_graph_references_are_closed(self) -> None:
        graph = json.loads(
            (self.plugin / "knowledge" / "knowledge-graph.json").read_text(encoding="utf-8")
        )
        node_ids = [node["id"] for node in graph["nodes"]]
        self.assertEqual(len(node_ids), len(set(node_ids)))
        known = set(node_ids)
        for edge in graph["edges"]:
            self.assertIn(edge["source"], known)
            self.assertIn(edge["target"], known)
        for layer in graph["layers"]:
            self.assertTrue(set(layer["nodeIds"]).issubset(known))
        for step in graph["tour"]:
            self.assertTrue(set(step["nodeIds"]).issubset(known))

    def test_distribution_recipe_is_valid_and_skills_only(self) -> None:
        recipe = power_dist.load_structured(self.recipe_path)
        power_dist.validate_recipe(recipe)
        includes = set(recipe["spec"]["include"])
        self.assertIn("src/core-skills/**", includes)
        self.assertIn("src/bmm-skills/**", includes)
        self.assertNotIn("website/**", includes)
        self.assertNotIn("docs/**", includes)
        self.assertEqual(
            ["distribution/skills/bmad/SKILL.md"],
            recipe["spec"]["package"]["entrypoints"],
        )

    def test_power_manifest_validates(self) -> None:
        manifest = yaml.safe_load(
            (ROOT / "manifests" / "powers" / "bmad.yaml").read_text(encoding="utf-8")
        )
        schema = json.loads(
            (ROOT / "schemas" / "power-manifest.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator(schema).validate(manifest)
        self.assertEqual("release", manifest["spec"]["distribution"]["defaultMode"])
        self.assertEqual(
            "power-dist-bmad",
            manifest["spec"]["distribution"]["modes"]["powerDist"]["ref"],
        )

    def test_bootstrap_host_mapping(self) -> None:
        self.assertEqual("codex", bootstrap_bmad.HOST_MAP["codex"])
        self.assertEqual("claude-code", bootstrap_bmad.HOST_MAP["claude"])
        self.assertEqual("github-copilot", bootstrap_bmad.HOST_MAP["copilot"])
        self.assertEqual((20, 12, 0), bootstrap_bmad.MIN_NODE)

    def test_external_source_overlay_builds_a_deterministic_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = root / "provider"
            staging = root / "output" / "staging" / "bmad-main-test"
            provider.mkdir()

            files = {
                "src/core-skills/module.yaml": "code: core\n",
                "src/core-skills/bmad-help/SKILL.md": "---\nname: bmad-help\n---\n",
                "src/bmm-skills/module.yaml": "code: bmm\n",
                "src/bmm-skills/1-analysis/create-product-brief/SKILL.md": (
                    "---\nname: create-product-brief\n---\n"
                ),
                "src/scripts/resolve_config.py": "print('ok')\n",
                "tools/installer/bmad-cli.js": "#!/usr/bin/env node\n",
                "tools/installer/commands/install.js": "module.exports = {};\n",
                "bmad-modules.yaml": "modules: []\n",
                "package.json": '{"name":"bmad-method","version":"6.10.0"}\n',
                "package-lock.json": '{"lockfileVersion":3}\n',
                "LICENSE": "MIT\n",
                "TRADEMARK.md": "BMAD\n",
            }
            for relative, content in files.items():
                path = provider / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            shutil.copytree(
                self.plugin / "overlay" / "distribution",
                provider / "distribution",
            )
            shutil.copyfile(
                self.recipe_path,
                provider / "distribution" / "power-package.yaml",
            )

            recipe = power_dist.load_structured(provider / "distribution" / "power-package.yaml")
            power_dist.build_staging_tree(
                recipe,
                provider,
                staging,
                version="main-test",
                source_repository="nhatnguyenquang1838-coder/BMAD-METHOD",
                source_ref="main",
                source_sha="b" * 40,
                source_date_epoch=1700000000,
            )
            first = root / "first.zip"
            second = root / "second.zip"
            power_dist.create_deterministic_zip(
                staging,
                first,
                package_directory="bmad-main-test",
                source_date_epoch=1700000000,
            )
            power_dist.create_deterministic_zip(
                staging,
                second,
                package_directory="bmad-main-test",
                source_date_epoch=1700000000,
            )
            self.assertEqual(power_dist.sha256_file(first), power_dist.sha256_file(second))
            self.assertTrue((staging / "distribution" / "skills" / "bmad" / "SKILL.md").is_file())
            self.assertFalse((staging / "website").exists())
            self.assertFalse((staging / "test").exists())

    def test_workflow_has_manual_and_scheduled_modes(self) -> None:
        workflow = yaml.load(
            (ROOT / ".github" / "workflows" / "publish-bmad-power.yml").read_text(
                encoding="utf-8"
            ),
            Loader=yaml.BaseLoader,
        )
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertIn("schedule", workflow["on"])


if __name__ == "__main__":
    unittest.main()
