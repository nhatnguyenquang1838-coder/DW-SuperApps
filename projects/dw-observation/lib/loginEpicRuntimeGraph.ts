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
  const active = getActiveRoute(run, cursor);
  if (active.gate_id === gateId && getNodeState(run, active.node_id, cursor) === "active")
    return "active";
  // gate is done if all its nodes have route index < cursor
  const gateNodeIds = new Set(gate.nodes.map((n) => n.id));
  const cursorRoute = run.route.slice(0, clampCursor(run, cursor) + 1);
  const cursorInGate = cursorRoute.some(
    (s) => s.gate_id === gateId && gateNodeIds.has(s.node_id),
  );
  if (!cursorInGate) {
    // if any gate node appears after cursor => future
    const after = run.route.slice(clampCursor(run, cursor) + 1);
    return after.some((s) => s.gate_id === gateId && gateNodeIds.has(s.node_id))
      ? "future"
      : "done";
  }
  return "future";
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
