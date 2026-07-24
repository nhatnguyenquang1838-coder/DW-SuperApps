from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dw_power_package", ROOT / "scripts" / "dw_power_package.py"
)
assert SPEC is not None and SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def file_record(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


class PowerPackageConsumerTests(unittest.TestCase):
    def package(self, root: Path, version: str) -> Path:
        package = root / f"task-me-{version}"
        (package / "lib").mkdir(parents=True)
        (package / "skill").mkdir()
        shutil.copyfile(
            ROOT / "templates" / "power-runtime" / "lib" / "power_runtime.py",
            package / "lib" / "power_runtime.py",
        )
        (package / "skill" / "SKILL.md").write_text(
            "---\nname: test-task-me\n---\n", encoding="utf-8"
        )
        files = [
            file_record(package, package / "lib" / "power_runtime.py"),
            file_record(package, package / "skill" / "SKILL.md"),
        ]
        (package / "MANIFEST.json").write_text(
            json.dumps(
                {
                    "metadata": {"powerId": "task-me", "version": version},
                    "spec": {
                        "runtimeDataRoot": ".task-me",
                        "entrypoints": ["skill/SKILL.md"],
                    },
                    "files": files,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return package

    def args(self, **values: object) -> argparse.Namespace:
        defaults: dict[str, object] = {
            "power_id": "task-me",
            "source": "package",
            "package": None,
            "checksum": None,
            "version": None,
            "target": ".",
            "config": None,
            "contract": None,
            "require_config": False,
            "include_runtime": False,
            "yes": False,
        }
        defaults.update(values)
        return argparse.Namespace(**defaults)

    def test_install_upgrade_history_rollback_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "consumer"
            target.mkdir()
            v1 = self.package(root, "1.0.0")
            v2 = self.package(root, "2.0.0")

            result = consumer.install(
                self.args(package=str(v1), target=str(target))
            )
            self.assertEqual("INSTALLED", result["status"])
            self.assertTrue((target / ".task-me").is_dir())

            config = root / "config.yaml"
            contract = root / "contract.yaml"
            config.write_text("folderMode: per_task\n", encoding="utf-8")
            contract.write_text("authority: local\n", encoding="utf-8")
            configured = consumer.configure(
                self.args(
                    config=str(config),
                    contract=str(contract),
                    target=str(target),
                )
            )
            self.assertEqual("CONFIGURED", configured["status"])
            self.assertEqual(
                "PASS",
                consumer.doctor(self.args(target=str(target), require_config=True))["status"],
            )

            consumer.install(self.args(package=str(v2), target=str(target)))
            history = consumer.history(self.args(target=str(target)))["history"]
            self.assertEqual("1.0.0", history[0]["version"])

            rolled_back = consumer.rollback(
                self.args(target=str(target), version="1.0.0")
            )
            self.assertEqual("ROLLED_BACK", rolled_back["status"])
            self.assertEqual(
                "1.0.0",
                consumer.doctor(self.args(target=str(target)))["version"],
            )

            removed = consumer.uninstall(self.args(target=str(target)))
            self.assertEqual("UNINSTALLED", removed["status"])
            self.assertTrue((target / ".task-me").is_dir())

    def test_archive_checksum_and_path_safety(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self.package(root, "1.0.0")
            archive = root / "task-me.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                for path in sorted(package.rglob("*")):
                    if path.is_file():
                        bundle.write(path, path.relative_to(package))
            checksum = root / "task-me.zip.sha256"
            checksum.write_text(
                f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n",
                encoding="utf-8",
            )
            target = root / "consumer"
            target.mkdir()
            result = consumer.install(
                self.args(
                    package=str(archive),
                    checksum=str(checksum),
                    target=str(target),
                )
            )
            self.assertEqual("INSTALLED", result["status"])

            malicious = root / "malicious.zip"
            with zipfile.ZipFile(malicious, "w") as bundle:
                bundle.writestr("../escape.txt", "no")
            with self.assertRaises(consumer.ConsumerError):
                consumer.safe_extract(malicious, root / "bad")

    def test_parser_exposes_package_lifecycle(self) -> None:
        parser = consumer.parser()
        for command in ("install", "configure", "doctor", "history", "rollback", "uninstall"):
            with self.subTest(command=command):
                parsed = parser.parse_args([command, "task-me"])
                self.assertTrue(callable(parsed.handler))


if __name__ == "__main__":
    unittest.main()
