from __future__ import annotations

import argparse
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dw_cli", ROOT / "scripts" / "dw_cli.py")
assert SPEC is not None and SPEC.loader is not None
dw_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dw_cli)


class PowerRuntimeV2Tests(unittest.TestCase):
    def test_registered_power_ids(self) -> None:
        self.assertEqual({"gwc", "ua", "task-me"}, set(dw_cli.manifests()))

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

    def test_dynamic_submodule_targets(self) -> None:
        powers = dw_cli.select_submodules("powers")
        systems = dw_cli.select_submodules("systems")
        self.assertEqual(3, len(powers))
        self.assertEqual(1, len(systems))
        self.assertEqual("rental-home", systems[0]["id"])

    def test_cli_parses_v2_commands(self) -> None:
        parser = dw_cli.build_parser()
        cases = [
            ["workspace", "info"],
            ["power", "list"],
            ["power", "info", "task-me"],
            [
                "power",
                "prompt",
                "ua",
                "--system",
                "rental-home",
                "--task",
                "Analyze architecture",
            ],
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
            ["validate"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                parsed = parser.parse_args(argv)
                self.assertTrue(callable(parsed.handler))

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
        )
        self.assertIn(dw_cli.GENERATED_MARKER, content)
        self.assertIn("workspace.yaml", content)
        self.assertIn(".task-me", content)
        self.assertIn("dw power prompt task-me", content)

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
