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
                expected_default = "release" if power_id == "bmad" else "submodule"
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
        self.assertEqual("blocked-policy", states["gwc"]["status"])
        self.assertEqual("ready-unpublished", states["task-me"]["status"])
        self.assertEqual(
            "711d6314f31a844253bb6719cd28986817768ebc",
            states["task-me"]["sourceCommit"],
        )
        self.assertEqual("blocked-missing-repository", states["ua"]["status"])
        self.assertEqual("ready-unpublished", states["bmad"]["status"])
        self.assertEqual(
            "bb45db4aa4496c69239f9c0629c290fd1b072fc9",
            states["bmad"]["sourceCommit"],
        )

    def test_submodule_source_contract_remains_canonical(self) -> None:
        for power_id, manifest in dw_cli.manifests().items():
            with self.subTest(power_id=power_id):
                submodule = manifest["spec"]["distribution"]["modes"]["submodule"]
                self.assertEqual(manifest["spec"]["source"], submodule["repository"])


if __name__ == "__main__":
    unittest.main()
