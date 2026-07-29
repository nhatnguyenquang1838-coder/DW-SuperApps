from __future__ import annotations

import importlib.util
import subprocess
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
                self.assertEqual("power-dist", distribution["defaultMode"])
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
        for power_id, state in states.items():
            with self.subTest(power_id=power_id):
                source_root = ROOT / dw_cli.manifests()[power_id]["spec"]["path"]
                source_commit = subprocess.check_output(
                    ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True
                ).strip()
                self.assertEqual(source_commit, state["sourceCommit"])

    def test_submodule_source_contract_remains_available_as_fallback(self) -> None:
        for power_id, manifest in dw_cli.manifests().items():
            with self.subTest(power_id=power_id):
                submodule = manifest["spec"]["distribution"]["modes"]["submodule"]
                self.assertEqual(manifest["spec"]["source"], submodule["repository"])


if __name__ == "__main__":
    unittest.main()
