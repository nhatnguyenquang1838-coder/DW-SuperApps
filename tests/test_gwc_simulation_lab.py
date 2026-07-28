from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "systems" / "gwc-simulation-lab"
SPEC = importlib.util.spec_from_file_location("gwc_simulate", LAB / "tools" / "simulate.py")
assert SPEC is not None and SPEC.loader is not None
simulate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = simulate
SPEC.loader.exec_module(simulate)


class GwcSimulationLabTests(unittest.TestCase):
    def test_fixture_invariants(self) -> None:
        manifest = json.loads((LAB / "simulation-lab.json").read_text(encoding="utf-8"))
        nodes = json.loads((LAB / "fixtures" / "node-index.json").read_text(encoding="utf-8"))["nodes"]
        scenarios = json.loads(
            (LAB / "fixtures" / "scenario-index.json").read_text(encoding="utf-8")
        )["scenarios"]
        tasks = simulate.load_jsonl(LAB / "seeds" / "tasks.jsonl")
        self.assertEqual(81, manifest["invariants"]["nodes"])
        self.assertEqual(81, len(nodes))
        self.assertEqual(81, len({node["id"] for node in nodes}))
        self.assertEqual(14, len(scenarios))
        self.assertEqual(116, manifest["invariants"]["declared_scenarios"])
        self.assertEqual(100, len(tasks))

    def test_auto_mock_human_passes_full_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = simulate.simulate(output_dir=Path(temporary), mock_human="auto", strict=True)
        summary = result["summary"]
        self.assertEqual("PASS", summary["result"])
        self.assertEqual(100, summary["counts"]["tasks"])
        self.assertEqual(81, summary["counts"]["nodes_covered"])
        self.assertEqual(14, summary["counts"]["scenarios_covered"])
        self.assertEqual(6, summary["counts"]["fault_cases_covered"])
        self.assertGreater(summary["counts"]["simulation_approval_envelopes"], 0)
        self.assertTrue(all(item["simulation_only"] for item in result["envelopes"]))
        self.assertTrue(all(item["real_authority"] is False for item in result["envelopes"]))
        self.assertTrue(all(item["decision"] == "APPROVE_SIMULATION" for item in result["envelopes"]))

    def test_mock_human_off_blocks_human_boundaries(self) -> None:
        result = simulate.simulate(output_dir=None, mock_human="off", strict=False)
        self.assertEqual("FAIL", result["summary"]["result"])
        self.assertTrue(
            any("SIMULATED_HUMAN_APPROVAL_REQUIRED" in item["reasons"] for item in result["results"])
        )

    def test_envelope_validator_rejects_real_authority(self) -> None:
        unsafe = {
            "artifact_type": "simulation-approval-envelope",
            "actor": "mock-human-agent",
            "decision": "APPROVE_SIMULATION",
            "simulation_only": True,
            "real_authority": True,
            "external_side_effects_allowed": False,
            "executable_outside_simulation": False,
        }
        with self.assertRaises(ValueError):
            simulate.validate_envelope(unsafe)

    def test_simulation_digest_is_deterministic(self) -> None:
        first = simulate.simulate(output_dir=None, mock_human="auto", strict=True)
        second = simulate.simulate(output_dir=None, mock_human="auto", strict=True)
        self.assertEqual(first["summary"]["run_digest"], second["summary"]["run_digest"])
        self.assertEqual(first["results"], second["results"])

    def test_workflow_runs_tests_and_strict_simulation(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "gwc-simulation-lab.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("pull_request:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("tests.test_gwc_simulation_lab", workflow)
        self.assertIn("--mock-human auto --strict", workflow)
        self.assertIn("actions/upload-artifact", workflow)


if __name__ == "__main__":
    unittest.main()
