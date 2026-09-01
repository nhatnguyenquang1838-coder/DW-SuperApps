from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

from taskcontroller.compiler import compile_blueprint
from taskcontroller.domain.runtime_plan import (
    PlanEdge,
    RunCursor,
    RuntimePlan,
    RuntimePlanStep,
)
from taskcontroller.runtime.closed_loop_runtime_executor import (
    ClosedLoopRuntimeError,
    ClosedLoopRuntimeExecutor,
)
from taskcontroller.runtime.execution_state import FileRuntimeExecutionStateStore

EXPECTED_GWC_SHA = "43f6379158978b0c299d775cd162ad69b5a1c099"
DIGEST = "sha256:" + "a" * 64


@pytest.fixture(scope="session")
def gwc_root() -> Path:
    """Resolve and verify the exact read-only GWC test dependency.

    The path is supplied by the test environment/CI, never inferred from a
    workstation-specific checkout. A missing or mismatched dependency is a
    hard test failure so the live cross-repo proof cannot become a false green.
    """
    raw_root = os.environ.get("GWC_ROOT", "").strip()
    if not raw_root:
        pytest.fail("GWC_ROOT must be set to the paired GWC checkout root")
    root = Path(raw_root).expanduser().resolve()
    if not root.is_dir():
        pytest.fail(f"GWC_ROOT does not exist or is not a directory: {root}")
    try:
        top_level = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        actual_sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        pytest.fail(f"GWC_ROOT is not a readable Git checkout: {root} ({exc})")
    if Path(top_level).resolve() != root:
        pytest.fail(f"GWC_ROOT Git top-level mismatch: {top_level} != {root}")
    if actual_sha != EXPECTED_GWC_SHA:
        pytest.fail(
            "GWC_ROOT exact identity mismatch: "
            f"expected {EXPECTED_GWC_SHA}, got {actual_sha}"
        )
    remote = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    parsed = urlparse(remote if "://" in remote else f"ssh://{remote.replace(':', '/', 1)}")
    remote_path = parsed.path.strip("/").removesuffix(".git")
    if parsed.hostname != "github.com" or remote_path != "nhatnguyenquang1838-coder/gwc":
        pytest.fail(
            "GWC_ROOT remote identity mismatch: expected "
            "github.com/nhatnguyenquang1838-coder/gwc, got "
            f"{remote}"
        )
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    drift = []
    for entry in status:
        code, rel = entry[:2], entry[3:]
        if code == "??" or code.strip() not in {"M"}:
            drift.append(entry)
            continue
        try:
            expected = subprocess.run(
                ["git", "-C", str(root), "show", f"HEAD:{rel}"],
                check=True,
                capture_output=True,
            ).stdout
            actual = (root / rel).read_bytes()
        except (OSError, subprocess.CalledProcessError) as exc:
            pytest.fail(f"GWC_ROOT checkout cannot verify {rel}: {exc}")
        if actual.replace(b"\r\n", b"\n") != expected.replace(b"\r\n", b"\n"):
            drift.append(entry)
    if drift:
        pytest.fail(
            "GWC_ROOT checkout has non-EOL drift; refusing live proof: "
            + "\n".join(drift)
        )
    return root


def _run_live_producer(gwc_root: Path):
    producer = subprocess.run(
        [sys.executable, "-c", "import json,sys; sys.path.insert(0,sys.argv[1]); from tools.node_architect.governed_execution_blueprint import produce_governed_blueprint; print(json.dumps(produce_governed_blueprint(task_id='SCRUM-668', scenario='standard_real_run', repo_root=sys.argv[1]).to_dict()))", str(gwc_root)],
        check=True, capture_output=True, text=True,
    )
    blueprint = json.loads(producer.stdout)
    assert blueprint["source_bindings"]["gwc_sha"] == EXPECTED_GWC_SHA
    return compile_blueprint(blueprint, node_instruction_root=gwc_root)


def _blueprint(*, effectful: bool = False) -> dict:
    allowed = ["write_file"] if effectful else ["read"]
    return {
        "schema_version": "1.0",
        "artifact_type": "governed-execution-blueprint",
        "blueprint_id": "blueprint.arch-p0",
        "task_id": "SCRUM-668",
        "scenario": "architecture_p0",
        "source_bindings": {
            "gwc_sha": EXPECTED_GWC_SHA,
            "flow_ref": "core/node-architect/profile-registry.json",
            "flow_revision": "flow-r1",
            "flow_digest": DIGEST,
            "policy_ref": "core/node-architect/gate-applicability-policy-registry.json",
            "policy_revision": "policy-r1",
            "policy_digest": DIGEST,
            "project_profile_ref": "projects/gwc/project-profile.yaml",
        },
        "runbooks": [{"runbook_id": "rb", "revision": "1", "digest": DIGEST}],
        "nodes": [
            {
                "action": "inspect",
                "node_id": "reference.inspect",
                "node_instruction_ref": "core/node-architect/node-instructions/reference/inspect.node-instruction.yaml",
                "node_instruction_digest": DIGEST,
                "implementation_ref": "tools/node_architect/inspect.py",
                "route_profile_revision": "route-r1",
                "graph_revision": "graph-r1",
                "node_registry_revision": "nodes-r1",
                "allowed_actions": allowed,
                "allowed_inputs": ["input.current"],
                "evidence_refs": ["evidence.inspect"],
            },
            {
                "action": "next",
                "node_id": "reference.next",
                "node_instruction_ref": "core/node-architect/node-instructions/reference/next.node-instruction.yaml",
                "node_instruction_digest": DIGEST,
                "implementation_ref": "tools/node_architect/next.py",
                "route_profile_revision": "route-r1",
                "graph_revision": "graph-r1",
                "node_registry_revision": "nodes-r1",
                "allowed_actions": ["read"],
                "allowed_inputs": ["input.current"],
                "evidence_refs": ["evidence.next"],
            },
        ],
        "topology": [
            {
                "action": "inspect",
                "node_id": "reference.inspect",
                "edges": [
                    {"target": "next", "kind": "continue", "runtime_executable": True},
                ],
            },
            {"action": "next", "node_id": "reference.next", "edges": []},
        ],
        "authority_requirements": [
            {"action": "inspect", "gate": "G3_PR", "required": effectful}
        ],
        "implementation_plan_ref": "implementation-plan/SCRUM-668/r1",
    }


def test_arch_p0_a_runtime_and_implementation_plan_identity_are_distinct():
    plan = compile_blueprint(_blueprint())
    assert plan.implementation_plan_ref == "implementation-plan/SCRUM-668/r1"
    assert plan.runtime_plan_ref != plan.implementation_plan_ref
    r2 = RuntimePlan(
        runtime_plan_ref=plan.runtime_plan_ref,
        implementation_plan_ref=plan.implementation_plan_ref,
        revision="runtime-revision-r2",
        steps=plan.steps,
        source_bindings=plan.source_bindings,
        runbooks=plan.runbooks,
        authority_requirements=plan.authority_requirements,
        blueprint_id=plan.blueprint_id,
        blueprint_digest=plan.blueprint_digest,
        task_id=plan.task_id,
        scenario=plan.scenario,
    )
    assert r2.runtime_plan_ref == plan.runtime_plan_ref
    assert r2.implementation_plan_ref == plan.implementation_plan_ref
    assert r2.revision != plan.revision


def test_arch_p0_b_digest_is_stable_after_caller_mutation():
    source = {"nested": {"value": "before"}}
    binding = {"nested": {"value": "node-before"}}
    step = RuntimePlanStep(
        step_id="s", semantic_action="s", node_binding=binding,
    )
    plan = RuntimePlan(
        runtime_plan_ref="runtime/r1", implementation_plan_ref="implementation/r1",
        revision="r1", steps={"s": step}, source_bindings=source,
        runbooks=[{"runbook_id": "rb", "revision": "1", "digest": DIGEST}],
        authority_requirements=[{"action": "s", "gate": "G3_PR", "required": True}],
    )
    digest = plan.runtime_plan_digest
    source["nested"]["value"] = "after"
    binding["nested"]["value"] = "node-after"
    assert plan.runtime_plan_digest == digest
    assert plan.source_bindings["nested"]["value"] == "before"
    assert plan.step("s").node_binding["nested"]["value"] == "node-before"
    with pytest.raises(TypeError):
        plan.source_bindings["nested"]["value"] = "mutated"


def test_arch_p0_c_wait_resumes_same_plan_and_replan_switches_revision():
    step = RuntimePlanStep(
        step_id="s", semantic_action="s",
        edges={
            "WAIT": PlanEdge(outcome="WAIT", target="wait", kind="blocked"),
            "REPLAN_REQUIRED": PlanEdge(
                outcome="REPLAN_REQUIRED", target="replan", kind="blocked"
            ),
        },
    )
    plan = RuntimePlan(runtime_plan_ref="runtime/r1", implementation_plan_ref="impl/r1", revision="r1", steps={"s": step})
    wait_cursor = RunCursor(
        run_id="run", runtime_plan_ref=plan.runtime_plan_ref,
        runtime_plan_digest=plan.runtime_plan_digest, plan_revision=plan.revision,
        current_step_id="s",
    ).advance(plan.resolve_edge("s", "WAIT"))
    assert wait_cursor.control_state == "WAITING"
    assert wait_cursor.current_step_id == "s"
    resumed = wait_cursor.resume()
    assert resumed.control_state == "RUNNING"
    assert resumed.runtime_plan_ref == plan.runtime_plan_ref
    r2 = RuntimePlan(
        runtime_plan_ref=plan.runtime_plan_ref, implementation_plan_ref="impl/r1",
        revision="r2", steps={"s": step},
    )
    switched = resumed.switch_to(r2)
    assert switched.runtime_plan_ref == r2.runtime_plan_ref
    assert switched.runtime_plan_digest == r2.runtime_plan_digest
    assert switched.plan_revision == "r2"
    assert switched.control_state == "RUNNING"
    assert switched.current_step_id == "s"
    assert not plan.resolve_edge("s", "WAIT").is_terminal
    assert not plan.resolve_edge("s", "REPLAN_REQUIRED").is_terminal


def _runtime_plan_dict(*, nonexec: bool = False, effectful: bool = False) -> tuple[dict, RunCursor]:
    action = "write_file" if effectful else "read"
    edge = {
        "outcome": "NEXT", "target": "next", "kind": "continue",
        "runtime_executable": not nonexec,
    }
    plan = RuntimePlan.from_dict({
        "runtime_plan_ref": "runtime/executor",
        "implementation_plan_ref": "implementation/executor",
        "revision": "r1",
        "steps": {
            "s": {
                "step_id": "s", "semantic_action": "s",
                "allowed_actions": [action], "edges": {"NEXT": edge},
            },
            "next": {
                "step_id": "next", "semantic_action": "next",
                "allowed_actions": ["read"], "edges": {},
            },
        },
    })
    payload = plan.to_dict()
    cursor = RunCursor(
        run_id="run-executor", runtime_plan_ref=plan.runtime_plan_ref,
        runtime_plan_digest=plan.runtime_plan_digest, plan_revision=plan.revision,
        current_step_id="s",
    )
    return payload, cursor


def test_arch_p0_d_non_executable_route_is_rejected_without_cursor_advance():
    payload, cursor = _runtime_plan_dict(nonexec=True)
    executor = ClosedLoopRuntimeExecutor(payload, cursor)
    with pytest.raises(ClosedLoopRuntimeError, match="non-executable"):
        executor.execute_step("s", {}, outcome="NEXT", requested_action="read", sequence=1)
    assert executor.cursor.current_step_id == "s"


def test_arch_p0_e_w4_can_compile_source_backed_capabilities(gwc_root: Path):
    plan = _run_live_producer(gwc_root)
    assert all(step.allowed_actions for step in plan.steps.values())
    assert all(step.allowed_inputs for step in plan.steps.values())
    assert all(step.evidence_refs for step in plan.steps.values())


def test_arch_p0_e_w4_to_w5_real_read_and_effectful_actions(gwc_root: Path):
    plan = _run_live_producer(gwc_root)
    read_id = "repo_delivery.ci-run-capture"
    read_cursor = RunCursor("run-real-w5-read", plan.runtime_plan_ref, plan.runtime_plan_digest, plan.revision, read_id)
    read_result = ClosedLoopRuntimeExecutor(plan.to_dict(), read_cursor).execute_step(
        read_id, {}, requested_action="reconcile_pr_head_state", sequence=1,
        outcome_resolver=lambda _step, _payload: "CONTINUE",
    )
    assert read_result["authority_revalidated"] is False

    effect_id = "runtime_checkpoint.checkpoint-persist"
    effect_action = plan.step(effect_id).allowed_actions[0]
    observed: list[dict] = []
    authority_context = {
        "task_id": "SCRUM-668", "repository": "nhatnguyenquang1838-coder/gwc",
        "base_sha": "a" * 40, "head_sha": "b" * 40,
        "scope_hash": "sha256:" + "c" * 64, "expires_at": "2099-01-01T00:00:00Z",
    }
    def authority(ctx):
        observed.append(dict(ctx))
        return ctx["task_id"] == "SCRUM-668" and ctx["repository"] == "nhatnguyenquang1838-coder/gwc" and ctx["action"] == effect_action
    effect_cursor = RunCursor("run-real-w5-effect", plan.runtime_plan_ref, plan.runtime_plan_digest, plan.revision, effect_id)
    effect_result = ClosedLoopRuntimeExecutor(
        plan.to_dict(), effect_cursor, authority_context=authority_context, authority_checker=authority,
    ).execute_step(effect_id, {}, requested_action=effect_action, sequence=1, outcome_resolver=lambda _step, _payload: "CONTINUE", side_effect=lambda: observed.append({"effect": "ran"}))
    assert effect_result["authority_revalidated"] is True
    assert any(entry.get("effect") == "ran" for entry in observed)
    assert observed[0]["base_sha"] == "a" * 40


def test_arch_p0_i_live_gwc_terminal_progression(gwc_root: Path):
    plan = _run_live_producer(gwc_root)
    terminal_id = "validation_quality.ci-evidence-capture"
    step = plan.step(terminal_id)
    assert step.terminal is True
    cursor = RunCursor("run-real-terminal", plan.runtime_plan_ref, plan.runtime_plan_digest, plan.revision, terminal_id)
    result = ClosedLoopRuntimeExecutor(plan.to_dict(), cursor).execute_step(
        terminal_id, {}, requested_action="capture_ci_evidence", sequence=1,
    )
    assert result["current_step"] == "terminal"
    assert result["is_terminal"] is True
    assert result["evidence"][terminal_id]["status"] == "TERMINAL"


def test_arch_p0_f_fresh_executor_rehydrates_state(tmp_path):
    payload, cursor = _runtime_plan_dict()
    store = FileRuntimeExecutionStateStore(tmp_path)
    first = ClosedLoopRuntimeExecutor(payload, cursor, state_store=store)
    first.execute_step("s", {}, outcome="NEXT", requested_action="read", sequence=7)
    fresh = ClosedLoopRuntimeExecutor(payload, first.cursor, state_store=store)
    assert fresh.completed_steps == ("s",)
    assert fresh.evidence["s"]["status"] == "NEXT"
    assert fresh.last_sequence == 7
    with pytest.raises(ClosedLoopRuntimeError, match="stale"):
        fresh.execute_step("next", {}, requested_action="read", sequence=7)


def test_arch_p0_g_invalid_authority_blocks_effect_and_cursor():
    payload, cursor = _runtime_plan_dict(effectful=True)
    effects: list[dict] = []
    executor = ClosedLoopRuntimeExecutor(
        payload,
        cursor,
        authority_context={
            "task_id": "SCRUM-668", "repository": "nhatnguyenquang1838-coder/gwc",
            "base_sha": "a" * 40, "head_sha": "b" * 40,
            "scope_hash": "sha256:" + "c" * 64,
            "requested_action": "write_file", "expires_at": "2099-01-01T00:00:00Z",
        },
        authority_checker=lambda context: False,
    )
    with pytest.raises(ClosedLoopRuntimeError, match="authority"):
        executor.execute_step(
            "s", {"requested_action": "write_file"},
            outcome="NEXT", requested_action="write_file", sequence=1,
            side_effect=lambda: effects.append({"ran": True}),
        )
    assert effects == []
    assert executor.cursor.current_step_id == "s"
    assert executor.completed_steps == ()
