from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

POWER_DIST_SPEC = importlib.util.spec_from_file_location("power_dist", ROOT / "scripts" / "power_dist.py")
assert POWER_DIST_SPEC is not None and POWER_DIST_SPEC.loader is not None
power_dist = importlib.util.module_from_spec(POWER_DIST_SPEC)
POWER_DIST_SPEC.loader.exec_module(power_dist)

CAPABILITY_SPEC = importlib.util.spec_from_file_location(
    "power_dist_capability", ROOT / "scripts" / "power_dist_capability.py"
)
assert CAPABILITY_SPEC is not None and CAPABILITY_SPEC.loader is not None
power_dist_capability = importlib.util.module_from_spec(CAPABILITY_SPEC)
CAPABILITY_SPEC.loader.exec_module(power_dist_capability)

TOKEN_PATTERN = r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"][^'\"]{12,}['\"]"


class PowerDistributionCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        (self.source / "skills/demo").mkdir(parents=True)
        (self.source / "skills/demo/SKILL.md").write_text("# Demo\n", encoding="utf-8")
        (self.source / "dashboard").mkdir(parents=True)
        (self.source / "dashboard/index.html").write_text("dashboard\n", encoding="utf-8")
        self.recipe = yaml.safe_load(
            (ROOT / "tests" / "fixtures" / "power-distribution" / "valid-recipe.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.recipe["spec"]["include"].append("dashboard/**")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def capability_recipe(self) -> dict:
        recipe = copy.deepcopy(self.recipe)
        recipe["spec"]["capabilities"] = {"dashboard": True}
        return recipe

    def recipe_with_token_pattern(self) -> dict:
        recipe = self.capability_recipe()
        recipe["spec"].setdefault("forbidden", {}).setdefault("contentPatterns", []).append(
            TOKEN_PATTERN
        )
        return recipe

    def assert_style_token_allowed(self, value: str) -> None:
        recipe = self.recipe_with_token_pattern()
        (self.source / "dashboard/index.html").write_text(
            f'token: "{value}"\n', encoding="utf-8"
        )
        power_dist_capability.patch_power_dist_module(power_dist)
        selected = power_dist.collect_files(recipe, self.source)
        self.assertIn(self.source / "dashboard/index.html", selected)

    def test_dashboard_rejected_without_capability(self) -> None:
        with self.assertRaises(power_dist.DistributionError):
            power_dist.collect_files(copy.deepcopy(self.recipe), self.source)

    def test_dashboard_allowed_with_dashboard_capability(self) -> None:
        recipe = self.capability_recipe()
        power_dist_capability.patch_power_dist_module(power_dist)
        selected = power_dist.collect_files(recipe, self.source)
        selected_paths = {path.relative_to(self.source).as_posix() for path in selected}
        self.assertIn("dashboard/index.html", selected_paths)
        self.assertIn("skills/demo/SKILL.md", selected_paths)

    def test_css_custom_property_token_mapping_is_not_a_secret(self) -> None:
        self.assert_style_token_allowed("var(--color-node-config)")

    def test_css_utility_token_mapping_is_not_a_secret(self) -> None:
        self.assert_style_token_allowed("text-node-config")

    def test_css_utility_class_list_is_not_a_secret(self) -> None:
        self.assert_style_token_allowed(
            "text-node-config border border-node-config/30 bg-node-config/10"
        )

    def test_real_token_literal_remains_forbidden(self) -> None:
        recipe = self.recipe_with_token_pattern()
        (self.source / "dashboard/index.html").write_text(
            'token: "abcdefghijklmnop"\n', encoding="utf-8"
        )

        power_dist_capability.patch_power_dist_module(power_dist)
        with self.assertRaises(power_dist.DistributionError):
            power_dist.collect_files(recipe, self.source)


if __name__ == "__main__":
    unittest.main()
