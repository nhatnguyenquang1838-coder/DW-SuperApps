import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import path from "path";
import { loadLoginEpicFixture } from "@/lib/loginEpicFixture";
import { validateLoginEpicFixture } from "@/lib/loginEpicRuntimeValidation";
import {
  type LoginEpicRuntimeFixture,
  getRun,
  getGate,
  getRuntimeNode,
  getRouteIndex,
  clampCursor,
  getActiveRoute,
  getNodeState,
  getGateState,
  buildGateEdges,
  buildRouteEdges,
  makeArtifactPreview,
} from "@/lib/loginEpicRuntimeGraph";

const fixture = loadLoginEpicFixture();

describe("Login Epic dataset shape", () => {
  it("has exactly 10 runs", () => {
    expect(fixture.runs.length).toBe(10);
  });
  it("has exactly 243 runtime nodes across all runs", () => {
    const total = fixture.runs.reduce(
      (n, r) => n + r.gates.reduce((m, g) => m + g.nodes.length, 0),
      0,
    );
    expect(total).toBe(243);
  });
  it("every run contains all 7 gates", () => {
    const want = ["G0_CONTEXT", "G1_ALIGNMENT", "G2_EXECUTION", "G3_PR", "G4_MERGE", "G5_DEPLOY", "G6_PRODUCTION"];
    for (const r of fixture.runs) {
      expect(r.gates.map((g) => g.id).sort()).toEqual([...want].sort());
    }
  });
  it("every route node exists in its gate", () => {
    for (const r of fixture.runs) {
      const ids = new Set(r.gates.flatMap((g) => g.nodes.map((n) => n.id)));
      for (const step of r.route) expect(ids.has(step.node_id)).toBe(true);
    }
  });
  it("passes validateLoginEpicFixture", () => {
    const res = validateLoginEpicFixture(fixture);
    expect(res.ok).toBe(true);
    if (!res.ok) console.log(res.issues);
  });
});

describe("Login Epic pure engine", () => {
  const r0 = fixture.runs[0];
  it("getRun / getGate / getRuntimeNode", () => {
    expect(getRun(fixture, r0.id).id).toBe(r0.id);
    expect(getGate(r0, "G2_EXECUTION").id).toBe("G2_EXECUTION");
    const first = r0.gates[0].nodes[0];
    const found = getRuntimeNode(r0, first.id);
    expect(found.node.id).toBe(first.id);
    expect(found.gate.id).toBe("G0_CONTEXT");
  });
  it("getRouteIndex finds the node index in route order", () => {
    const n0 = r0.route[0].node_id;
    expect(getRouteIndex(r0, n0)).toBe(0);
    const nMid = r0.route[5].node_id;
    expect(getRouteIndex(r0, nMid)).toBe(5);
  });
  it("clampCursor bounds within route length", () => {
    expect(clampCursor(r0, -5)).toBe(0);
    expect(clampCursor(r0, 9999)).toBe(r0.route.length - 1);
  });
  it("getActiveRoute returns the cursor step", () => {
    const a = getActiveRoute(r0, 3);
    expect(a.node_id).toBe(r0.route[3].node_id);
  });
  it("getNodeState done/active/future", () => {
    expect(getNodeState(r0, r0.route[0].node_id, 2)).toBe("done");
    expect(getNodeState(r0, r0.route[2].node_id, 2)).toBe("active");
    expect(getNodeState(r0, r0.route[4].node_id, 2)).toBe("future");
  });
  it("getGateState transitions", () => {
    const g0 = getGateState(r0, "G0_CONTEXT", 0);
    expect(["active", "done", "future"]).toContain(g0);
  });
  it("buildGateEdges produces 6 G0->G6 arrows", () => {
    expect(buildGateEdges(r0).length).toBe(6);
  });
  it("buildRouteEdges covers route length - 1", () => {
    expect(buildRouteEdges(r0).length).toBe(r0.route.length - 1);
  });
});

describe("Login Epic makeArtifactPreview enrichment (blocker #5)", () => {
  const r0 = fixture.runs[0];
  const node = r0.gates[0].nodes[0];

  const targets = [
    "app/login/page.tsx",
    "components/auth/LoginShell.tsx",
    "components/auth/LoginForm.tsx",
    "lib/contracts/login.ts",
    "app/api/login/route.ts",
    "lib/api/loginClient.ts",
  ];
  for (const p of targets) {
    it(`enriches source preview for ${p}`, () => {
      const out = makeArtifactPreview({ run: r0, gate: r0.gates[0], node, path: p, cursor: 0 });
      expect(out).toContain("simulated source-code write preview");
      expect(out.length).toBeGreaterThan(40);
      // node-agnostic open also enriches (deterministic content, defaults for purpose/boundary)
      const agnostic = makeArtifactPreview({ run: r0, path: p, cursor: 0 });
      expect(agnostic).toContain("simulated source-code write preview");
    });
  }
  it("non-login source file is not enriched", () => {
    const out = makeArtifactPreview({ run: r0, path: "lib/other.ts", cursor: 0 });
    expect(out).not.toContain("simulated source-code write preview");
  });
});

describe("Login Epic delivery docs exist (blocker #1)", () => {
  const root = process.cwd();
  // tests run with cwd = projects/dw-observation; docs live at repo root .gwc/...
  const repoRoot = path.resolve(root, "..", "..");
  const design = path.join(repoRoot, ".gwc/tasks/SCRUM-555/m5/login-epic-runtime-graph-design.md");
  const acceptance = path.join(repoRoot, ".gwc/tasks/SCRUM-555/m5/login-epic-runtime-graph-acceptance.md");
  it("design doc present", () => {
    const txt = readFileSync(design, "utf8");
    expect(txt).toContain("Login Epic GWC Runtime Graph — Design");
  });
  it("acceptance doc present and lists all blockers", () => {
    const txt = readFileSync(acceptance, "utf8");
    expect(txt).toContain("Acceptance");
    for (const b of ["# Dataset", "run graph", "run-level graph", "player", "zoom", "right panel", "Blockers addressed", "Screenshot evidence"]) {
      expect(txt).toContain(b);
    }
  });
});

