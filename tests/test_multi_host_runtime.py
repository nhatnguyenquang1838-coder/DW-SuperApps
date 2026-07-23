from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dw_cli_multi", ROOT / "scripts" / "dw_cli.py")
assert SPEC is not None and SPEC.loader is not None
dw_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dw_cli)


class MultiHostRuntimeTests(unittest.TestCase):
    def test_workspace_registers_supported_hosts(self) -> None:
        expected = {
            "kiro",
            "codex",
            "copilot",
            "cline",
            "kilo",
            "claude",
            "custom",
        }
        self.assertEqual(expected, set(dw_cli.configured_hosts()))

    def test_custom_agent_aliases(self) -> None:
        self.assertEqual("custom", dw_cli.normalize_host("bionics"))
        self.assertEqual("custom", dw_cli.normalize_host("biotic"))
        self.assertEqual("custom", dw_cli.normalize_host("ollama"))

    def test_host_layouts_are_distinct(self) -> None:
        expected_fragments = {
            "kiro": ".kiro/skills",
            "codex": ".codex/skills",
            "copilot": ".github/instructions",
            "cline": ".clinerules",
            "kilo": ".kilo/rules",
            "claude": ".claude/skills",
            "custom": ".agents/skills",
        }
        for host, fragment in expected_fragments.items():
            with self.subTest(host=host):
                paths = [path.as_posix() for path in dw_cli.host_expected_paths(host)]
                self.assertTrue(any(fragment in path for path in paths))

    def test_instruction_hosts_include_canonical_routing(self) -> None:
        for host in ("copilot", "cline", "kilo", "claude", "custom"):
            with self.subTest(host=host):
                content = dw_cli.host_instruction_content(host)
                self.assertIn("AGENTS.md", content)
                self.assertIn("workspace.yaml", content)
                self.assertIn("dw power prompt", content)


if __name__ == "__main__":
    unittest.main()
