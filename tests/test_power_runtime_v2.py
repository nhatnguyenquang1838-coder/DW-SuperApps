from __future__ import annotations

import argparse
import contextlib
import io
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("dw_cli", ROOT / "scripts" / "dw_cli.py")
assert SPEC is not None and SPEC.loader is not None
dw_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dw_cli)


class PowerRuntimeV2Tests(unittest.TestCase):
    def test_registered_power_ids(self) -> None:
        self.assertEqual({"gwc", "ua", "task-me", "bmad"}, set(dw_cli.manifests()))

    def test_manifests_use_v2_contract(self) -> None:
        expected_hosts = {
            "kiro",
            "codex",
            "copilot",
            "cline",
            "kilo",
            "claude",
            "custom",
            "cli",
        }
        for power_id, manifest in dw_cli.manifests().items():
            self.assertEqual("dw.superapps/v2", manifest["apiVersion"])
            self.assertEqual(power_id, manifest["metadata"]["id"])
            self.assertIn("description", manifest["metadata"])
            self.assertTrue(manifest["spec"]["entrypoints"]["skillCandidates"])
            self.assertEqual(expected_hosts, set(manifest["spec"]["hosts"]))
            self.assertIn(
                f"{manifest['spec']['runtimeDataRoot']}/**",
                manifest["spec"]["permissions"]["write"],
            )

    def test_dynamic_submodule_targets_exclude_external_power(self) -> None:
        powers = dw_cli.select_submodules("powers")
        systems = dw_cli.select_submodules("systems")
        self.assertEqual(5, len(powers))
        self.assertEqual(
            {"gwc", "ua", "task-me", "bmad", "dw-chatgpt-app"},
            {item["id"] for item in powers},
        )
        self.assertEqual(1, len(systems))
        self.assertEqual("rental-home", systems[0]["id"])

    def test_rental_home_enables_bmad(self) -> None:
        system = dw_cli.find_system("rental-home")
        self.assertIn("bmad", dw_cli.enabled_powers(system))
        manifest = dw_cli.manifests()["bmad"]
        self.assertEqual("projects/bmad", manifest["spec"]["path"])

    def test_cli_parses_v2_commands(self) -> None:
        parser = dw_cli.build_parser()
        cases = [
            ["workspace", "info"],
            ["power", "list"],
            ["power", "info", "task-me"],
            ["power", "help", "gwc"],
            ["power", "check", "all"],
            ["host", "list"],
            ["host", "install", "copilot"],
            ["host", "install", "bionics"],
            ["host", "status", "all"],
            ["provider", "install", "ollama", "--model", "test-model"],
            ["provider", "status", "all"],
            ["provider", "info", "ollama"],
            ["system", "list"],
            ["system", "powers", "rental-home"],
            ["skill", "bmad", "--help"],
            ["skill", "--help"],
            ["validate"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                parsed = parser.parse_args(argv)
                self.assertTrue(callable(parsed.handler))

    def test_power_help_contract_covers_user_questions(self) -> None:
        for power_id in ("gwc", "ua", "task-me", "bmad"):
            with self.subTest(power_id=power_id):
                data = dw_cli.power_help_data(power_id)
                self.assertEqual(power_id, data["id"])
                self.assertTrue(data["what"])
                self.assertTrue(data["why"])
                for key in ("when", "how", "gives", "doesNot"):
                    self.assertTrue(data[key])
                    self.assertTrue(all(isinstance(item, str) for item in data[key]))
                self.assertEqual(f"/dw-{power_id}", data["nativeAlias"])

    def test_power_help_is_read_only_user_facing_output(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = dw_cli.power_help(argparse.Namespace(power_id="ua", json=False))
        self.assertEqual(0, result)
        rendered = output.getvalue()
        self.assertIn("What:", rendered)
        self.assertIn("When:", rendered)
        self.assertIn("How:", rendered)
        self.assertIn("Why:", rendered)
        self.assertIn("User gets:", rendered)
        self.assertIn("Does not:", rendered)
        self.assertIn("/dw-ua", rendered)

    def test_cli_rejects_removed_prompt_command(self) -> None:
        parser = dw_cli.build_parser()
        with self.assertRaises(SystemExit) as raised:
            parser.parse_args(
                [
                    "power",
                    "prompt",
                    "ua",
                    "--system",
                    "rental-home",
                    "--task",
                    "Analyze architecture",
                ]
            )
        self.assertNotEqual(raised.exception.code, 0)
        self.assertFalse(hasattr(dw_cli, "power_prompt"))

    def test_wrapper_is_host_neutral(self) -> None:
        manifest = dw_cli.manifests()["task-me"]
        content = dw_cli.wrapper_content(
            "codex",
            "task-me",
            manifest,
            ROOT
            / "powers"
            / "task-me"
            / ".kiro"
            / "skills"
            / "implementation-task-architect",
            "source-submodule-fallback",
        )
        forbidden = "dw power " + "prompt"
        self.assertIn(dw_cli.GENERATED_MARKER, content)
        self.assertIn("workspace.yaml", content)
        self.assertIn(".task-me", content)
        self.assertIn("This Power is already active", content)
        self.assertIn("Apply that Power", content)
        self.assertNotIn(forbidden, content)

    def test_provider_config_uses_workspace_defaults(self) -> None:
        provider = dw_cli.find_provider("ollama")
        config = dw_cli.provider_config(
            provider,
            argparse.Namespace(model=None, base_url=None, api_key=None),
        )
        self.assertEqual("openai-compatible", config["protocol"])
        self.assertEqual("http://localhost:11434/v1", config["baseUrl"])
        self.assertTrue(config["model"])


if __name__ == "__main__":
    unittest.main()
