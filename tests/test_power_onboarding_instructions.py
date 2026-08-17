"""Regression coverage for Power onboarding instruction hardening.

These tests assert that the canonical DW-SuperApps instructions distinguish:
1. target product submodule  vs  Power source submodule;
2. Power install/bind (availability)  vs  Power activate/use (task intent);
3. workspace package store / bindings  vs  project-owned runtime;
4. that a normal project task must NOT execute/initialize the Power source
   submodule, and must NOT create <project>/.dw/powers as a normal install.

Scope: G2B (DW-SuperApps@ceff15d96ef1653da74a4aa48723fce42ee0f0e3).
Read-only against repository instruction files; no mutation.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AGENTS = ROOT / "AGENTS.md"
CONSUMER = ROOT / "docs" / "POWER_CONSUMER_RUNTIME_V1.md"
ONBOARDING = ROOT / "docs" / "runbooks" / "POWER_DIST_ONBOARDING.md"


def _read(p: Path) -> str:
    self = unittest.TestCase()
    self.assertTrue(p.exists(), f"required instruction file missing: {p}")
    return p.read_text(encoding="utf-8")


class TargetVsPowerSourceSubmoduleTests(unittest.TestCase):
    def test_agents_md_distinguishes_target_vs_source_submodule(self):
        text = _read(AGENTS)
        self.assertIn("Target project submodule", text)
        self.assertIn("Power source submodule", text)
        # the parent gitlink pin must not be an implicit task head
        self.assertIn("not", text)
        self.assertIn("bumped implicitly", text)

    def test_consumer_runtime_distinguishes_target_vs_source(self):
        text = _read(CONSUMER)
        self.assertIn("Target project submodule", text)
        self.assertIn("Power source submodule", text)

    def test_onboarding_separates_target_materialization_from_power_onboarding(self):
        text = _read(ONBOARDING)
        self.assertIn("Target submodule materialization", text)
        self.assertIn("Do not initialize Power submodules", text)


class InstallVsActivateTests(unittest.TestCase):
    def test_agents_md_install_does_not_mean_activate(self):
        text = _read(AGENTS)
        self.assertIn("Installed/available does not mean activated", text)
        self.assertIn("task intent", text)
        self.assertIn("inactive", text)

    def test_consumer_runtime_install_vs_activate(self):
        text = _read(CONSUMER)
        self.assertIn("Install/availability vs activate/use", text)
        self.assertIn("task-intent", text)

    def test_onboarding_install_vs_activate(self):
        text = _read(ONBOARDING)
        self.assertIn("Install/configure vs activate/use", text)


class OwnershipBoundaryTests(unittest.TestCase):
    def test_consumer_runtime_package_store_vs_project_runtime(self):
        text = _read(CONSUMER)
        self.assertIn(".dw/powers/", text)
        self.assertIn("Project runtime", text)

    def test_no_project_dw_powers_normal_install(self):
        # The instruction must forbid creating <project>/.dw/powers as a
        # normal installation target (legacy detection only).
        for p, label in ((AGENTS, "AGENTS.md"), (CONSUMER, "consumer runtime")):
            text = _read(p)
            self.assertIn("LEGACY_TARGET_INSTALL", text)


class DistributionDriftRoutingTests(unittest.TestCase):
    def test_onboarding_blocks_on_distribution_drift(self):
        text = _read(ONBOARDING)
        self.assertIn("BLOCKED_DISTRIBUTION_DRIFT", text)
        self.assertIn("raw Power source", text)


if __name__ == "__main__":
    unittest.main()
