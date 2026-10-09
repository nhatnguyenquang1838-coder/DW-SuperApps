from __future__ import annotations

import importlib.util
import json
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
        manifests = dw_cli.manifests()
        lock = json.loads(
            (ROOT / "manifests/power-compatibility-lock.json").read_text(
                encoding="utf-8"
            )
        )["powers"]
        for power_id, manifest in manifests.items():
            with self.subTest(power_id=power_id):
                state = manifest["spec"]["distribution"]["providerState"]
                # Published distribution provenance and the workspace's source
                # integration gitlink are independently pinned. New source
                # integration commits do not silently republish old packages.
                self.assertEqual(
                    lock[power_id]["publishedSourceSha"], state["sourceCommit"]
                )
                self.assertRegex(state["sourceCommit"], r"^[0-9a-f]{40}$")
                self.assertTrue(state["sourceLock"])
                self.assertTrue(state["status"])

                # CI must still pin each source submodule via the root tree;
                # a nested checkout's HEAD is not integration evidence.
                gitlink = subprocess.check_output(
                    ["git", "ls-tree", "HEAD", manifest["spec"]["path"]],
                    cwd=ROOT,
                    text=True,
                ).strip().split()
                self.assertGreaterEqual(len(gitlink), 3)
                self.assertEqual("160000", gitlink[0])
                self.assertEqual("commit", gitlink[1])
                self.assertRegex(gitlink[2], r"^[0-9a-f]{40}$")

    def test_submodule_source_contract_remains_available_as_fallback(self) -> None:
        for power_id, manifest in dw_cli.manifests().items():
            with self.subTest(power_id=power_id):
                submodule = manifest["spec"]["distribution"]["modes"]["submodule"]
                self.assertEqual(manifest["spec"]["source"], submodule["repository"])


if __name__ == "__main__":
    unittest.main()
