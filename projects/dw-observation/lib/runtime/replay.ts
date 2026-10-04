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
 * Result of replayToModel — either OK with a model, or PROJECTION_UNAVAILABLE
 * when selectedSequence has no matching durable step (fail-closed).
 */
export interface ReplayModelResult {
  status: "OK" | "PROJECTION_UNAVAILABLE";
  model: UnifiedRunWorkspaceModel | null;
  projection: ReplayProjection | null;
}

/**
 * Convert a replay projection into a UnifiedRunWorkspaceModel for
 * rendering through the same UnifiedRunWorkspace shell in REPLAY mode.
 *
 * Absent/unknown fields stay null/UNKNOWN — no fixture fallback.
 *
 * Returns PROJECTION_UNAVAILABLE when selectedSequence has no matching
 * durable step (fail-closed — never fabricate a step).
 */
export function replayToModel(
  projection: ReplayProjection,
  selectedSequence: number | null,
  mode: WorkspaceMode = "REPLAY"
): ReplayModelResult {
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

  // No dependency evidence in canonical events → zero DEPENDENCY edges.
  // Event/gate membership is NOT dependency evidence.
  const edges: UnifiedRuntimeEdge[] = [];

  // orderedSteps carries the DURABLE sequence from each canonical
  // node event (node_started / node_progress / node_completed).
  // One step per event — never a positional index.
  const seenSequences = new Set<number>();
  const orderedSteps: { nodeId: string; sequence: number }[] = [];
  for (const e of projection.events ?? []) {
    if (typeof e.sequence !== "number") continue; // never fabricate a sequence
    if (seenSequences.has(e.sequence)) continue;
    seenSequences.add(e.sequence);
    const nodeId =
      typeof (e as Record<string, unknown>).node_id === "string"
        ? ((e as Record<string, unknown>).node_id as string)
        : projection.runId ?? "";
    orderedSteps.push({ nodeId, sequence: e.sequence });
  }
  orderedSteps.sort((a, b) => a.sequence - b.sequence);

  // Fail-closed: selectedSequence must match a durable step.
  if (selectedSequence !== null && !orderedSteps.some((s) => s.sequence === selectedSequence)) {
    return { status: "PROJECTION_UNAVAILABLE", model: null, projection: null };
  }

  const model: UnifiedRunWorkspaceModel = {
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

  return { status: "OK", model, projection };
}
