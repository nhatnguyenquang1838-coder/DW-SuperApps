from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = "dw power " + "prompt"


class PowerPromptRemovalTests(unittest.TestCase):
    def test_command_is_not_registered(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/dw_cli.py"),
                "power",
                "prompt",
                "gwc",
                "--system",
                "rental-home",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Use the `gwc` Power", result.stdout)

    def test_active_generators_do_not_emit_prompt_export(self) -> None:
        for relative in ("scripts/dw_cli.py", "scripts/dw_workspace_dist.py", "bin/dw"):
            content = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn(FORBIDDEN, content, relative)
            self.assertNotIn("Generate a complete task prompt", content, relative)
            self.assertNotIn("Generate a host-neutral prompt", content, relative)

    def test_root_contract_requires_direct_activation(self) -> None:
        content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Native Power activation", content)
        self.assertIn("does not generate task prompts", content)


if __name__ == "__main__":
    unittest.main()
