from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".kiro" / "skills" / "dw-power-installation"


class KiroInstallationAssetTests(unittest.TestCase):
    def test_skill_and_agent_are_self_contained(self) -> None:
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        agent = json.loads(
            (ROOT / ".kiro" / "agents" / "dw-power-installation.json").read_text(encoding="utf-8")
        )
        self.assertIn("name: dw-power-installation", skill)
        self.assertIn("dw_python_init", skill)
        self.assertIn("python3", skill)
        self.assertIn("py -3", skill)
        self.assertIn('"$RELEASE_DIR/offline_release_installer.py"', skill)
        agent_prompt = (ROOT / ".kiro" / "agents" / "DW_POWER_INSTALLATION_AGENT.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("dw_python_init", agent_prompt)
        self.assertEqual("dw-power-installation", agent["name"])
        self.assertEqual("file://.kiro/agents/DW_POWER_INSTALLATION_AGENT.md", agent["prompt"])
        for resource in agent["resources"]:
            self.assertTrue((ROOT / resource.removeprefix("file://")).is_file(), resource)

    def test_workspace_init_runtime_includes_kiro_installation_assets(self) -> None:
        import scripts.dw_project_registry as registry

        self.assertIn(".kiro/skills/dw-power-installation", registry.RUNTIME_DIRS)
        self.assertIn(".kiro/agents", registry.RUNTIME_DIRS)


if __name__ == "__main__":
    unittest.main()
