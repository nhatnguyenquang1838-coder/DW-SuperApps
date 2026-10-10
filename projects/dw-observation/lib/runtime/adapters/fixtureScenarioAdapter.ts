/**
 * Fixture scenario adapter — adapts the DWO-UR-30-V1 catalog from
 * lib/dwo/fixtureSpec.ts into the UnifiedRunWorkspaceModel.
 *
 * Pure TypeScript — no React import, no DOM access.
 * Incomplete scenarios are kept explicit — no node fabrication.
 */

import type {
  UnifiedRuntimeNode,
  UnifiedRuntimeEdge,
  UnifiedRunWorkspaceModel,
  WorkspaceMode,
} from "../unifiedRuntime";
import {
  FIXTURE_CATALOG,
  resolveFixtureProjection,
  type FixtureProjection,
} from "@/lib/dwo/fixtureSpec";

/**
 * Adapt a single DWO-UR-30-V1 catalog entry into a unified model.
 * For negative fixtures (DEV-RUN-020), the projection is INCOMPATIBLE
 * and no nodes are fabricated — the model is returned with empty nodes
 * and an explicit status.
 */
export function fixtureScenarioAdapter(
  catalogEntry: (typeof FIXTURE_CATALOG)[number],
): UnifiedRunWorkspaceModel {
  const projection: FixtureProjection = resolveFixtureProjection(catalogEntry);

  const isNegative = catalogEntry.kind === "NEGATIVE";
  const nodes: UnifiedRuntimeNode[] = [];
  const edges: UnifiedRuntimeEdge[] = [];

  if (!isNegative) {
    // Create a single representative node for this fixture run.
    // The fixture catalog does not expose per-node detail — we keep
    // the node minimal and explicit about what the catalog provides.
    nodes.push({
      id: catalogEntry.id,
      gateId: catalogEntry.gate ?? null,
      title: `${catalogEntry.domain} / ${catalogEntry.purpose}`,
      family: catalogEntry.kind,
      nodeType: null,
      authorityBoundary: null,
      sourceStatus: projection.sourceProfile === "UNKNOWN" ? "UNKNOWN" : "ACTIVE",
      maturity: null,
      declaredGates: catalogEntry.gate ? [catalogEntry.gate] : [],
      purpose: catalogEntry.purpose,
      fileReads: [],
      fileWrites: [],
      artifacts: [],
      runbook: [],
      taskControllerHistory: [],
      executorHistory: [],
      checkpoints: [],
    });
  }

  // Edges from catalog dependency references (deps are explicit recorded
  // dependencies, never inferred from hierarchy).
  for (const depId of catalogEntry.deps ?? []) {
    edges.push({
      id: `dep-${catalogEntry.id}-${depId}`,
      source: depId,
      target: catalogEntry.id,
      kind: "DEPENDENCY",
      state: "SATISFIED",
    });
  }

  // Child edges represent the hierarchy (parent/child), which is a
  // SEPARATE concept from dependency edges. We emit them as edges
  // with kind inferred from the relationship — hierarchy edges are
  // recorded as FANOUT for the parent→child relationship, keeping
  // them distinct from DEPENDENCY edges above.
  for (const childId of catalogEntry.children ?? []) {
    edges.push({
      id: `child-${catalogEntry.id}-${childId}`,
      source: catalogEntry.id,
      target: childId,
      kind: "FANOUT",
      state: "UNKNOWN",
    });
  }

  return {
    runId: catalogEntry.id,
    taskRef: null,
    mode: "SIMULATED" as WorkspaceMode,
    status: isNegative ? "INCOMPATIBLE" : projection.syncState,
    hierarchy: null,
    nodes,
    edges,
    orderedSteps: nodes.map((n, i) => ({ nodeId: n.id, sequence: i })),
    currentSequence: null,
    canonicalHistoryAvailable: false,
    projectionStatus: isNegative
      ? "INCOMPATIBLE"
      : projection.semanticQualification,
    sourceDigest: null,
  };
}
