from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("power_dist", ROOT / "scripts" / "power_dist.py")
assert SPEC is not None and SPEC.loader is not None
power_dist = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(power_dist)


class PowerRuntimeInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        (self.source / "skills/demo").mkdir(parents=True)
        (self.source / "skills/demo/SKILL.md").write_text("# Demo\n", encoding="utf-8")
        (self.source / "README.md").write_text("demo\n", encoding="utf-8")
        recipe = power_dist.load_structured(
            ROOT / "tests" / "fixtures" / "power-distribution" / "valid-recipe.yaml"
        )
        self.package = self.root / "package"
        power_dist.build_staging_tree(
            recipe,
            self.source,
            self.package,
            version="power-v1.0.0",
            source_repository="example/demo",
            source_ref="main",
            source_sha="abcdef0123456789",
            source_date_epoch=1700000000,
            templates_root=ROOT / "templates" / "power-runtime",
        )
        self.runtime = self.package / "lib" / "power_runtime.py"
        self.consumer = self.root / "consumer"
        self.consumer.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_runtime(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.runtime), *args],
            check=check,
            text=True,
            capture_output=True,
        )

    def test_install_configure_doctor_and_uninstall_preserve_runtime(self) -> None:
        installed = self.run_runtime("install", "--target", str(self.consumer))
        install_payload = json.loads(installed.stdout)
        install_root = Path(install_payload["install_root"])
        self.assertTrue((install_root / ".dw-managed.json").is_file())
        self.assertTrue((self.consumer / ".demo").is_dir())

        config = self.root / "config.yaml"
        contract = self.root / "contract.yaml"
        config.write_text("enabled: true\n", encoding="utf-8")
        contract.write_text("allowExternalWrites: false\n", encoding="utf-8")
        self.run_runtime(
            "configure",
            "--target",
            str(self.consumer),
            "--config",
            str(config),
            "--contract",
            str(contract),
        )
        doctor = self.run_runtime(
            "doctor", "--target", str(self.consumer), "--require-config"
        )
        self.assertEqual("PASS", json.loads(doctor.stdout)["status"])

        self.run_runtime("install", "--target", str(self.consumer))
        history = self.consumer / ".dw" / "history" / "demo"
        self.assertTrue(any(history.iterdir()))

        self.run_runtime("uninstall", "--target", str(self.consumer))
        self.assertFalse((self.consumer / ".dw" / "powers" / "demo").exists())
        self.assertTrue((self.consumer / ".demo").exists())

    def test_unmanaged_install_is_not_overwritten(self) -> None:
        unmanaged = self.consumer / ".dw" / "powers" / "demo"
        unmanaged.mkdir(parents=True)
        (unmanaged / "mine.txt").write_text("do not replace", encoding="utf-8")
        result = self.run_runtime("install", "--target", str(self.consumer), check=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("unmanaged", result.stderr)

    def test_destructive_runtime_removal_requires_yes(self) -> None:
        self.run_runtime("install", "--target", str(self.consumer))
        result = self.run_runtime(
            "uninstall",
            "--target",
            str(self.consumer),
            "--include-runtime",
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertTrue((self.consumer / ".demo").exists())

        self.run_runtime(
            "uninstall",
            "--target",
            str(self.consumer),
            "--include-runtime",
            "--yes",
        )
        self.assertFalse((self.consumer / ".demo").exists())


if __name__ == "__main__":
    unittest.main()
