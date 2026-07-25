from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
HOST_ROOT = ROOT / "hosts" / "openclaw-acpx"


class OpenClawAcpxRuntimeTests(unittest.TestCase):
    def test_manifest_registers_exact_worker_allowlist(self) -> None:
        manifest = yaml.safe_load((HOST_ROOT / "manifest.yaml").read_text(encoding="utf-8"))
        spec = manifest["spec"]
        self.assertEqual("openclaw", spec["host"])
        self.assertEqual("acpx", spec["backend"])
        self.assertEqual(
            ["codex", "claude", "kiro", "kilocode"],
            [worker["id"] for worker in spec["workers"]],
        )

    def test_profile_is_fail_closed_and_bridges_are_disabled(self) -> None:
        profile = json.loads((HOST_ROOT / "openclaw.config.json").read_text(encoding="utf-8"))
        self.assertEqual(
            ["codex", "claude", "kiro", "kilocode"],
            profile["acp"]["allowedAgents"],
        )
        acpx = profile["plugins"]["entries"]["acpx"]
        self.assertTrue(acpx["enabled"])
        self.assertEqual("approve-reads", acpx["config"]["permissionMode"])
        self.assertEqual("fail", acpx["config"]["nonInteractivePermissions"])
        self.assertFalse(acpx["config"]["pluginToolsMcpBridge"])
        self.assertFalse(acpx["config"]["openClawToolsMcpBridge"])

    def test_contract_schemas_are_valid_draft_2020_12(self) -> None:
        for name in ("work-order.schema.json", "worker-result.schema.json"):
            with self.subTest(schema=name):
                schema = json.loads((HOST_ROOT / "schemas" / name).read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)

    def test_installers_use_official_plugin_and_strict_allowlist(self) -> None:
        bash = (HOST_ROOT / "install.sh").read_text(encoding="utf-8")
        powershell = (HOST_ROOT / "install.ps1").read_text(encoding="utf-8")
        for content in (bash, powershell):
            with self.subTest(installer=content.splitlines()[0]):
                self.assertIn("@openclaw/acpx", content)
                self.assertIn('["codex","claude","kiro","kilocode"]', content)
                self.assertIn("permissionMode approve-reads", content)
                self.assertIn("nonInteractivePermissions fail", content)
                self.assertIn("pluginToolsMcpBridge false", content)
                self.assertIn("openClawToolsMcpBridge false", content)

    def test_workspace_registers_openclaw_orchestrator(self) -> None:
        workspace = yaml.safe_load((ROOT / "workspace.yaml").read_text(encoding="utf-8"))
        orchestrators = {item["id"]: item for item in workspace["orchestrators"]}
        runtime = orchestrators["openclaw-acpx"]
        self.assertEqual("hosts/openclaw-acpx", runtime["path"])
        self.assertEqual("acpx", runtime["backend"])
        self.assertEqual(
            ["codex", "claude", "kiro", "kilocode"],
            runtime["workers"],
        )


if __name__ == "__main__":
    unittest.main()
