/**
 * T07 — Source-backed Next Flow projection.
 *
 * TECH_SPEC §7: Next Flow must be source-backed.
 *
 * Rules:
 *  - NO graph-position inference (no visual adjacency/layout/coordinates)
 *  - NO guessing from sequence when the source contract does not authorize it
 * *  - Conflicting sources => CONFLICT
 *  - Missing source => UNKNOWN
 *  - Replay computes Next Flow as-of the selected historical sequence only
 */

import type { UnifiedRunWorkspaceModel, WorkspaceMode } from "./unifiedRuntime";
import type { BlockingPath } from "../dwo/blockingPath";

export type NextFlowSource = "DURABLE_RUNTIME" | "REPLAY_SNAPSHOT" | "FIXTURE";

export interface NextFlowProjection {
  currentNodeId: string | null;
  nextNodeId: string | null;
  reason: string | null;
  blocker: string | null;
  source: NextFlowSource;
  status: "RESOLVED" | "UNKNOWN" | "BLOCKED" | "CONFLICT";
}

/** Map workspace mode to the source tag used in the projection. */
function modeToSource(mode: WorkspaceMode): NextFlowSource {
  switch (mode) {
    case "LIVE":
      return "DURABLE_RUNTIME";
    case "REPLAY":
      return "REPLAY_SNAPSHOT";
    case "SIMULATED":
      return "FIXTURE";
  }
}

/**
 * Derive the NextFlowProjection from the unified run workspace model.
 *
 * Lookup is by sequence number (the source contract field), NOT by array
 * position — this is what the shuffle negative test proves: reordering the
 * orderedSteps array must not change the result.
 *
 * @param model     - the unified runtime model (source-backed)
 * @param options   - optional blockingPath override for conflict detection
 */
export function computeNextFlow(
  model: UnifiedRunWorkspaceModel,
  options?: { blockingPath?: BlockingPath | null }
): NextFlowProjection {
  const source = modeToSource(model.mode);

  // Missing source data => UNKNOWN (fail closed, never guess)
  if (model.currentSequence == null) {
    return {
      currentNodeId: null,
      nextNodeId: null,
      reason: "No current sequence — source data unavailable",
      blocker: null,
      source,
      status: "UNKNOWN",
    };
  }

  if (!model.orderedSteps || model.orderedSteps.length === 0) {
    return {
      currentNodeId: null,
      nextNodeId: null,
      reason: "No ordered steps — source data unavailable",
      blocker: null,
      source,
      status: "UNKNOWN",
    };
  }

  const seq = model.currentSequence; // narrowed to number after null check above

  // Derive currentNodeId by matching the sequence field (NOT array index).
  const currentStep = model.orderedSteps.find(
    (s) => s.sequence === seq
  );
  const currentNodeId = currentStep?.nodeId ?? null;

  // Derive nextNodeId by matching currentSequence + 1 in the sequence field.
  const nextStep = model.orderedSteps.find(
    (s) => s.sequence === seq + 1
  );
  const nextNodeIdFromSteps = nextStep?.nodeId ?? null;

  // Derive candidate next nodes from dependency edges (source contract).
  const nextNodeIdFromEdges = deriveNextFromEdges(model, currentNodeId);

  // Conflict detection: orderedSteps and edges disagree on the next node.
  const hasConflict =
    nextNodeIdFromSteps !== null &&
    nextNodeIdFromEdges !== null &&
    nextNodeIdFromSteps !== nextNodeIdFromEdges;

  if (hasConflict) {
    return {
      currentNodeId,
      nextNodeId: null,
      reason: `conflict: orderedSteps says ${nextNodeIdFromSteps}, edges say ${nextNodeIdFromEdges}`,
      blocker: null,
      source,
      status: "CONFLICT",
    };
  }

  // Conflict detection: multiple satisfied edges for the current node with
  // no ordered-step disambiguation is a CONFLICT — surfaced as CONFLICT, not
  // RESOLVED with a sentinel nextNodeId (fail-closed).
  if (hasEdgeConflict(model, currentNodeId)) {
    return {
      currentNodeId,
      nextNodeId: null,
      reason: "conflict: multiple satisfied edges for current node",
      blocker: null,
      source,
      status: "CONFLICT",
    };
  }

  // Blocking path check — BLOCKED with explicit blocker text.
  const blocking = options?.blockingPath ?? detectBlockingFromEdges(model, currentNodeId);
  if (blocking.status === "BLOCKED") {
    return {
      currentNodeId,
      nextNodeId: null,
      reason: blocking.reason ?? "Blocked by dependency",
      blocker: blocking.reason ?? "UNKNOWN",
      source,
      status: "BLOCKED",
    };
  }

  // At final step — no next node, but resolved.
  if (nextNodeIdFromSteps === null && nextNodeIdFromEdges === null) {
    return {
      currentNodeId,
      nextNodeId: null,
      reason: "At final step",
      blocker: null,
      source,
      status: "RESOLVED",
    };
  }

  // RESOLVED — next node determined from source-backed data.
  const nextNodeId = nextNodeIdFromSteps ?? nextNodeIdFromEdges;
  return {
    currentNodeId,
    nextNodeId,
    reason: `Step ${model.currentSequence} → ${model.currentSequence + 1}`,
    blocker: null,
    source,
    status: "RESOLVED",
  };
}

/** Derive candidate next node IDs from satisfied dependency edges of the current node. */
function deriveNextFromEdges(
  model: UnifiedRunWorkspaceModel,
  currentNodeId: string | null
): string | null {
  if (!currentNodeId) return null;
  const satisfied = model.edges.filter(
    (e) => e.source === currentNodeId && e.state === "SATISFIED"
  );
  if (satisfied.length === 0) return null;
  // Return the single candidate, or null to signal a conflict (caller
  // detects via hasEdgeConflict below). We must NOT return a sentinel string
  // like "CONFLICT_MULTIPLE" as nextNodeId — that would leak into the RESOLVED
  // branch and certify a non-existent node as real (fail-closed violation).
  if (satisfied.length > 1) return null;
  return satisfied[0].target;
}

/** Whether deriveNextFromEdges saw multiple satisfied edges (conflict signal). */
function hasEdgeConflict(
  model: UnifiedRunWorkspaceModel,
  currentNodeId: string | null
): boolean {
  if (!currentNodeId) return false;
  return (
    model.edges.filter(
      (e) => e.source === currentNodeId && e.state === "SATISFIED"
    ).length > 1
  );
}

/** Detect blocking status from edges when no explicit blockingPath is provided. */
function detectBlockingFromEdges(
  model: UnifiedRunWorkspaceModel,
  currentNodeId: string | null
): BlockingPath {
  if (!currentNodeId) {
    return { runId: model.runId, status: "UNKNOWN", reason: "UNKNOWN", blockedBy: [], authorityState: "UNKNOWN" };
  }
  const blockingEdges = model.edges.filter(
    (e) => e.source === currentNodeId && e.state === "BLOCKING"
  );
  if (blockingEdges.length > 0) {
    return {
      runId: model.runId,
      status: "BLOCKED",
      reason: "UNMET_DEPENDENCY",
      blockedBy: blockingEdges.map((e) => e.target),
      authorityState: "NOT_REQUIRED",
    };
  }
  return { runId: model.runId, status: "ELIGIBLE", reason: null, blockedBy: [], authorityState: "NOT_REQUIRED" };
}