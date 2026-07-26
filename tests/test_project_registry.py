from __future__ import annotations

import argparse
import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "dw_project_registry",
    Path(__file__).resolve().parents[1] / "scripts" / "dw_project_registry.py",
)
assert SPEC is not None and SPEC.loader is not None
registry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry)


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


if __name__ == "__main__":
    unittest.main()
