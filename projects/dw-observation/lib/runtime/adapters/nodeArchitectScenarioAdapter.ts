/**
 * Node Architect scenario adapter — adapts lib/simRun.ts output
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
import type { SimRun, SimNode, SimGate } from "@/lib/simRun";

/** Map node_state ("done"/"active"/"future") to UnifiedRuntimeState. */
function mapSourceState(state: string): UnifiedRuntimeNode["sourceStatus"] {
  switch (state) {
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

/** Convert a SimNode to UnifiedRuntimeNode. */
function nodeFromSimNode(gateId: string, n: SimNode): UnifiedRuntimeNode {
  return {
    id: n.node_id,
    gateId,
    title: n.title,
    family: n.family ?? null,
    nodeType: n.node_type ?? null,
    authorityBoundary: n.authority_boundary ?? null,
    sourceStatus: n.source_status
      ? mapSourceState(n.source_status)
      : null,
    maturity: n.maturity ?? null,
    declaredGates: n.declared_gates ?? [],
    purpose: null,
    fileReads: n.reads ?? [],
    fileWrites: [],
    artifacts: n.artifacts ?? [],
    runbook: n.runbook ?? [],
    taskControllerHistory: n.taskcontroller_history ?? [],
    executorHistory: n.executor_history ?? [],
    checkpoints: n.checkpoints ?? [],
  };
}

/**
 * Adapt a SimRun into the unified model.
 */
export function nodeArchitectScenarioAdapter(
  run: SimRun,
): UnifiedRunWorkspaceModel {
  const nodes: UnifiedRuntimeNode[] = [];
  const edges: UnifiedRuntimeEdge[] = [];

  // Build nodes and track sequence order.
  const sequenceByNodeId = new Map<string, number>();
  for (const gate of run.gates) {
    for (let i = 0; i < gate.nodes.length; i++) {
      const n = gate.nodes[i];
      sequenceByNodeId.set(n.node_id, i);
      nodes.push(nodeFromSimNode(gate.id, n));
    }
  }

  // Sort nodes by sequence within each gate.
  nodes.sort((a, b) => {
    const seqA = sequenceByNodeId.get(a.id) ?? 0;
    const seqB = sequenceByNodeId.get(b.id) ?? 0;
    return seqA - seqB;
  });

  // Gate dependency edges (parent/child from hierarchy + dependency refs).
  // SimRun has no explicit dependency edges, so we derive DEPENDENCY
  // only from the recorded parent/child structure — never from layout.
  const byId = new Map<string, SimNode>();
  for (const gate of run.gates) {
    for (const n of gate.nodes) {
      byId.set(n.node_id, n);
    }
  }

  // Build orderedSteps from timeline order.
  const timelineEntries = Array.from(sequenceByNodeId.entries())
    .sort((a, b) => a[1] - b[1])
    .map(([nodeId, sequence]) => ({ nodeId, sequence }));

  // Determine hierarchy (parent/child) from catalog data if available.
  // SimRun itself carries no hierarchy field — set to null.
  const hierarchy = null;

  return {
    runId: run.run_id,
    taskRef: run.task_id ?? null,
    mode: "SIMULATED" as WorkspaceMode,
    status: run.status ?? "UNKNOWN",
    hierarchy,
    nodes,
    edges,
    orderedSteps: timelineEntries,
    currentSequence: null,
    canonicalHistoryAvailable: false,
    projectionStatus: "UNKNOWN",
    sourceDigest: null,
  };
}
