/**
 * Login Auth scenario adapter — adapts lib/loginEpicRuntimeGraph.ts output
 * to the UnifiedRunWorkspaceModel.
 *
 * Pure TypeScript — no React import, no DOM access.
 */

import type {
  UnifiedRuntimeNode,
  UnifiedRuntimeEdge,
  UnifiedRunWorkspaceModel,
  WorkspaceMode,
} from "../unifiedRuntime";
import type { LoginEpicRuntimeFixture, RuntimeNode, RouteStep } from "@/lib/loginEpicRuntimeGraph";
import { GATE_CHAIN } from "@/lib/loginEpicRuntimeGraph";

/** Map login-epic NodeState ("done"/"active"/"future") to UnifiedRuntimeState. */
function mapNodeState(es: string | null): UnifiedRuntimeNode["sourceStatus"] {
  if (es === null) return null;
  switch (es) {
    case "done":
      return "DONE";
    case "active":
      return "ACTIVE";
    case "future":
      return "FUTURE";
    default:
      return "UNKNOWN";
  }
}

/** Convert a RuntimeNode to UnifiedRuntimeNode. */
function nodeFromRuntime(
  n: RuntimeNode,
  gateId: string | null,
  nodeState: string | null,
): UnifiedRuntimeNode {
  return {
    id: n.id,
    gateId,
    title: n.title,
    family: n.family ?? null,
    nodeType: n.type ?? null,
    authorityBoundary: n.boundary ?? null,
    sourceStatus: mapNodeState(nodeState),
    maturity: null,
    declaredGates: [],
    purpose: n.purpose ?? null,
    fileReads: n.fileReads ?? [],
    fileWrites: n.fileWrites ?? [],
    artifacts: n.artifacts ?? [],
    runbook: n.runbook ?? [],
    taskControllerHistory: n.taskControllerHistory ?? [],
    executorHistory: n.executorHistory ?? [],
    checkpoints: n.checkpoints ?? [],
  };
}

/**
 * Adapt a LoginEpicRuntimeFixture + runId into the unified model.
 * If runId is omitted, uses the first run in the fixture.
 */
export function loginAuthScenarioAdapter(
  fixture: LoginEpicRuntimeFixture,
  runId?: string,
): UnifiedRunWorkspaceModel {
  const run = runId
    ? fixture.runs.find((r) => r.id === runId) ?? fixture.runs[0]
    : fixture.runs[0];

  const nodes: UnifiedRuntimeNode[] = [];
  const edges: UnifiedRuntimeEdge[] = [];

  // Build nodes from gates + their runtime nodes.
  for (const gate of run.gates) {
    for (const n of gate.nodes) {
      const state =
        n.family === "runtime"
          ? mapNodeState("future")
          : mapNodeState("active");
      nodes.push(nodeFromRuntime(n, gate.id as string | null, state));
    }
  }

  // Gate dependency edges (G0->G1->...->G6).
  const gateChain = [...GATE_CHAIN];
  for (let i = 0; i < gateChain.length - 1; i++) {
    const fromGate = run.gates.find((g) => g.id === gateChain[i]);
    const toGate = run.gates.find((g) => g.id === gateChain[i + 1]);
    if (fromGate?.nodes.length && toGate?.nodes.length) {
      edges.push({
        id: `gate-${gateChain[i]}-${gateChain[i + 1]}`,
        source: fromGate.nodes[fromGate.nodes.length - 1].id,
        target: toGate.nodes[0].id,
        kind: "DEPENDENCY",
        state: "SATISFIED",
      });
    }
  }

  // Route edges from run.route.
  const route: RouteStep[] = run.route ?? [];
  for (let i = 0; i < route.length - 1; i++) {
    edges.push({
      id: `route-${i}`,
      source: route[i].node_id,
      target: route[i + 1].node_id,
      kind: "ROUTE",
      state: "SATISFIED",
    });
  }

  // Fanout edges: when a node has multiple outgoing route targets,
  // mark them as FANOUT. (Login epic route is linear, so this is
  // defensive — only emits when the route forks.)
  const routeTargets = new Set(route.slice(1).map((r) => r.node_id));
  for (const step of route) {
    if (!routeTargets.has(step.node_id)) {
      // This node is not a target of any route edge — it's a fanout source.
      const outgoing = route.filter((r) => {
        const ix = route.indexOf(step);
        return ix >= 0 && route[ix + 1]?.node_id === step.node_id;
      });
      if (outgoing.length > 1) {
        for (const out of outgoing) {
          edges.push({
            id: `fanout-${step.node_id}-${out.node_id}`,
            source: step.node_id,
            target: out.node_id,
            kind: "FANOUT",
            state: "UNKNOWN",
          });
        }
      }
    }
  }

  const orderedSteps = route.map((r, i) => ({ nodeId: r.node_id, sequence: i }));

  return {
    runId: run.id,
    taskRef: null,
    mode: "SIMULATED" as WorkspaceMode,
    status: run.status ?? "UNKNOWN",
    hierarchy: null,
    nodes,
    edges,
    orderedSteps,
    currentSequence: null,
    canonicalHistoryAvailable: false,
    projectionStatus: "UNKNOWN",
    sourceDigest: null,
  };
}
