#!/usr/bin/env python3
"""Controller transfer generator for SCRUM-555 / #80 / seq=5.

Generates the Login Capability Epic reference dataset and a standalone HTML
reference page. This is transfer/reference material for Hermes; production UI
source must follow login_epic_ui_source_architecture.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GATES = [
    "G0_CONTEXT",
    "G1_ALIGNMENT",
    "G2_EXECUTION",
    "G3_PR",
    "G4_MERGE",
    "G5_DEPLOY",
    "G6_PRODUCTION",
]

RUNS = [
    ("LOGIN-R00-EPIC-BOOT", "Epic Boot / Architecture Baseline", "planning"),
    ("LOGIN-R01-UX-CONTRACT", "Product + UX Contract", "design"),
    ("LOGIN-R02-REPO-MAPPING", "Repository Mapping + Implementation Plan", "planning"),
    ("LOGIN-R03-UI-SHELL", "UI Shell / Static Login Screen", "implementation"),
    ("LOGIN-R04-FORM-STATE", "Login Form State Machine", "implementation"),
    ("LOGIN-R05-API-CONTRACT", "API Contract + Mock Auth Route", "implementation"),
    ("LOGIN-R06-UI-API-INTEGRATION", "UI ↔ API Integration", "implementation"),
    ("LOGIN-R07-NAVIGATION-SESSION", "Navigation / Session Boundary", "design"),
    ("LOGIN-R08-QUALITY-HARDENING", "Quality / Accessibility / Security Hardening", "quality"),
    ("LOGIN-R09-OBSERVATORY-DEPLOY-BOUNDARY", "Observatory Integration + Deploy/Production Boundary", "observability_deploy_boundary"),
]

RUN_WRITES = {
    "LOGIN-R00-EPIC-BOOT": [".gwc/epics/login/architecture-baseline.yaml", ".gwc/epics/login/repository-scan.json", ".gwc/epics/login/auth-boundary-classification.json"],
    "LOGIN-R01-UX-CONTRACT": [".gwc/epics/login/r1/login-product-brief.yaml", ".gwc/epics/login/r1/login-ui-contract.json", ".gwc/epics/login/r1/login-a11y-checklist.yaml"],
    "LOGIN-R02-REPO-MAPPING": [".gwc/epics/login/r2/repository-mapping.yaml", ".gwc/epics/login/r2/file-write-plan.json", ".gwc/epics/login/r2/scope-hash-input.json"],
    "LOGIN-R03-UI-SHELL": ["projects/dw-observation/app/login/page.tsx", "projects/dw-observation/components/auth/LoginShell.tsx", ".gwc/epics/login/r3/screenshot-evidence.json"],
    "LOGIN-R04-FORM-STATE": ["projects/dw-observation/components/auth/LoginForm.tsx", "projects/dw-observation/lib/contracts/loginState.ts", "projects/dw-observation/tests/login-form-state.test.tsx"],
    "LOGIN-R05-API-CONTRACT": ["projects/dw-observation/lib/contracts/login.ts", "projects/dw-observation/app/api/login/route.ts", "projects/dw-observation/tests/login-api.test.ts"],
    "LOGIN-R06-UI-API-INTEGRATION": ["projects/dw-observation/components/auth/LoginForm.tsx", "projects/dw-observation/lib/api/loginClient.ts", "projects/dw-observation/tests/login-ui-api.test.tsx"],
    "LOGIN-R07-NAVIGATION-SESSION": [".gwc/epics/login/r7/navigation-contract.yaml", ".gwc/epics/login/r7/session-boundary-decision.json", ".gwc/epics/login/r7/route-guard-plan.json"],
    "LOGIN-R08-QUALITY-HARDENING": ["projects/dw-observation/tests/login-a11y.test.tsx", "projects/dw-observation/tests/login-security.test.ts", ".gwc/epics/login/r8/a11y-report.json", ".gwc/epics/login/r8/security-review.yaml"],
    "LOGIN-R09-OBSERVATORY-DEPLOY-BOUNDARY": ["projects/dw-observation/fixtures/login_epic_runs.json", "projects/dw-observation/lib/loginEpicRuntimeGraph.ts", "projects/dw-observation/components/LoginEpicRunGraph.tsx", ".gwc/epics/login/r9/production-boundary-decision.yaml"],
}

RUN_READS = {
    rid: ["AGENTS.md", "workspace.yaml", "projects/dw-observation/package.json", "projects/dw-observation/app/**", "projects/dw-observation/components/**"]
    for rid, _, _ in RUNS
}

BUDGET_24 = {"G0_CONTEXT": 3, "G1_ALIGNMENT": 4, "G2_EXECUTION": 6, "G3_PR": 5, "G4_MERGE": 3, "G5_DEPLOY": 2, "G6_PRODUCTION": 1}
BUDGET_25 = {"G0_CONTEXT": 3, "G1_ALIGNMENT": 4, "G2_EXECUTION": 6, "G3_PR": 5, "G4_MERGE": 3, "G5_DEPLOY": 2, "G6_PRODUCTION": 2}

FAMILIES = {
    "G0_CONTEXT": ["intake_context", "intake_context", "intake_context"],
    "G1_ALIGNMENT": ["gate_authority", "gate_authority", "gate_authority", "gate_authority"],
    "G2_EXECUTION": ["gate_authority", "runtime_checkpoint", "repo_delivery", "repo_delivery", "runtime_checkpoint", "package_export"],
    "G3_PR": ["repo_delivery", "validation_quality", "repo_delivery", "validation_quality", "validation_quality"],
    "G4_MERGE": ["gate_authority", "lifecycle_contract", "repo_delivery"],
    "G5_DEPLOY": ["scale_control", "scale_control", "failure_recovery"],
    "G6_PRODUCTION": ["lifecycle_contract", "sync_projection", "sync_projection"],
}

TITLES = {
    "G0_CONTEXT": ["Boot source resolution", "Repo identity check", "Boundary classification"],
    "G1_ALIGNMENT": ["Gate state resolution", "Evidence artifact map", "Options + scope hash", "Decision + G2 prep"],
    "G2_EXECUTION": ["Execution envelope", "Runtime lease", "Branch / worktree", "Scoped source writes", "Checkpoint persist", "Export / hash report"],
    "G3_PR": ["Diff readback", "Validators + tests", "Draft PR / patch evidence", "CI evidence", "G3 pass decision"],
    "G4_MERGE": ["Merge boundary check", "Merge approval artifact", "Merge exact head"],
    "G5_DEPLOY": ["Merged head status", "Preview/deploy observability", "Deploy approval / recovery"],
    "G6_PRODUCTION": ["Production boundary not applicable", "Production approval", "Apply + audit"],
}

COORDS = {
    "G0_CONTEXT": (60, 80, 460, 460),
    "G1_ALIGNMENT": (620, 60, 560, 520),
    "G2_EXECUTION": (1330, 70, 680, 560),
    "G3_PR": (1320, 760, 680, 560),
    "G4_MERGE": (2180, 780, 500, 460),
    "G5_DEPLOY": (2840, 600, 520, 480),
    "G6_PRODUCTION": (3500, 640, 520, 480),
}

NODE_POS = [(24, 86, 205, 182), (252, 86, 190, 182), (462, 86, 190, 182), (26, 314, 205, 205), (252, 314, 190, 205), (462, 314, 190, 205)]


def make_node(run_id: str, run_i: int, gate_id: str, node_i: int, global_i: int) -> dict[str, Any]:
    family = FAMILIES[gate_id][node_i % len(FAMILIES[gate_id])]
    title = TITLES[gate_id][node_i % len(TITLES[gate_id])]
    short_gate = gate_id.split("_")[0].lower()
    x, y, w, h = NODE_POS[node_i % len(NODE_POS)]
    base = f".gwc/tasks/LOGIN-EPIC/{run_id.lower()}"
    reads = list(dict.fromkeys(RUN_READS[run_id] + [f"{base}/g0/context-snapshot.yaml", f"{base}/g1/scope-hash-input.json"]))[:6]
    writes = list(dict.fromkeys(RUN_WRITES[run_id] + [f"{base}/{short_gate}/node-{node_i + 1:02d}-readback.json"]))[:6]
    return {
        "gate_id": gate_id,
        "id": f"{family}.{run_i:02d}.{short_gate}.{node_i + 1:02d}",
        "title": title,
        "family": family,
        "type": title.lower().replace(" ", "_"),
        "boundary": "read_only" if gate_id in ["G0_CONTEXT", "G1_ALIGNMENT"] else f"{gate_id.lower()}_boundary",
        "purpose": f"{title} for {run_id}; records evidence, file reads/writes, runbook and history.",
        "fileReads": reads,
        "fileWrites": writes,
        "artifacts": list(dict.fromkeys(writes + [f"{base}/{short_gate}/artifact-{node_i + 1:02d}.json"])),
        "runbook": ["Read declared evidence only", "Execute only under current gate authority", "Persist event and checkpoint", "Advance cursor"],
        "taskControllerHistory": [f"TC entered {gate_id}/{title}", "TC checked evidence", "TC persisted runtime event"],
        "executorHistory": [] if gate_id in ["G0_CONTEXT", "G1_ALIGNMENT"] else ["Hermes executor processed node", "Executor returned deterministic readback"],
        "checkpoints": [f"checkpoint:{run_id}:{gate_id}:node-{node_i + 1:02d}:rev-{global_i + 1}"],
        "x": x,
        "y": y,
        "w": w,
        "h": h,
    }


def make_run(run_i: int, run_id: str, title: str, kind: str) -> dict[str, Any]:
    budget = BUDGET_25 if run_i in [7, 8, 9] else BUDGET_24
    gates = []
    global_i = 0
    for gate_id in GATES:
        gx, gy, gw, gh = COORDS[gate_id]
        nodes = []
        for n_i in range(budget[gate_id]):
            nodes.append(make_node(run_id, run_i, gate_id, n_i, global_i))
            global_i += 1
        gates.append({
            "id": gate_id,
            "label": gate_id.replace("_", " · "),
            "summary": f"{gate_id} cluster for {run_id}; owns {len(nodes)} runtime nodes.",
            "x": gx,
            "y": gy,
            "w": gw,
            "h": gh,
            "nodes": nodes,
            "gateArtifacts": sorted({a for n in nodes for a in n["artifacts"] if a.startswith(".gwc/")}),
            "taskControllerHistory": [f"TC opened {gate_id}", f"TC evaluated {len(nodes)} runtime nodes", f"TC checkpointed {gate_id}"],
            "executorHistory": [e for n in nodes for e in n["executorHistory"]][:8] or ["no executor side effect in this gate"],
        })
    route = [{"gate_id": g["id"], "node_id": n["id"]} for g in gates for n in g["nodes"]]
    return {
        "id": run_id,
        "index": run_i,
        "slug": run_id.lower(),
        "title": title,
        "objective": f"Implement planned Login Capability Epic run: {title}.",
        "run_kind": kind,
        "allowed_paths": ["projects/dw-observation/**", ".gwc/tasks/LOGIN-EPIC/**"],
        "forbidden_actions": ["unapproved production secret mutation", "unapproved remote DB migration", "merge without G4", "deploy without G5", "production auth without G6"],
        "gates": gates,
        "route": route,
        "status": "simulated_planned",
        "summary": f"{title}: {len(route)} runtime nodes across G0→G6",
    }


def make_fixture() -> dict[str, Any]:
    runs = [make_run(i, rid, title, kind) for i, (rid, title, kind) in enumerate(RUNS)]
    total = sum(len(r["route"]) for r in runs)
    assert len(runs) == 10
    assert total == 243, total
    assert all(g in [gate["id"] for gate in r["gates"]] for r in runs for g in GATES)
    return {
        "epic_id": "LOGIN-CAPABILITY",
        "title": "Login Capability Epic",
        "run_count": 10,
        "runtime_node_count": total,
        "runtime_model": "Epic → Runs → GWC Gates → Runtime Nodes → Artifacts / Runbook / TaskController History / Executor History / Checkpoints",
        "runs": runs,
    }


def make_html() -> str:
    return """<!doctype html><html><head><meta charset='utf-8'/><title>Login Epic Runtime Graph Reference</title><style>body{margin:0;background:#06111e;color:#eef6ff;font-family:system-ui}.app{padding:16px}.run{display:inline-block;width:240px;min-height:120px;margin:8px;padding:12px;border:1px solid #334155;border-radius:14px;background:#142b49;vertical-align:top;cursor:pointer}.run.active{border-color:#f59e0b}.gate{margin:18px 0;padding:12px;border:1px solid #334155;border-radius:16px;background:#0c1c31}.node{display:inline-block;width:220px;min-height:135px;margin:10px;padding:10px;border:1px solid #475569;border-radius:14px;background:#10233c;vertical-align:top}.node.active{border-color:#f59e0b;box-shadow:0 0 0 4px rgba(245,158,11,.12)}button{margin:4px;padding:8px;border-radius:8px;background:#10233c;color:white;border:1px solid #475569}pre{white-space:pre-wrap;background:#020617;padding:12px;border-radius:12px}</style></head><body><div class='app'><h1>Login Capability Epic — 10 GWC Runs</h1><p>Reference HTML. Production UI must use typed source architecture.</p><div id='runs'></div><hr/><div><button onclick='prev()'>Prev</button><button onclick='playPause()' id='play'>Play</button><button onclick='next()'>Next</button><span id='cursor'></span></div><div id='graph'></div><h2>Details</h2><pre id='details'></pre></div><script src='login_epic_10_runs_gwc_taskcontroller_data.json'></script><script>let data=window.EPIC||null,ri=0,ci=0,t=null;if(!data)document.body.insertAdjacentHTML('afterbegin','<b>Load generated JSON first.</b>');function render(){let r=data.runs[ri];runs.innerHTML=data.runs.map((x,i)=>`<div class='run ${i===ri?'active':''}' onclick='ri=${i};ci=0;render()'><b>${x.id}</b><br/>${x.title}<br/>${x.route.length} runtime nodes</div>`).join('');cursor.textContent=`${r.id} node ${ci+1}/${r.route.length}`;let active=r.route[ci];graph.innerHTML=r.gates.map(g=>`<section class='gate'><h2>${g.id} → ${g.nodes.length} nodes</h2>${g.nodes.map(n=>`<article class='node ${n.id===active.node_id?'active':''}' onclick='ci=${r.route.findIndex(z=>z.node_id===n.id)};render()'><b>${n.title}</b><br/><small>${n.id}</small><p>${n.purpose}</p></article>`).join('')}</section>`).join('');let n=r.gates.flatMap(g=>g.nodes).find(n=>n.id===active.node_id);details.textContent=JSON.stringify(n,null,2)}function next(){let r=data.runs[ri];ci=Math.min(r.route.length-1,ci+1);render()}function prev(){ci=Math.max(0,ci-1);render()}function playPause(){if(t){clearInterval(t);t=null;play.textContent='Play';return}play.textContent='Pause';t=setInterval(()=>{let r=data.runs[ri];if(ci>=r.route.length-1){clearInterval(t);t=null;play.textContent='Play';return}ci++;render()},800)}if(data)render()</script></body></html>"""


def main() -> None:
    root = Path.cwd()
    fixture = make_fixture()
    fixture_path = root / "projects/dw-observation/fixtures/login_epic_10_runs_gwc_taskcontroller_data.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text("window.EPIC = " + json.dumps(fixture, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
    (root / "login_epic_10_runs_gwc_taskcontroller_data.raw.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "login_epic_10_runs_gwc_runtime_graph.reference.html").write_text(make_html(), encoding="utf-8")
    print(f"run_count={fixture['run_count']}")
    print(f"runtime_node_count={fixture['runtime_node_count']}")
    print("generated projects/dw-observation/fixtures/login_epic_10_runs_gwc_taskcontroller_data.json")
    print("generated login_epic_10_runs_gwc_taskcontroller_data.raw.json")
    print("generated login_epic_10_runs_gwc_runtime_graph.reference.html")

if __name__ == "__main__":
    main()
