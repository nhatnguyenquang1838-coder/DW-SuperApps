from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location(
    "dw_project_registry",
    SCRIPTS / "dw_project_registry.py",
)
assert SPEC is not None and SPEC.loader is not None
registry = importlib.util.module_from_spec(SPEC)
sys.modules["dw_project_registry"] = registry
SPEC.loader.exec_module(registry)

ADD_SPEC = importlib.util.spec_from_file_location(
    "dw_project_add",
    SCRIPTS / "dw_project_add.py",
)
assert ADD_SPEC is not None and ADD_SPEC.loader is not None
project_add = importlib.util.module_from_spec(ADD_SPEC)
ADD_SPEC.loader.exec_module(project_add)

INIT_SPEC = importlib.util.spec_from_file_location(
    "dw_workspace_init",
    SCRIPTS / "dw_workspace_init.py",
)
assert INIT_SPEC is not None and INIT_SPEC.loader is not None
workspace_init = importlib.util.module_from_spec(INIT_SPEC)
INIT_SPEC.loader.exec_module(workspace_init)


class ProjectRegistryTests(unittest.TestCase):
    def workspace(self) -> dict:
        return {
            "projects": [
                {
                    "id": "alpha",
                    "path": "projects/alpha",
                    "source": "example/alpha",
                    "roles": ["product", "system"],
                },
                {
                    "id": "gwc",
                    "path": "powers/gwc",
                    "source": "example/gwc",
                    "roles": ["power-source"],
                },
            ],
            "powers": [
                {
                    "id": "gwc",
                    "project": "gwc",
                    "path": "powers/gwc",
                    "source": "example/gwc",
                }
            ],
            "systems": [
                {
                    "id": "alpha",
                    "project": "alpha",
                    "path": "projects/alpha",
                    "source": "example/alpha",
                }
            ],
        }

    def test_registry_resolves_project_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            projects = registry.validate_registry(
                self.workspace(),
                root=root,
                gitmodules={
                    "projects/alpha": "https://github.com/example/alpha.git",
                    "powers/gwc": "https://github.com/example/gwc.git",
                },
            )
            self.assertEqual("example/alpha", projects["alpha"]["source"])
            self.assertIn("system", projects["alpha"]["roles"])

    def test_unknown_project_reference_fails_closed(self) -> None:
        data = self.workspace()
        data["systems"][0]["project"] = "missing"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(registry.ProjectRegistryError):
                registry.validate_registry(data, root=Path(temporary))

    def test_template_has_no_product_specific_dependency(self) -> None:
        data = registry.template_workspace("example-super", "Example Super")
        rendered = str(data).lower()
        self.assertNotIn("rental", rendered)
        self.assertEqual([], data["projects"])
        self.assertEqual([], data["systems"])
        self.assertEqual(".dw/powers", data["distribution"]["storeRoot"])

    def test_workspace_init_is_non_destructive(self) -> None:
        with tempfile.TemporaryDirectory() as source_temp, tempfile.TemporaryDirectory() as target_temp:
            source = Path(source_temp)
            target = Path(target_temp)
            (source / "bin").mkdir()
            (source / "bin" / "dw").write_text("#!/bin/sh\n", encoding="utf-8")
            (source / "scripts").mkdir()
            (source / "scripts" / "marker.py").write_text("pass\n", encoding="utf-8")
            previous = registry.ROOT
            registry.ROOT = source
            try:
                args = argparse.Namespace(
                    target=str(target),
                    workspace_id="example-super",
                    name="Example Super",
                    in_place=False,
                )
                self.assertEqual(0, registry.workspace_init(args))
                self.assertTrue((target / "workspace.yaml").is_file())
                self.assertTrue((target / "bin" / "dw").is_file())
                self.assertTrue((target / ".git").exists())
            finally:
                registry.ROOT = previous

    def test_project_add_preflight_rejects_registered_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry.write_yaml(root / "workspace.yaml", self.workspace())
            (root / "manifests" / "powers").mkdir(parents=True)
            (root / "manifests" / "powers" / "gwc.yaml").write_text("{}\n", encoding="utf-8")
            previous_registry_root = registry.ROOT
            previous_add_root = project_add.ROOT
            registry.ROOT = root
            project_add.ROOT = root
            try:
                args = argparse.Namespace(
                    project_id="beta",
                    repository="example/beta",
                    path="projects/alpha",
                    role=["product"],
                    system=False,
                    system_id=None,
                    enable_powers="",
                )
                with self.assertRaises(registry.ProjectRegistryError):
                    project_add.preflight(args)
            finally:
                registry.ROOT = previous_registry_root
                project_add.ROOT = previous_add_root

    def test_workspace_wrapper_rejects_invalid_id_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "target"
            result = workspace_init.main(
                ["workspace", "init", str(target), "--id", "Bad ID", "--name", "Bad"]
            )
            self.assertEqual(2, result)
            self.assertFalse(target.exists())

    def test_workspace_wrapper_exports_readme(self) -> None:
        with tempfile.TemporaryDirectory() as source_temp, tempfile.TemporaryDirectory() as target_temp:
            source = Path(source_temp)
            target = Path(target_temp)
            (source / "README.md").write_text("# Template\n", encoding="utf-8")
            (source / "bin").mkdir()
            (source / "bin" / "dw").write_text("#!/bin/sh\n", encoding="utf-8")
            (source / "scripts").mkdir()
            (source / "scripts" / "marker.py").write_text("pass\n", encoding="utf-8")
            previous = registry.ROOT
            registry.ROOT = source
            try:
                result = workspace_init.main(
                    [
                        "workspace",
                        "init",
                        str(target),
                        "--id",
                        "example-super",
                        "--name",
                        "Example Super",
                    ]
                )
                self.assertEqual(0, result)
                self.assertEqual("# Template\n", (target / "README.md").read_text(encoding="utf-8"))
            finally:
                registry.ROOT = previous


if __name__ == "__main__":
    unittest.main()
