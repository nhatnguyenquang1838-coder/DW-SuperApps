/**
 * Real runtime adapter — reads from the canonical server run path
 * (lib/serverRunRead.ts, lib/serverHistoricalRead.ts, lib/observatory.ts)
 * and maps the result to the UnifiedRunWorkspaceModel.
 *
 * If the canonical source cannot supply a field, leaves it null/UNKNOWN.
 * Does NOT fall back to fixtures.
 *
 * Pure TypeScript — no React import, no DOM access.
 */

import type {
  UnifiedRuntimeNode,
  UnifiedRuntimeEdge,
  UnifiedRunWorkspaceModel,
  WorkspaceMode,
} from "../unifiedRuntime";
import { UNKNOWN } from "@/lib/observatory";
import { readServerRunDetail } from "@/lib/serverRunRead";
import { readHistoricalEvents } from "@/lib/serverHistoricalRead";

/** Map a raw server state string to the closest unified sourceStatus. */
function mapSourceStatus(state: string | null | undefined): string | null {
  if (!state) return null;
  const upper = state.toUpperCase();
  const vocabulary = new Set([
    "PENDING", "GRANTED", "DENIED", "EXPIRED", "REVOKED",
    "NOT_REQUIRED", "UNKNOWN",
  ]);
  if (vocabulary.has(upper)) return upper;
  switch (upper) {
    case "OPEN":
    case "ACTIVE":
      return "PENDING";
    case "COMPLETED":
    case "ACCEPTED":
    case "PASSED":
      return "GRANTED";
    case "FAILED":
      return "DENIED";
    case "CANCELLED":
      return "REVOKED";
    case "BLOCKED":
      return "BLOCKED";
    default:
      return null;
  }
}

/**
 * Adapt server-side run data to the unified model.
 * When the server is unavailable, returns a fully-degraded model
 * with all fields null/UNKNOWN — no fixture fallback.
 */
export async function realRuntimeAdapter(
  runId: string,
): Promise<UnifiedRunWorkspaceModel> {
  const detail = await readServerRunDetail(runId);
  const history = await readHistoricalEvents(runId);

  if (detail.degraded) {
    return {
      runId,
      taskRef: null,
      mode: "LIVE" as WorkspaceMode,
      status: "UNKNOWN",
      hierarchy: null,
      nodes: [],
      edges: [],
      orderedSteps: [],
      currentSequence: null,
      canonicalHistoryAvailable: false,
      projectionStatus: "PROJECTION_UNAVAILABLE",
      sourceDigest: null,
    };
  }

  const nodes: UnifiedRuntimeNode[] = [];
  const edges: UnifiedRuntimeEdge[] = [];

  for (const gate of detail.gates) {
    const gateId = (gate.gate_id as string) ?? null;
    nodes.push({
      id: gateId ?? UNKNOWN,
      gateId,
      title: (gate.gate_label as string) ?? UNKNOWN,
      family: null,
      nodeType: null,
      authorityBoundary: (gate.boundary as string) ?? null,
      sourceStatus: mapSourceStatus((gate.state as string) ?? null),
      maturity: null,
      declaredGates: [],
      purpose: null,
      fileReads: [],
      fileWrites: [],
      artifacts: [],
      runbook: [],
      taskControllerHistory: [],
      executorHistory: [],
      checkpoints: [],
    });
  }

  for (const row of detail.nodes) {
    const nodeId = (row.node_id as string) ?? UNKNOWN;
    nodes.push({
      id: nodeId,
      gateId: (row.gate_id as string) ?? null,
      title: (row.label as string) ?? UNKNOWN,
      family: (row.family as string) ?? null,
      nodeType: null,
      authorityBoundary: (row.boundary as string) ?? null,
      sourceStatus: mapSourceStatus((row.state as string) ?? null),
      maturity: null,
      declaredGates: [],
      purpose: null,
      fileReads: [],
      fileWrites: [],
      artifacts: [],
      runbook: [],
      taskControllerHistory: [],
      executorHistory: [],
      checkpoints: [],
    });
  }

  // --- Dependency edges: canonical evidence only ---
  // Event/gate membership is NOT dependency evidence.
  // If the source provides no dependency evidence, edges stay empty.
  // (No DEPENDENCY edges fabricated here — see task SCRUM-820 P3.)

  // --- orderedSteps: durable sequences from canonical events ---
  const nodeSequence = new Map<string, number>();
  for (const evt of history.events) {
    const nodeId =
      typeof (evt as { node_id?: unknown }).node_id === "string"
        ? ((evt as { node_id?: unknown }).node_id as string)
        : null;
    if (nodeId && typeof evt.sequence === "number") {
      const existing = nodeSequence.get(nodeId);
      if (existing === undefined || evt.sequence > existing) {
        nodeSequence.set(nodeId, evt.sequence);
      }
    }
  }

  // Only include nodes that have canonical event evidence (fail-closed).
  const orderedSteps = nodes
    .filter((n) => n.id !== UNKNOWN && nodeSequence.has(n.id))
    .map((n) => ({ nodeId: n.id, sequence: nodeSequence.get(n.id)! }))
    .sort((a, b) => a.sequence - b.sequence);

  return {
    runId: (detail.run?.run_id as string) ?? runId,
    taskRef: null,
    mode: "LIVE" as WorkspaceMode,
    status: detail.run
      ? (detail.run.status as string) ?? UNKNOWN
      : UNKNOWN,
    hierarchy: null,
    nodes,
    edges,
    orderedSteps,
    currentSequence: null,
    canonicalHistoryAvailable: detail.canonicalHistoryAvailable,
    projectionStatus: detail.projectionStatus,
    sourceDigest: null,
  };
}
