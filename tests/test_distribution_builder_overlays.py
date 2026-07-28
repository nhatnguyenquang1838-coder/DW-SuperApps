from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "distribution_builder", ROOT / "scripts" / "distribution_builder.py"
)
assert SPEC is not None and SPEC.loader is not None
distribution_builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(distribution_builder)


class DistributionBuilderOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_prepare_source_applies_dw_owned_overlay_without_mutating_provider(self) -> None:
        source = self.root / "provider"
        (source / "distribution").mkdir(parents=True)
        (source / "base.txt").write_text("provider\n", encoding="utf-8")
        provider_recipe = source / "distribution" / "power-package.yaml"
        provider_recipe.write_text("invalid provider recipe\n", encoding="utf-8")

        overlay = self.root / "overlay"
        overlay_skill = overlay / "distribution" / "skills" / "bmad" / "SKILL.md"
        overlay_skill.parent.mkdir(parents=True)
        overlay_skill.write_text("# BMAD\n", encoding="utf-8")

        recipe = self.root / "power-package.yaml"
        recipe.write_text("valid DW recipe\n", encoding="utf-8")
        output = self.root / "output"

        original = distribution_builder.POWER_OVERLAYS
        distribution_builder.POWER_OVERLAYS = {
            "bmad": {"overlay_root": overlay, "recipe_path": recipe}
        }
        try:
            prepared = distribution_builder.prepare_source("bmad", source, output)
        finally:
            distribution_builder.POWER_OVERLAYS = original

        self.assertNotEqual(source, prepared)
        self.assertEqual("provider\n", (prepared / "base.txt").read_text(encoding="utf-8"))
        self.assertEqual(
            "# BMAD\n",
            (prepared / "distribution" / "skills" / "bmad" / "SKILL.md").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            "valid DW recipe\n",
            (prepared / "distribution" / "power-package.yaml").read_text(encoding="utf-8"),
        )
        self.assertEqual("invalid provider recipe\n", provider_recipe.read_text(encoding="utf-8"))

    def test_prepare_source_returns_provider_when_no_overlay_is_registered(self) -> None:
        source = self.root / "provider"
        source.mkdir()
        original = distribution_builder.POWER_OVERLAYS
        distribution_builder.POWER_OVERLAYS = {}
        try:
            prepared = distribution_builder.prepare_source("gwc", source, self.root / "output")
        finally:
            distribution_builder.POWER_OVERLAYS = original
        self.assertEqual(source, prepared)


if __name__ == "__main__":
    unittest.main()
