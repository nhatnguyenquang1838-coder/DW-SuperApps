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
  shouldDisableFollowOnMove,
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

  // Blocker #3: approved UX must be username / password / CTA "Login" (not email / Sign in).
  it("LoginForm preview uses approved UX (username, password, CTA Login)", () => {
    const out = makeArtifactPreview({ run: r0, path: "components/auth/LoginForm.tsx", cursor: 0 });
    expect(out).toContain("username");
    expect(out).toContain("password");
    expect(out).toContain("Login"); // CTA text
    expect(out).not.toContain("email");
    expect(out).not.toContain("Sign in");
  });
  it("LoginShell preview heading is Login (approved UX)", () => {
    const out = makeArtifactPreview({ run: r0, path: "components/auth/LoginShell.tsx", cursor: 0 });
    expect(out).toContain("<h1>Login</h1>");
    expect(out).not.toContain("Sign in");
  });

  // Blocker #4: the six snippets form one coherent import/export graph.
  describe("source preview import/export contract (blocker #4)", () => {
    const preview = (p: string) => makeArtifactPreview({ run: r0, path: p, cursor: 0 });
    it("page.tsx default-exports LoginPage and imports named LoginShell", () => {
      const out = preview("app/login/page.tsx");
      expect(out).toMatch(/import \{ LoginShell \} from "@\/components\/auth\/LoginShell"/);
      expect(out).toMatch(/export default function LoginPage/);
    });
    it("LoginShell named-exports LoginShell and imports named LoginForm", () => {
      const out = preview("components/auth/LoginShell.tsx");
      expect(out).toMatch(/import \{ LoginForm \} from "@\/components\/auth\/LoginForm"/);
      expect(out).toMatch(/export function LoginShell/);
    });
    it("LoginForm named-exports LoginForm and imports loginClient", () => {
      const out = preview("components/auth/LoginForm.tsx");
      expect(out).toMatch(/import \{ loginClient \} from "@\/lib\/api\/loginClient"/);
      expect(out).toMatch(/export function LoginForm/);
    });
    it("login.ts exports login() + LoginRequest + LOGIN_ENDPOINT", () => {
      const out = preview("lib/contracts/login.ts");
      expect(out).toMatch(/export interface LoginRequest/);
      expect(out).toMatch(/export async function login\(/);
      expect(out).toMatch(/export const LOGIN_ENDPOINT/);
    });
    it("route.ts imports the named login + LoginRequest from contracts", () => {
      const out = preview("app/api/login/route.ts");
      expect(out).toMatch(/import \{ login, type LoginRequest \} from "@\/lib\/contracts\/login"/);
    });
    it("loginClient.ts imports LOGIN_ENDPOINT + types from contracts and exports loginClient", () => {
      const out = preview("lib/api/loginClient.ts");
      expect(out).toMatch(/import \{ LOGIN_ENDPOINT, type LoginRequest, type LoginResponse \} from "@\/lib\/contracts\/login"/);
      expect(out).toMatch(/export const loginClient/);
    });
  });
});

describe("Login Epic gate completion semantics (blocker #1)", () => {
  const r0 = fixture.runs[0];
  const gates = r0.gates;
  // Pick a cursor that sits inside G2_EXECUTION (gates[2]) so G0/G1 are done,
  // G2 active, G3-G6 future. Use the route index of a G2 node + 1.
  const g2 = gates[2]; // G2_EXECUTION
  const g2FirstIdx = getRouteIndex(r0, g2.nodes[0].id); // first G2 node index
  const cursorInG2 = g2FirstIdx + 1;

  it("at cursor inside G2: G0/G1=done, G2=active, later=future", () => {
    expect(getGateState(r0, "G0_CONTEXT", cursorInG2)).toBe("done");
    expect(getGateState(r0, "G1_ALIGNMENT", cursorInG2)).toBe("done");
    expect(getGateState(r0, "G2_EXECUTION", cursorInG2)).toBe("active");
    expect(getGateState(r0, "G3_PR", cursorInG2)).toBe("future");
    expect(getGateState(r0, "G4_MERGE", cursorInG2)).toBe("future");
    expect(getGateState(r0, "G5_DEPLOY", cursorInG2)).toBe("future");
    expect(getGateState(r0, "G6_PRODUCTION", cursorInG2)).toBe("future");
  });

  it("at cursor inside G0: only G0 active, rest future", () => {
    const c = 0;
    expect(getGateState(r0, "G0_CONTEXT", c)).toBe("active");
    expect(getGateState(r0, "G1_ALIGNMENT", c)).toBe("future");
    expect(getGateState(r0, "G6_PRODUCTION", c)).toBe("future");
  });

  it("at last node: all gates done, G6 active", () => {
    const c = r0.route.length - 1;
    expect(getGateState(r0, "G0_CONTEXT", c)).toBe("done");
    expect(getGateState(r0, "G5_DEPLOY", c)).toBe("done");
    expect(getGateState(r0, "G6_PRODUCTION", c)).toBe("active");
  });

  it("prior completed gate never regresses to future as cursor advances", () => {
    for (let c = 0; c < r0.route.length; c++) {
      const g0 = getGateState(r0, "G0_CONTEXT", c);
      // G0 can only be active (at its own cursor) or done — never future once we pass it.
      if (c > 0) expect(g0).not.toBe("future");
    }
  });
});

describe("Login Epic viewport follow decision (blocker #5)", () => {
  it("genuine user move disables Follow", () => {
    expect(shouldDisableFollowOnMove(false)).toBe(true);
  });
  it("programmatic setCenter preserves Follow", () => {
    expect(shouldDisableFollowOnMove(true)).toBe(false);
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

