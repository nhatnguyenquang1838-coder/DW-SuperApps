from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
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

    def test_installers_use_official_plugin_strict_allowlist_and_readback(self) -> None:
        bash = (HOST_ROOT / "install.sh").read_text(encoding="utf-8")
        powershell = (HOST_ROOT / "install.ps1").read_text(encoding="utf-8")
        for content in (bash, powershell):
            with self.subTest(installer=content.splitlines()[0]):
                self.assertIn("@openclaw/acpx", content)
                self.assertIn('["codex","claude","kiro","kilocode"]', content)
                self.assertIn("approve-reads", content)
                self.assertIn("nonInteractivePermissions", content)
                self.assertIn("pluginToolsMcpBridge", content)
                self.assertIn("openClawToolsMcpBridge", content)
                self.assertIn("config", content)
                self.assertIn("validate", content)
                self.assertIn("get", content)

        self.assertIn("--profile", bash)
        self.assertIn("--verify-only", bash)
        self.assertIn("OPENCLAW_ARGS", bash)
        self.assertIn("[string]$Profile", powershell)
        self.assertIn("[switch]$VerifyOnly", powershell)
        self.assertIn("$OpenClawPrefix", powershell)

    def test_bash_verify_only_targets_profile_and_does_not_write(self) -> None:
        expected = {
            "plugins.entries.acpx.enabled": True,
            "acp.enabled": True,
            "acp.dispatch.enabled": True,
            "acp.backend": "acpx",
            "acp.defaultAgent": "codex",
            "acp.allowedAgents": ["codex", "claude", "kiro", "kilocode"],
            "session.threadBindings.enabled": True,
            "session.threadBindings.idleHours": 24,
            "session.threadBindings.maxAgeHours": 0,
            "session.threadBindings.spawnSessions": True,
            "plugins.entries.acpx.config.permissionMode": "approve-reads",
            "plugins.entries.acpx.config.nonInteractivePermissions": "fail",
            "plugins.entries.acpx.config.probeAgent": "codex",
            "plugins.entries.acpx.config.timeoutSeconds": 120,
            "plugins.entries.acpx.config.pluginToolsMcpBridge": False,
            "plugins.entries.acpx.config.openClawToolsMcpBridge": False,
            "skills.load.extraDirs": [
                str(ROOT / ".agents" / "skills"),
                str(HOST_ROOT / "skills"),
            ],
            "skills.load.watch": True,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir()
            log_path = temp_path / "openclaw.log"
            fake_openclaw = fake_bin / "openclaw"

            case_lines = "\n".join(
                f"    {path}) printf '%s\\n' '{json.dumps(value, separators=(',', ':'))}' ;;"
                for path, value in expected.items()
            )
            fake_openclaw.write_text(
                f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$OPENCLAW_TEST_LOG"
[[ "$1" == "--profile" && "$2" == "gwc" ]] || exit 9
shift 2
if [[ "$1" == "config" && "$2" == "file" ]]; then
  echo "/tmp/openclaw-gwc.json"
elif [[ "$1" == "config" && "$2" == "validate" ]]; then
  echo "Config valid"
elif [[ "$1" == "config" && "$2" == "get" && "$4" == "--json" ]]; then
  case "$3" in
{case_lines}
    *) exit 8 ;;
  esac
else
  exit 7
fi
""",
                encoding="utf-8",
            )
            fake_openclaw.chmod(
                fake_openclaw.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["OPENCLAW_TEST_LOG"] = str(log_path)

            result = subprocess.run(
                [
                    "bash",
                    str(HOST_ROOT / "install.sh"),
                    "--profile",
                    "gwc",
                    "--verify-only",
                ],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            calls = log_path.read_text(encoding="utf-8").splitlines()
            self.assertTrue(calls)
            self.assertTrue(all(call.startswith("--profile gwc ") for call in calls))
            self.assertIn("--profile gwc config file", calls)
            self.assertIn("--profile gwc config validate", calls)
            self.assertNotIn("config set", "\n".join(calls))
            self.assertNotIn("plugins install", "\n".join(calls))
            self.assertIn("Verification completed for profile: gwc", result.stdout)

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
