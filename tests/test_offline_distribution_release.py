import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OfflineDistributionReleaseTests(unittest.TestCase):
    def test_build_verify_install_conflict_force_and_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td).resolve()
            source = temp / "source"
            (source / "projects" / "task-me").mkdir(parents=True)
            (source / "projects" / "bmad").mkdir(parents=True)
            (source / ".kiro").mkdir(parents=True)
            (source / "templates" / "power-runtime").mkdir(parents=True)
            (source / "projects" / "task-me" / "MANIFEST.json").write_text('{"id":"task-me"}\n')
            (source / "projects" / "bmad" / "MANIFEST.json").write_text('{"id":"bmad"}\n')
            (source / ".kiro" / "agent.json").write_text('{"host":"kiro"}\n')
            (source / "templates" / "power-runtime" / "runtime.txt").write_text("runtime\n")

            config = temp / "components.json"
            config.write_text(json.dumps({
                "components": [
                    {"name": "task-me", "source": "projects/task-me", "package": "task-me.zip"},
                    {"name": "bmad", "source": "projects/bmad", "package": "bmad.zip"},
                    {"name": "kiro-adapter", "source": ".kiro", "package": "kiro-adapter.zip"},
                    {"name": "bootstrap", "source": "templates/power-runtime", "package": "bootstrap.zip"},
                ]
            }))

            out = temp / "out"
            subprocess.run([
                sys.executable, str(ROOT / "scripts" / "release_builder.py"),
                "--version", "1.0.0",
                "--source-root", str(source),
                "--config", str(config),
                "--output", str(out),
                "--source-ref", "test",
                "--source-sha", "abc123",
            ], check=True)

            release = out / "dw-super-offline-1.0.0"
            for evidence in ("MANIFEST.json", "SOURCE_LOCK.json", "SHA256SUMS.txt", "VALIDATION_REPORT.json"):
                self.assertTrue((release / evidence).is_file())

            subprocess.run([
                sys.executable, str(ROOT / "scripts" / "offline_release_installer.py"),
                "verify",
                "--release", str(release),
            ], check=True)

            workspace = temp / "workspace"
            (workspace / ".task-me").mkdir(parents=True)
            (workspace / ".task-me" / "state.json").write_text("{}\n")
            subprocess.run([
                sys.executable, str(ROOT / "scripts" / "offline_release_installer.py"),
                "install",
                "--release", str(release),
                "--workspace", str(workspace),
            ], check=True)

            self.assertTrue((workspace / ".dw" / "powers" / "task-me" / "MANIFEST.json").is_file())
            self.assertTrue((workspace / ".task-me" / "state.json").is_file())

            blocked = subprocess.run([
                sys.executable, str(ROOT / "scripts" / "offline_release_installer.py"),
                "install",
                "--release", str(release),
                "--workspace", str(workspace),
            ])
            self.assertNotEqual(blocked.returncode, 0)

            subprocess.run([
                sys.executable, str(ROOT / "scripts" / "offline_release_installer.py"),
                "install",
                "--release", str(release),
                "--workspace", str(workspace),
                "--force",
            ], check=True)

            subprocess.run([
                sys.executable, str(ROOT / "scripts" / "offline_release_installer.py"),
                "rollback",
                "--workspace", str(workspace),
            ], check=True)


if __name__ == "__main__":
    unittest.main()
