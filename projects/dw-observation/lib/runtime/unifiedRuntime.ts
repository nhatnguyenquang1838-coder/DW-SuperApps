/**
 * Unified runtime domain model — DWO v2 Penpot spec §5.
 *
 * Renderer-neutral model shared by real runtime data and simulations.
 * Pure TypeScript — no React import, no DOM access.
 */

export type WorkspaceMode = "LIVE" | "REPLAY" | "SIMULATED";

export type RuntimeNodeState =
  | "DONE"
  | "ACTIVE"
  | "FUTURE"
  | "BLOCKED"
  | "WAITING"
  | "UNKNOWN";

export interface UnifiedRuntimeNode {
  id: string;
  gateId: string | null;
  title: string;
  family: string | null;
  nodeType: string | null;
  authorityBoundary: string | null;
  sourceStatus: string | null;
  maturity: string | null;
  declaredGates: string[];
  purpose: string | null;
  fileReads: string[];
  fileWrites: string[];
  artifacts: string[];
  runbook: string[];
  taskControllerHistory: unknown[];
  executorHistory: unknown[];
  checkpoints: unknown[];
}

export interface UnifiedRuntimeEdge {
  id: string;
  source: string;
  target: string;
  kind: "DEPENDENCY" | "ROUTE" | "FANOUT";
  state: "SATISFIED" | "BLOCKING" | "UNKNOWN";
}

export interface UnifiedRunWorkspaceModel {
  runId: string;
  taskRef: string | null;
  mode: WorkspaceMode;
  status: string;
  hierarchy: unknown;
  nodes: UnifiedRuntimeNode[];
  edges: UnifiedRuntimeEdge[];
  orderedSteps: Array<{ nodeId: string; sequence: number }>;
  currentSequence: number | null;
  canonicalHistoryAvailable: boolean;
  projectionStatus: string;
  sourceDigest: string | null;
}
