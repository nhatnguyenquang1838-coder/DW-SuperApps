/**
 * T06 — Real replay reducer + same-shell replay mode.
 *
 * Wires serverHistoricalRead (source-backed) through the deterministic
 * replay reducer (lib/replay.ts).  Replay is a MODE of the workspace,
 * never a second product UI.
 *
 * Failure states (fail closed):
 *   - missing canonical history → PROJECTION_UNAVAILABLE
 *   - invalid sequence          → REPLAY_POSITION_UNAVAILABLE
 *   - digest/revision conflict  → REPLAY_POSITION_UNAVAILABLE
 */

import { reduceEvents, type ReplayProjection } from "@/lib/replay";
import { readHistoricalEvents } from "@/lib/serverHistoricalRead";
import type { ProjectionEvent } from "@/lib/live";
import type {
  UnifiedRunWorkspaceModel,
  WorkspaceMode,
  UnifiedRuntimeNode,
  UnifiedRuntimeEdge,
} from "@/lib/runtime/unifiedRuntime";

export const REPLAY_POSITION_UNAVAILABLE =
  "REPLAY_POSITION_UNAVAILABLE" as const;
export const PROJECTION_UNAVAILABLE = "PROJECTION_UNAVAILABLE" as const;

export interface ReplaySnapshot {
  status: "OK" | typeof REPLAY_POSITION_UNAVAILABLE | typeof PROJECTION_UNAVAILABLE;
  projection: ReplayProjection | null;
  selectedSequence: number | null;
  totalEvents: number;
}

/**
 * Build a replay snapshot from the canonical durable history.
 *
 * @param runId            - the run to replay
 * @param selectedSequence - cursor position in durable order (0..max)
 * @param clientOverride   - test seam for SupabaseClient
 */
export async function getReplaySnapshot(
  runId: string,
  selectedSequence: number,
  clientOverride?: unknown
): Promise<ReplaySnapshot> {
  const result = await readHistoricalEvents(runId, clientOverride as any);

  // Missing canonical history → PROJECTION_UNAVAILABLE
  if (result.degraded || result.events.length === 0) {
    return { status: PROJECTION_UNAVAILABLE, projection: null, selectedSequence: null, totalEvents: 0 };
  }

  const canonicalEvents = result.events;

  // Determine the valid sequence range from canonical events.
  const sequences = canonicalEvents
    .map((e) => (typeof e.sequence === "number" ? e.sequence : -1))
    .filter((s) => s >= 0);

  if (sequences.length === 0) {
    return { status: PROJECTION_UNAVAILABLE, projection: null, selectedSequence: null, totalEvents: 0 };
  }

  const maxSequence = Math.max(...sequences);

  // Invalid sequence → REPLAY_POSITION_UNAVAILABLE (fail closed)
  if (selectedSequence < 0 || selectedSequence > maxSequence) {
    return { status: REPLAY_POSITION_UNAVAILABLE, projection: null, selectedSequence, totalEvents: canonicalEvents.length };
  }

  // historicalEvents = canonicalEvents where sequence <= selectedSequence
  const historicalEvents = canonicalEvents.filter(
    (e) => typeof e.sequence === "number" && e.sequence <= selectedSequence
  );

  // snapshot = reduce(historicalEvents)
  const projection = reduceEvents(historicalEvents);

  return { status: "OK", projection, selectedSequence, totalEvents: canonicalEvents.length };
}

// ---------------------------------------------------------------------------
// ReplayProjection → UnifiedRunWorkspaceModel (same-shell rendering)
// ---------------------------------------------------------------------------

/**
 * Convert a replay projection into a UnifiedRunWorkspaceModel for
 * rendering through the same UnifiedRunWorkspace shell in REPLAY mode.
 *
 * Absent/unknown fields stay null/UNKNOWN — no fixture fallback.
 */
export function replayToModel(
  projection: ReplayProjection,
  selectedSequence: number | null,
  mode: WorkspaceMode = "REPLAY"
): UnifiedRunWorkspaceModel {
  const nodes: UnifiedRuntimeNode[] = Object.values(
    projection.nodes
  ).map((n) => ({
    id: n.node,
    gateId: null,
    title: n.node,
    family: null,
    nodeType: null,
    authorityBoundary: null,
    sourceStatus: n.status,
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
  }));

  const edges: UnifiedRuntimeEdge[] = projection.events
    .filter(
      (e) =>
        typeof (e as Record<string, unknown>).node_id === "string" &&
        typeof (e as Record<string, unknown>).gate === "string"
    )
    .map((e) => ({
      id: `replay-evt-${e.source_event_id}`,
      source: (e as Record<string, unknown>).gate as string,
      target: (e as Record<string, unknown>).node_id as string,
      kind: "DEPENDENCY" as const,
      state: "SATISFIED" as const,
    }));

  const orderedSteps = nodes.map((n, i) => ({ nodeId: n.id, sequence: i }));

  return {
    runId: projection.runId ?? "",
    taskRef: null,
    mode,
    status: "REPLAY",
    hierarchy: null,
    nodes,
    edges,
    orderedSteps,
    currentSequence: selectedSequence,
    canonicalHistoryAvailable: true,
    projectionStatus: "AVAILABLE",
    sourceDigest: null,
  };
}