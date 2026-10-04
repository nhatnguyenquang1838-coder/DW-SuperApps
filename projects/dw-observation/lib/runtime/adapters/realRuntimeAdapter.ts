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
import { readServerConfig, readServerRunDetail } from "@/lib/serverRunRead";
import { readHistoricalEvents } from "@/lib/serverHistoricalRead";

/** Map a raw server state string to the closest unified sourceStatus. */
function mapSourceStatus(state: string | null | undefined): string | null {
  if (!state) return null;
  const upper = state.toUpperCase();
  // Direct vocabulary matches from authorityVocabulary.
  const vocabulary = new Set([
    "PENDING", "GRANTED", "DENIED", "EXPIRED", "REVOKED",
    "NOT_REQUIRED", "UNKNOWN",
  ]);
  if (vocabulary.has(upper)) return upper;
  // Common run state mappings — keep them close to the vocabulary.
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
  const cfg = readServerConfig();
  const detail = await readServerRunDetail(runId);
  const history = await readHistoricalEvents(runId);

  // If the server read is degraded, return fully unknown — no fallback.
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

  // Map server gates → nodes (one node per gate as a summary).
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

  // Map server nodes → nodes with detail.
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

  // Map projection events → edges (recorded relationships only).
  for (const evt of history.events) {
    if (evt.nodeId && evt.gate) {
      edges.push({
        id: `evt-${evt.sourceEventId}`,
        source: evt.gate as string,
        target: evt.nodeId as string,
        kind: "DEPENDENCY",
        state: "SATISFIED",
      });
    }
  }

  const orderedSteps = nodes.map((n, i) => ({ nodeId: n.id, sequence: i }));

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
