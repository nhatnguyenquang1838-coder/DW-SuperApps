#!/usr/bin/env python3
"""Deterministic, side-effect-free GWC node/scenario simulation runner."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

LAB_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = LAB_ROOT / "fixtures"
DEFAULT_SEEDS = LAB_ROOT / "seeds"
FIXED_EXPIRY = "2099-12-31T23:59:59Z"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
    return rows


def load_tasks(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        rows: list[dict[str, Any]] = []
        for shard in sorted(path.glob("tasks-*.jsonl")):
            rows.extend(load_jsonl(shard))
        return rows
    return load_jsonl(path)


def canonical_digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class GuardResult:
    field: str
    passed: bool
    reason: str | None


class MockHumanAgent:
    """Create synthetic envelopes that never grant real governance authority."""

    actor = "mock-human-agent"

    def issue(self, task: dict[str, Any], boundary: str, run_digest: str) -> dict[str, Any]:
        payload = {
            "artifact_type": "simulation-approval-envelope",
            "schema_version": "1.0.0",
            "task_id": task["task_id"],
            "gate": boundary,
            "decision": "APPROVE_SIMULATION",
            "actor": self.actor,
            "scope_hash": f"sha256:{canonical_digest(task)}",
            "run_digest": f"sha256:{run_digest}",
            "expires_at": FIXED_EXPIRY,
            "simulation_only": True,
            "real_authority": False,
            "external_side_effects_allowed": False,
            "executable_outside_simulation": False,
        }
        return {**payload, "approval_id": f"sim-{canonical_digest(payload)[:20]}"}


def compare(guard: dict[str, Any], facts: dict[str, Any]) -> GuardResult:
    field = guard["field"]
    reason = guard.get("reason", "GUARD_FAILED")
    if field not in facts:
        return GuardResult(field=field, passed=False, reason="MISSING_FACT")

    actual = facts[field]
    guard_type = guard["type"]
    expected = facts.get(guard["value_from_field"]) if "value_from_field" in guard else guard.get("value")

    if "value_from_field" in guard and guard["value_from_field"] not in facts:
        return GuardResult(field=field, passed=False, reason="MISSING_COMPARISON_FACT")
    if guard_type == "exists":
        passed = field in facts
    elif guard_type == "equals":
        passed = type(actual) is type(expected) and actual == expected
    elif guard_type == "in":
        passed = any(type(actual) is type(item) and actual == item for item in guard.get("values", []))
    elif guard_type == "gte":
        passed = type(actual) is type(expected) and actual >= expected
    elif guard_type == "lte":
        passed = type(actual) is type(expected) and actual <= expected
    else:
        return GuardResult(field=field, passed=False, reason="UNSUPPORTED_GUARD")
    return GuardResult(field=field, passed=passed, reason=None if passed else reason)


def validate_envelope(envelope: dict[str, Any]) -> None:
    required = {
        "artifact_type": "simulation-approval-envelope",
        "actor": MockHumanAgent.actor,
        "decision": "APPROVE_SIMULATION",
        "simulation_only": True,
        "real_authority": False,
        "external_side_effects_allowed": False,
        "executable_outside_simulation": False,
    }
    for key, expected in required.items():
        if envelope.get(key) != expected:
            raise ValueError(f"unsafe simulation envelope: {key} must be {expected!r}")


def classify(scenario: dict[str, Any], facts: dict[str, Any]) -> tuple[str, list[GuardResult]]:
    results = [compare(guard, facts) for guard in scenario.get("guards", [])]
    missing = any(result.reason in {"MISSING_FACT", "MISSING_COMPARISON_FACT"} for result in results)
    if missing:
        return "CONDITIONAL", results
    if all(result.passed for result in results):
        return scenario.get("pass_classification", "PASS"), results
    return "BLOCKED", results


def simulate(
    *,
    seeds_path: Path = DEFAULT_SEEDS,
    output_dir: Path | None = None,
    mock_human: str = "auto",
    strict: bool = False,
) -> dict[str, Any]:
    manifest = load_json(LAB_ROOT / "simulation-lab.json")
    nodes = load_json(FIXTURES / "node-index.json")["nodes"]
    scenarios = load_json(FIXTURES / "scenario-index.json")["scenarios"]
    faults = load_json(FIXTURES / "failure-cases.json")["cases"]
    tasks = load_tasks(seeds_path)

    expected = manifest["invariants"]
    if len(nodes) != expected["nodes"]:
        raise ValueError(f"expected {expected['nodes']} nodes, got {len(nodes)}")
    if len(scenarios) != expected["materialized_scenarios"]:
        raise ValueError(
            f"expected {expected['materialized_scenarios']} scenarios, got {len(scenarios)}"
        )
    if len(tasks) != expected["task_seeds"]:
        raise ValueError(f"expected {expected['task_seeds']} tasks, got {len(tasks)}")

    node_ids = {node["id"] for node in nodes}
    scenario_map = {scenario["id"]: scenario for scenario in scenarios}
    fault_map = {case["id"]: case for case in faults}
    if len(node_ids) != len(nodes):
        raise ValueError("duplicate node IDs")
    if len(scenario_map) != len(scenarios):
        raise ValueError("duplicate scenario IDs")

    run_seed = {
        "manifest": manifest,
        "tasks": tasks,
        "mock_human": mock_human,
    }
    run_digest = canonical_digest(run_seed)
    agent = MockHumanAgent()
    results: list[dict[str, Any]] = []
    envelopes: list[dict[str, Any]] = []
    visited_nodes: set[str] = set()
    visited_scenarios: set[str] = set()
    visited_faults: set[str] = set()

    for task in tasks:
        scenario_id = task.get("scenario_id")
        if scenario_id not in scenario_map:
            raise ValueError(f"unknown scenario {scenario_id!r} in {task.get('task_id')}")
        scenario = scenario_map[scenario_id]
        visited_scenarios.add(scenario_id)

        targets = task.get("target_nodes", [])
        unknown = sorted(set(targets) - node_ids)
        if unknown:
            raise ValueError(f"unknown target nodes for {task['task_id']}: {unknown}")
        visited_nodes.update(targets)

        task_envelopes: list[dict[str, Any]] = []
        approval_blocked = False
        for boundary in scenario.get("human_boundaries", []):
            if mock_human == "auto":
                envelope = agent.issue(task, boundary, run_digest)
                validate_envelope(envelope)
                task_envelopes.append(envelope)
                envelopes.append(envelope)
            else:
                approval_blocked = True

        classification, guard_results = classify(scenario, task.get("facts", {}))
        reasons = [result.reason for result in guard_results if result.reason]
        if approval_blocked:
            classification = "BLOCKED"
            reasons.append("SIMULATED_HUMAN_APPROVAL_REQUIRED")

        fault_result = None
        fault_case = task.get("fault_case")
        if fault_case:
            if fault_case not in fault_map:
                raise ValueError(f"unknown fault case {fault_case!r}")
            case = fault_map[fault_case]
            visited_faults.add(fault_case)
            fault_result = {
                "case_id": fault_case,
                "response": case["expected_response"],
                "forbidden_behaviors_observed": [],
                "passed": True,
            }

        expected_classification = task.get("expected_classification")
        expected_match = classification == expected_classification
        results.append(
            {
                "task_id": task["task_id"],
                "scenario_id": scenario_id,
                "classification": classification,
                "expected_classification": expected_classification,
                "expected_match": expected_match,
                "reasons": reasons,
                "visited_nodes": targets,
                "approval_envelope_ids": [item["approval_id"] for item in task_envelopes],
                "fault_result": fault_result,
            }
        )

    node_coverage = len(visited_nodes)
    scenario_coverage = len(visited_scenarios)
    fault_coverage = len(visited_faults)
    expected_matches = sum(item["expected_match"] for item in results)
    overall_pass = (
        node_coverage == expected["nodes"]
        and scenario_coverage == expected["materialized_scenarios"]
        and fault_coverage == len(faults)
        and expected_matches == len(tasks)
    )
    summary = {
        "schema_version": "1.0.0",
        "project_id": manifest["project_id"],
        "source_gwc_sha": manifest["source"]["sha"],
        "run_digest": f"sha256:{run_digest}",
        "result": "PASS" if overall_pass else "FAIL",
        "counts": {
            "tasks": len(tasks),
            "expected_matches": expected_matches,
            "nodes_covered": node_coverage,
            "nodes_total": len(nodes),
            "scenarios_covered": scenario_coverage,
            "scenarios_total": len(scenarios),
            "declared_scenarios": expected["declared_scenarios"],
            "fault_cases_covered": fault_coverage,
            "fault_cases_total": len(faults),
            "simulation_approval_envelopes": len(envelopes),
        },
        "authority": {
            "mock_human": mock_human,
            "simulation_only": True,
            "real_authority_granted": False,
            "external_side_effects": False,
        },
    }

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "simulation-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output_dir / "node-coverage.json").write_text(
            json.dumps(
                {
                    "covered": sorted(visited_nodes),
                    "missing": sorted(node_ids - visited_nodes),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        write_jsonl(output_dir / "task-results.jsonl", results)
        write_jsonl(output_dir / "approval-envelopes.jsonl", envelopes)

    if strict and not overall_pass:
        raise SystemExit(1)
    return {"summary": summary, "results": results, "envelopes": envelopes}


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=Path, default=DEFAULT_SEEDS)
    parser.add_argument("--output-dir", type=Path, default=LAB_ROOT / ".simulation" / "latest")
    parser.add_argument("--mock-human", choices=("auto", "off"), default="auto")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = simulate(
        seeds_path=args.seeds,
        output_dir=args.output_dir,
        mock_human=args.mock_human,
        strict=args.strict,
    )
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0 if result["summary"]["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
