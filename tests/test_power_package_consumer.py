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
    def package(self, root: Path, version: str, power_id: str = "task-me") -> Path:
        package = root / f"{power_id}-{version}"
        (package / "lib").mkdir(parents=True)
        (package / "skill").mkdir()
        shutil.copyfile(
            ROOT / "templates" / "power-runtime" / "lib" / "power_runtime.py",
            package / "lib" / "power_runtime.py",
        )
        (package / "skill" / "SKILL.md").write_text(
            f"---\nname: test-{power_id}\n---\n", encoding="utf-8"
        )
        files = [
            file_record(package, package / "lib" / "power_runtime.py"),
            file_record(package, package / "skill" / "SKILL.md"),
        ]
        runtime_root = ".task-me" if power_id == "task-me" else f".{power_id}"
        (package / "MANIFEST.json").write_text(
            json.dumps(
                {
                    "metadata": {"powerId": power_id, "version": version},
                    "spec": {
                        "runtimeDataRoot": runtime_root,
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
            "store_root": None,
            "config": None,
            "contract": None,
            "require_config": False,
            "include_runtime": False,
            "yes": False,
        }
        defaults.update(values)
        return argparse.Namespace(**defaults)

    def test_split_store_runtime_config_history_rollback_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "workspace" / ".dw" / "powers"
            target = root / "systems" / "consumer"
            target.mkdir(parents=True)
            v1 = self.package(root, "1.0.0")
            v2 = self.package(root, "2.0.0")

            result = consumer.install(
                self.args(package=str(v1), target=str(target), store_root=str(store))
            )
            self.assertEqual("INSTALLED", result["status"])
            self.assertTrue((store / "task-me").is_dir())
            self.assertTrue((target / ".task-me").is_dir())
            self.assertFalse((target / ".dw").exists())

            config = root / "config.yaml"
            contract = root / "contract.yaml"
            config.write_text("folderMode: per_task\n", encoding="utf-8")
            contract.write_text("authority: local\n", encoding="utf-8")
            configured = consumer.configure(
                self.args(
                    config=str(config),
                    contract=str(contract),
                    target=str(target),
                    store_root=str(store),
                )
            )
            self.assertEqual("CONFIGURED", configured["status"])
            self.assertTrue((target / ".task-me" / "config" / "config.yaml").is_file())
            self.assertFalse((target / ".dw").exists())
            self.assertEqual(
                "PASS",
                consumer.doctor(
                    self.args(
                        target=str(target),
                        store_root=str(store),
                        require_config=True,
                    )
                )["status"],
            )

            consumer.install(
                self.args(package=str(v2), target=str(target), store_root=str(store))
            )
            history = consumer.history(self.args(store_root=str(store)))["history"]
            self.assertEqual("1.0.0", history[0]["version"])

            rolled_back = consumer.rollback(
                self.args(store_root=str(store), version="1.0.0")
            )
            self.assertEqual("ROLLED_BACK", rolled_back["status"])
            self.assertEqual(
                "1.0.0",
                consumer.doctor(
                    self.args(target=str(target), store_root=str(store))
                )["version"],
            )

            removed = consumer.uninstall(
                self.args(target=str(target), store_root=str(store))
            )
            self.assertEqual("UNINSTALLED", removed["status"])
            self.assertFalse((store / "task-me").exists())
            self.assertTrue((target / ".task-me").is_dir())
            self.assertFalse((target / ".dw").exists())

    def test_shared_package_detach_preserves_other_system(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "workspace" / ".dw" / "powers"
            first = root / "systems" / "first"
            second = root / "systems" / "second"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            package = self.package(root, "1.0.0")
            for target in (first, second):
                consumer.install(
                    self.args(
                        package=str(package), target=str(target), store_root=str(store)
                    )
                )

            detached = consumer.uninstall(
                self.args(target=str(first), store_root=str(store))
            )
            self.assertEqual("DETACHED", detached["status"])
            self.assertTrue((store / "task-me").is_dir())
            self.assertEqual(
                "PASS",
                consumer.doctor(
                    self.args(target=str(second), store_root=str(store))
                )["status"],
            )

    def test_legacy_target_install_is_reported_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "workspace" / ".dw" / "powers"
            target = root / "systems" / "consumer"
            legacy = target / ".dw" / "powers" / "task-me"
            legacy.mkdir(parents=True)
            legacy_file = legacy / "legacy.txt"
            legacy_file.write_text("preserve me\n", encoding="utf-8")
            before = hashlib.sha256(legacy_file.read_bytes()).hexdigest()
            package = self.package(root, "1.0.0")

            result = consumer.install(
                self.args(
                    package=str(package), target=str(target), store_root=str(store)
                )
            )
            self.assertEqual("LEGACY_TARGET_INSTALL", result["legacy"]["status"])
            self.assertEqual(before, hashlib.sha256(legacy_file.read_bytes()).hexdigest())
            self.assertTrue((store / "task-me").is_dir())

    def test_offline_package_is_discovered_from_workspace_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "workspace" / ".dw" / "powers"
            inbox = store.parent / "inbox" / "powers" / "task-me"
            inbox.mkdir(parents=True)
            package = self.package(root, "1.0.0")
            archive = inbox / "task-me-1.0.0.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                for path in sorted(package.rglob("*")):
                    if path.is_file():
                        bundle.write(path, path.relative_to(package))
            checksum = archive.with_name(archive.name + ".sha256")
            checksum.write_text(
                f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n",
                encoding="utf-8",
            )
            target = root / "systems" / "consumer"
            target.mkdir(parents=True)
            result = consumer.install(
                self.args(source="package", target=str(target), store_root=str(store))
            )
            self.assertEqual("INSTALLED", result["status"])
            self.assertEqual(str(store / "task-me"), result["install_root"])
            self.assertFalse((target / ".dw").exists())

    def test_archive_checksum_overlap_and_path_safety(self) -> None:
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
            store = root / "workspace" / ".dw" / "powers"
            result = consumer.install(
                self.args(
                    package=str(archive),
                    checksum=str(checksum),
                    target=str(target),
                    store_root=str(store),
                )
            )
            self.assertEqual("INSTALLED", result["status"])

            with self.assertRaisesRegex(consumer.ConsumerError, "BLOCKED_STORE"):
                consumer.install(
                    self.args(
                        package=str(package),
                        target=str(target),
                        store_root=str(target / ".dw" / "powers"),
                    )
                )

            malicious = root / "malicious.zip"
            with zipfile.ZipFile(malicious, "w") as bundle:
                bundle.writestr("../escape.txt", "no")
            with self.assertRaises(consumer.ConsumerError):
                consumer.safe_extract(malicious, root / "bad")

    def test_parser_exposes_split_lifecycle_and_store_override(self) -> None:
        parser = consumer.parser()
        for command in ("install", "configure", "doctor", "history", "rollback", "uninstall"):
            with self.subTest(command=command):
                parsed = parser.parse_args([command, "task-me", "--store-root", "/tmp/store"])
                self.assertTrue(callable(parsed.handler))
                self.assertEqual("/tmp/store", parsed.store_root)


if __name__ == "__main__":
    unittest.main()
