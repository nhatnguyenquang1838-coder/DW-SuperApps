from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("power_dist", ROOT / "scripts" / "power_dist.py")
assert SPEC is not None and SPEC.loader is not None
power_dist = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(power_dist)


class PowerDistributionContractTests(unittest.TestCase):
    def test_valid_recipe_fixture(self) -> None:
        recipe = power_dist.load_structured(
            ROOT / "tests" / "fixtures" / "power-distribution" / "valid-recipe.yaml"
        )
        power_dist.validate_recipe(recipe)

    def test_absolute_include_is_rejected(self) -> None:
        recipe = power_dist.load_structured(
            ROOT
            / "tests"
            / "fixtures"
            / "power-distribution"
            / "invalid-absolute-include.yaml"
        )
        with self.assertRaises(power_dist.DistributionError):
            power_dist.validate_recipe(recipe)

    def test_consumer_binding_fixture(self) -> None:
        binding = yaml.safe_load(
            (
                ROOT
                / "tests"
                / "fixtures"
                / "power-distribution"
                / "valid-consumer-binding.yaml"
            ).read_text(encoding="utf-8")
        )
        schema = json.loads(
            (ROOT / "schemas" / "power-consumer-binding.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(binding)

    def test_manifest_schema_rejects_bad_hash(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "power-package-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        manifest = {
            "apiVersion": "dw.superapps/v1",
            "kind": "PowerPackageManifest",
            "metadata": {
                "powerId": "demo",
                "version": "1.0.0",
                "sourceSha": "abcdef0",
            },
            "spec": {
                "entrypoints": ["skills/demo/SKILL.md"],
                "runtimeDataRoot": ".demo",
                "generatedFiles": ["POWER.yaml"],
            },
            "files": [
                {
                    "path": "skills/demo/SKILL.md",
                    "size": 1,
                    "sha256": "not-a-hash",
                    "mode": "0644",
                }
            ],
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(manifest)


if __name__ == "__main__":
    unittest.main()
