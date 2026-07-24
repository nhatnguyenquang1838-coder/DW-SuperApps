from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dw_cli", ROOT / "scripts" / "dw_cli.py")
assert SPEC is not None and SPEC.loader is not None
dw_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dw_cli)


class PowerDistributionIntegrationTests(unittest.TestCase):
    def test_all_manifests_share_distribution_contract(self) -> None:
        for power_id, manifest in dw_cli.manifests().items():
            with self.subTest(power_id=power_id):
                distribution = manifest["spec"]["distribution"]
                self.assertEqual("dw.power-distribution/v1", distribution["contract"])
                expected_default = "release" if power_id == "bmad" else "power-dist"
                self.assertEqual(expected_default, distribution["defaultMode"])
                self.assertEqual(
                    {"submodule", "release", "powerDist"},
                    set(distribution["modes"]),
                )
                self.assertEqual(
                    manifest["spec"]["path"],
                    distribution["modes"]["submodule"]["path"],
                )

    def test_provider_evidence_is_explicit(self) -> None:
        states = {
            power_id: manifest["spec"]["distribution"]["providerState"]
            for power_id, manifest in dw_cli.manifests().items()
        }
        expected_commits = {
            "gwc": "62689ce35e279751a3bf17b5255ac258dafbe7d7",
            "task-me": "ef0b890b1fb9140109c04cbb490b41d9aa94bfff",
            "ua": "c0e4821c519f564d6c8b353537cf121eb52a1617",
            "bmad": "bb45db4aa4496c69239f9c0629c290fd1b072fc9",
        }
        for power_id, source_commit in expected_commits.items():
            with self.subTest(power_id=power_id):
                expected_status = "ready-unpublished" if power_id == "bmad" else "published"
                self.assertEqual(expected_status, states[power_id]["status"])
                self.assertEqual(source_commit, states[power_id]["sourceCommit"])

    def test_submodule_source_contract_remains_available_as_fallback(self) -> None:
        for power_id, manifest in dw_cli.manifests().items():
            with self.subTest(power_id=power_id):
                submodule = manifest["spec"]["distribution"]["modes"]["submodule"]
                self.assertEqual(manifest["spec"]["source"], submodule["repository"])


if __name__ == "__main__":
    unittest.main()
