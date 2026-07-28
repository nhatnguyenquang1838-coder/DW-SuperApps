from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dw_entry", ROOT / "scripts" / "dw_entry.py")
assert SPEC is not None and SPEC.loader is not None
dw_entry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dw_entry)


class OneClickCommandTests(unittest.TestCase):
    def test_oneclick_commands_parse(self) -> None:
        parser = dw_entry.build_parser()
        cases = [
            ["init", "all", "--skip-deps", "--skip-providers"],
            ["init", "all", "--host", "claude", "--model", "local-model"],
            ["sync", "all"],
            ["sync", "powers", "--pin"],
            ["clean", "all"],
            ["clean", "runtime", "--yes"],
            ["status", "all"],
            ["doctor", "all", "--offline"],
            ["doctor", "all", "--probe-providers"],
            ["reset", "all", "--yes"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertTrue(callable(args.handler))

    def test_all_host_scope_is_expanded(self) -> None:
        self.assertEqual(
            {
                "kiro",
                "codex",
                "copilot",
                "cline",
                "kilo",
                "claude",
                "custom",
            },
            set(dw_entry.HOSTS),
        )

    def test_clean_all_preserves_runtime_by_default(self) -> None:
        self.assertEqual({"adapters", "cache"}, dw_entry.clean_plan("all"))
        self.assertNotIn("runtime", dw_entry.clean_plan("all"))
        self.assertEqual(
            {"adapters", "cache", "runtime"},
            dw_entry.clean_plan("all", include_runtime=True),
        )


if __name__ == "__main__":
    unittest.main()
