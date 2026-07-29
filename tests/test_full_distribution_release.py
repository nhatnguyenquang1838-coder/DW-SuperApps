from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

POWER_SPEC = importlib.util.spec_from_file_location("power_dist", ROOT / "scripts" / "power_dist.py")
assert POWER_SPEC is not None and POWER_SPEC.loader is not None
power_dist = importlib.util.module_from_spec(POWER_SPEC)
sys.modules["power_dist"] = power_dist
POWER_SPEC.loader.exec_module(power_dist)

FULL_SPEC = importlib.util.spec_from_file_location(
    "full_distribution_release", ROOT / "scripts" / "full_distribution_release.py"
)
assert FULL_SPEC is not None and FULL_SPEC.loader is not None
full_distribution_release = importlib.util.module_from_spec(FULL_SPEC)
FULL_SPEC.loader.exec_module(full_distribution_release)

OFFLINE_SPEC = importlib.util.spec_from_file_location(
    "offline_release_installer", ROOT / "scripts" / "offline_release_installer.py"
)
assert OFFLINE_SPEC is not None and OFFLINE_SPEC.loader is not None
offline_release_installer = importlib.util.module_from_spec(OFFLINE_SPEC)
OFFLINE_SPEC.loader.exec_module(offline_release_installer)


class FullDistributionReleaseTests(unittest.TestCase):
    def test_assemble_is_verifiable_and_bundle_is_installable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            (source / "skills/demo").mkdir(parents=True)
            (source / "skills/demo/SKILL.md").write_text("# Demo\n", encoding="utf-8")
            (source / "README.md").write_text("demo\n", encoding="utf-8")
            recipe = ROOT / "tests/fixtures/power-distribution/valid-recipe.yaml"
            args = type(
                "Args",
                (),
                {
                    "recipe": str(recipe),
                    "source": str(source),
                    "output": str(root / "built"),
                    "version": "power-v1.0.0",
                    "source_repository": "example/demo",
                    "source_ref": "main",
                    "source_sha": "abcdef0123456789",
                    "source_date_epoch": 1700000000,
                    "templates_root": str(ROOT / "templates/power-runtime"),
                },
            )()
            built = power_dist.build_command(args)

            distribution = root / "distribution"
            (distribution / "staging").mkdir(parents=True)
            shutil.copytree(built["staging_root"], distribution / "staging" / "gwc-power-v1.0.0")
            (distribution / "assets").mkdir()
            shutil.copy2(built["archive"], distribution / "assets/gwc-power-v1.0.0.zip")
            shutil.copy2(built["checksum"], distribution / "assets/gwc-power-v1.0.0.zip.sha256")
            (distribution / "validation-report.json").write_text(
                json.dumps({"powers": {"gwc": {"status": "PASS"}}}) + "\n", encoding="utf-8"
            )

            release_args = type(
                "ReleaseArgs",
                (),
                {
                    "distribution_root": str(distribution),
                    "output": str(root / "release"),
                    "version": "1.0.0",
                    "source_ref": "main",
                    "source_sha": "abcdef0123456789",
                    "source_date_epoch": 1700000000,
                    "powers": ["gwc"],
                },
            )()
            result = full_distribution_release.assemble(release_args)
            release = Path(result["releaseRoot"])
            offline_release_installer.verify_release(release)
            self.assertTrue((release / "dw-superapps-full-1.0.0.zip").is_file())
            self.assertTrue((release / "KIRO_OFFLINE_INSTALL_PROMPT.md").is_file())
            self.assertTrue(
                (release / "kiro/skills/dw-power-installation/SKILL.md").is_file()
            )
            self.assertTrue((release / "kiro/agents/dw-power-installation.json").is_file())
            manifest = json.loads((release / "MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual("KIRO_OFFLINE_INSTALL_PROMPT.md", manifest["spec"]["kiroPrompt"])
            self.assertEqual(
                "kiro/skills/dw-power-installation/SKILL.md",
                manifest["spec"]["kiroInstallation"]["skill"],
            )
            self.assertEqual("offline-local", manifest["spec"]["registrationMode"])
            self.assertIn("assets/gwc-power-v1.0.0.zip", (release / "SHA256SUMS.txt").read_text())

            extracted = root / "extracted"
            with zipfile.ZipFile(release / "dw-superapps-full-1.0.0.zip") as archive:
                archive.extractall(extracted)
            offline_release_installer.verify_release(extracted)


if __name__ == "__main__":
    unittest.main()
