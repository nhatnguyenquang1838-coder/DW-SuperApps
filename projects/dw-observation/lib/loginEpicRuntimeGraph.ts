/**
 * Login Epic GWC Runtime Graph — types + pure engine.
 *
 * Data shape follows the Controller-transferred fixture
 * (fixtures/login_epic_10_runs_gwc_taskcontroller_data.json, emitted as
 * `window.EPIC = {...}`). Every function here is PURE (no React/DOM/browser).
 *
 * Mental model: Epic -> 10 Runs -> each Run owns G0..G6 -> each Gate owns
 * Runtime Nodes -> each Node owns fileReads/fileWrites/artifacts/runbook/
 * taskControllerHistory/executorHistory/checkpoints.
 */

export type GateId =
  | "G0_CONTEXT"
  | "G1_ALIGNMENT"
  | "G2_EXECUTION"
  | "G3_PR"
  | "G4_MERGE"
  | "G5_DEPLOY"
  | "G6_PRODUCTION";

export const GATE_CHAIN: GateId[] = [
  "G0_CONTEXT",
  "G1_ALIGNMENT",
  "G2_EXECUTION",
  "G3_PR",
  "G4_MERGE",
  "G5_DEPLOY",
  "G6_PRODUCTION",
];

export type NodeState = "done" | "active" | "future";
export type ReplayMode = "REPLAY" | "LIVE_SIM";
export type RunKind =
  | "planning"
  | "design"
  | "implementation"
  | "quality"
  | "observability_deploy_boundary";

export interface RuntimeNode {
  gate_id: GateId;
  id: string;
  title: string;
  family: string;
  type: string;
  boundary: string;
  purpose: string;
  fileReads: string[];
  fileWrites: string[];
  artifacts: string[];
  runbook: string[];
  taskControllerHistory: string[];
  executorHistory: string[];
  checkpoints: string[];
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface RuntimeGate {
  id: GateId;
  label: string;
  summary: string;
  x: number;
  y: number;
  w: number;
  h: number;
  nodes: RuntimeNode[];
  gateArtifacts: string[];
  taskControllerHistory: string[];
  executorHistory: string[];
}

export interface RouteStep {
  gate_id: GateId;
  node_id: string;
}

export interface LoginEpicRun {
  id: string;
  index: number;
  slug: string;
  title: string;
  objective: string;
  run_kind: RunKind;
  allowed_paths: string[];
  forbidden_actions: string[];
  gates: RuntimeGate[];
  route: RouteStep[];
  status: string;
  summary: string;
}

export interface LoginEpicRuntimeFixture {
  epic_id: "LOGIN-CAPABILITY";
  title: string;
  run_count: 10;
  runtime_node_count: number;
  runtime_model: string;
  runs: LoginEpicRun[];
}

/* ----------------------------- selectors ------------------------------ */

export function getRun(fixture: LoginEpicRuntimeFixture, runId: string): LoginEpicRun {
  const r = fixture.runs.find((x) => x.id === runId);
  if (!r) throw new Error(`run not found: ${runId}`);
  return r;
}

export function getGate(run: LoginEpicRun, gateId: GateId): RuntimeGate {
  const g = run.gates.find((x) => x.id === gateId);
  if (!g) throw new Error(`gate not found: ${gateId}`);
  return g;
}

export function getRuntimeNode(
  run: LoginEpicRun,
  nodeId: string,
): { gate: RuntimeGate; node: RuntimeNode } {
  for (const g of run.gates) {
    const n = g.nodes.find((x) => x.id === nodeId);
    if (n) return { gate: g, node: n };
  }
  throw new Error(`node not found: ${nodeId}`);
}

export function getRouteIndex(run: LoginEpicRun, nodeId: string): number {
  return run.route.findIndex((s) => s.node_id === nodeId);
}

export function clampCursor(run: LoginEpicRun, cursor: number): number {
  const len = run.route.length;
  if (len === 0) return 0;
  return Math.max(0, Math.min(len - 1, cursor));
}

export function getActiveRoute(
  run: LoginEpicRun,
  cursor: number,
): { gate_id: GateId; node_id: string } {
  return run.route[clampCursor(run, cursor)];
}

export function getNodeState(
  run: LoginEpicRun,
  nodeId: string,
  cursor: number,
): NodeState {
  const ix = getRouteIndex(run, nodeId);
  if (ix < 0) return "future";
  if (ix < cursor) return "done";
  if (ix === cursor) return "active";
  return "future";
}

export function getGateState(
  run: LoginEpicRun,
  gateId: GateId,
  cursor: number,
): "done" | "active" | "future" | "empty" {
  const gate = getGate(run, gateId);
  if (!gate.nodes.length) return "empty";
  const c = clampCursor(run, cursor);
  const active = getActiveRoute(run, c);
  // Active gate: the cursor's current node belongs to this gate.
  if (active.gate_id === gateId && getNodeState(run, active.node_id, c) === "active")
    return "active";
  // Route indices of THIS gate's nodes.
  const gateNodeIds = new Set(gate.nodes.map((n) => n.id));
  const idxs = run.route
    .map((s, i) => ({ s, i }))
    .filter(({ s }) => s.gate_id === gateId && gateNodeIds.has(s.node_id))
    .map(({ i }) => i);
  if (idxs.length === 0) return "future";
  // Done only when every node of the gate is strictly before the cursor.
  // Future when any node is after the cursor (covers prior-completed gates that
  // still have nodes inside the sliced prefix -> they are NOT future, they are done).
  return idxs.every((i) => i < c) ? "done" : "future";
}

export interface RuntimeEdgeModel {
  id: string;
  source: string;
  target: string;
  kind: "gate" | "route";
}

/** Gate dependency edges G0 -> G1 -> ... -> G6 (connect last node of gate to first of next). */
export function buildGateEdges(run: LoginEpicRun): RuntimeEdgeModel[] {
  const edges: RuntimeEdgeModel[] = [];
  for (let i = 0; i < run.gates.length - 1; i++) {
    const from = run.gates[i];
    const to = run.gates[i + 1];
    const a = from.nodes[from.nodes.length - 1];
    const b = to.nodes[0];
    if (a && b)
      edges.push({
        id: `gate-${from.id}-${to.id}`,
        source: a.id,
        target: b.id,
        kind: "gate",
      });
  }
  return edges;
}

/** Route edges following run.route (node i -> node i+1). */
export function buildRouteEdges(run: LoginEpicRun): RuntimeEdgeModel[] {
  const edges: RuntimeEdgeModel[] = [];
  for (let i = 0; i < run.route.length - 1; i++) {
    edges.push({
      id: `route-${i}`,
      source: run.route[i].node_id,
      target: run.route[i + 1].node_id,
      kind: "route",
    });
  }
  return edges;
}

/**
 * Id of the active route edge at the current cursor (the one that animates).
 * Returns null at the last node (no outgoing edge). Deterministic source of truth
 * for the `runtime-active-edge` marker rendered by RuntimeEdge.
 */
export function getActiveRouteEdgeId(run: LoginEpicRun, cursor: number): string | null {
  const c = clampCursor(run, cursor);
  if (c < 0 || c >= run.route.length - 1) return null;
  return `route-${c}`;
}

/**
 * Pure viewport-Follow decision (blocker #5 evidence).
 * A genuine user pan/zoom disables Follow; a programmatic setCenter (follow-cursor)
 * must NOT. Deterministic and unit-testable independently of React Flow.
 */
export function shouldDisableFollowOnMove(isProgrammatic: boolean): boolean {
  return !isProgrammatic;
}

/** Deterministic synthetic artifact preview (no real secrets/config). */
export function makeArtifactPreview(args: {
  run: LoginEpicRun;
  gate?: RuntimeGate;
  node?: RuntimeNode;
  path: string;
  cursor: number;
}): string {
  const { run, gate, node, path } = args;
  const suffix = path.split(".").pop() ?? "txt";
  const base = {
    path,
    epic: "LOGIN-CAPABILITY",
    run_id: run.id,
    gate_id: gate?.id ?? node?.gate_id ?? "GATE",
    node_id: node?.id ?? "node",
    status: "simulated",
    source_basis: "controller-transferred reference fixture (no real secrets)",
  };

  // Enriched, internally-consistent simulated source-code previews for the Login
  // Capability deliverables. Keyed by the file's trailing path segment so both
  // node-agnostic and node-scoped opens render the same deterministic content.
  // Import/export graph is coherent: page.tsx default-exports LoginPage and
  // imports the named LoginShell; LoginShell imports the named LoginForm;
  // LoginForm imports loginClient; route.ts + loginClient.ts import from
  // contracts/login.ts (which exports login + types + LOGIN_ENDPOINT).
  // UX matches the approved contract: username / password / CTA "Login".
  const seg = path.split("/").pop() ?? path;
  const SOURCE_PREVIEWS: Record<string, string> = {
    "page.tsx": `// app/login/page.tsx (simulated source-code write preview)
// Purpose: ${node?.purpose ?? "Render the login route entry screen"}
// Boundary: ${node?.boundary ?? "product/ui"}
import { LoginShell } from "@/components/auth/LoginShell";

export default function LoginPage() {
  return <LoginShell />;
}`,
    "LoginShell.tsx": `// components/auth/LoginShell.tsx (simulated source-code write preview)
// Purpose: ${node?.purpose ?? "Compose the login screen shell"}
// Boundary: ${node?.boundary ?? "product/ui"}
import { LoginForm } from "@/components/auth/LoginForm";

export function LoginShell() {
  return (
    <main className="login-shell">
      <h1>Login</h1>
      <LoginForm />
    </main>
  );
}`,
    "LoginForm.tsx": `// components/auth/LoginForm.tsx (simulated source-code write preview)
// Purpose: ${node?.purpose ?? "Login form state machine"}
// Boundary: ${node?.boundary ?? "product/ui"}
"use client";
import { useState } from "react";
import { loginClient } from "@/lib/api/loginClient";

export function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  return (
    <form onSubmit={async (e) => {
      e.preventDefault();
      await loginClient.signIn({ username, password });
    }}>
      <input aria-label="username" value={username} onChange={(e) => setUsername(e.target.value)} />
      <input aria-label="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <button type="submit">Login</button>
    </form>
  );
}`,
    "login.ts": `// lib/contracts/login.ts (simulated source-code write preview)
// Purpose: ${node?.purpose ?? "Login API contract types"}
// Boundary: ${node?.boundary ?? "shared/contract"}
export interface LoginRequest { username: string; password: string; }
export interface LoginResponse { token: string; expiresIn: number; }
export const LOGIN_ENDPOINT = "/api/login" as const;

export async function login(req: LoginRequest): Promise<LoginResponse> {
  const r = await fetch(LOGIN_ENDPOINT, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
  });
  return r.json();
}`,
    "route.ts": `// app/api/login/route.ts (simulated source-code write preview)
// Purpose: ${node?.purpose ?? "Login API route handler"}
// Boundary: ${node?.boundary ?? "backend/api"}
import { login, type LoginRequest } from "@/lib/contracts/login";
import { json } from "@/lib/http";

export async function POST(req: Request) {
  const body = (await req.json()) as LoginRequest;
  const res = await login(body);
  return json(res, { status: 200 });
}`,
    "loginClient.ts": `// lib/api/loginClient.ts (simulated source-code write preview)
// Purpose: ${node?.purpose ?? "Login API client"}
// Boundary: ${node?.boundary ?? "client/api"}
import { LOGIN_ENDPOINT, type LoginRequest, type LoginResponse } from "@/lib/contracts/login";

export const loginClient = {
  async signIn(req: LoginRequest): Promise<LoginResponse> {
    const r = await fetch(LOGIN_ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
    });
    return r.json();
  },
};`,
  };
  if (seg in SOURCE_PREVIEWS && (suffix === "ts" || suffix === "tsx")) {
    return SOURCE_PREVIEWS[seg];
  }

  if (suffix === "yaml" || suffix === "yml") {
    return [
      `path: ${base.path}`,
      `run_id: ${base.run_id}`,
      `gate_id: ${base.gate_id}`,
      `node_id: ${base.node_id}`,
      `status: ${base.status}`,
      `purpose: ${node?.purpose ?? ""}`,
      `boundary: ${node?.boundary ?? ""}`,
      `source_basis: ${base.source_basis}`,
    ].join("\n");
  }
  if (suffix === "ts" || suffix === "tsx") {
    return [
      `// ${base.path} (simulated preview)`,
      `// run=${base.run_id} gate=${base.gate_id} node=${base.node_id}`,
      `export const PURPOSE = ${JSON.stringify(node?.purpose ?? "")};`,
      `export const BOUNDARY = ${JSON.stringify(node?.boundary ?? "")};`,
    ].join("\n");
  }
  return JSON.stringify({ ...base, node_title: node?.title }, null, 2);
}

