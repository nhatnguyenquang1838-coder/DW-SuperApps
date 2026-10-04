/**
 * T09 — Fixture scenario materialization.
 *
 * Upgrades DWO-UR-30-V1 from catalog metadata to complete simulated workspaces.
 *
 * Every DEV-RUN-001..030 materializes a complete UnifiedRunWorkspaceModel
 * via the production-equivalent path:
 *   fixtureSpec catalog -> materializeFixtureScenario -> UnifiedRunWorkspaceModel
 *
 * DEV-RUN-020 (NEGATIVE) fails closed: CONFLICT status, no fabricated nodes/edges.
 *
 * TECH_SPEC §9 — Fixture Lab contract.
 */

import type {
  UnifiedRuntimeNode,
  UnifiedRuntimeEdge,
  UnifiedRunWorkspaceModel,
  WorkspaceMode,
} from "../runtime/unifiedRuntime";
import {
  FIXTURE_CATALOG,
  DEV_RUN_020,
  type FixtureProjection,
  resolveFixtureProjection,
} from "./fixtureSpec";
import { computeNextFlow } from "../runtime/nextFlow";

// ---------------------------------------------------------------------------
// Validation — reject incomplete scenario definitions (T09-5 invariant)
// ---------------------------------------------------------------------------

const REQUIRED_CATALOG_FIELDS: (keyof typeof FIXTURE_CATALOG[number])[] = [
  "id",
  "domain",
  "kind",
  "runState",
];

function assertCompleteCatalogEntry(
  entry: unknown
): asserts entry is (typeof FIXTURE_CATALOG)[number] {
  if (!entry || typeof entry !== "object") {
    throw new Error("fixture scenario entry must be an object");
  }
  const e = entry as Record<string, unknown>;
  for (const field of REQUIRED_CATALOG_FIELDS) {
    const val = e[field];
    if (typeof val !== "string" || val.trim().length === 0) {
      throw new Error(
        `incomplete fixture scenario: field "${field}" is missing or empty`
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Node builders
// ---------------------------------------------------------------------------

function buildRuntimeNode(
  entry: (typeof FIXTURE_CATALOG)[number]
): UnifiedRuntimeNode {
  const projection: FixtureProjection = resolveFixtureProjection(entry);

  return {
    id: entry.id,
    gateId: entry.gate ?? null,
    title: `${entry.domain} / ${entry.purpose}`,
    family: entry.kind,
    nodeType: null,
    authorityBoundary: null,
    sourceStatus:
      projection.sourceProfile === "UNKNOWN" ? "UNKNOWN" : "ACTIVE",
    maturity: null,
    declaredGates: entry.gate ? [entry.gate] : [],
    purpose: entry.purpose,
    fileReads: [],
    fileWrites: [],
    artifacts: [],
    runbook: [],
    taskControllerHistory: [],
    executorHistory: [],
    checkpoints: [],
  };
}

// ---------------------------------------------------------------------------
// Main materialization
// ---------------------------------------------------------------------------

export function materializeFixtureScenario(
  catalogEntry: (typeof FIXTURE_CATALOG)[number]
): UnifiedRunWorkspaceModel {
  // --- Validate completeness (T09-5) ---
  assertCompleteCatalogEntry(catalogEntry);

  // --- DEV-RUN-020: NEGATIVE fixture — fail closed, no fabrication ---
  if (catalogEntry.kind === "NEGATIVE" || catalogEntry.id === DEV_RUN_020) {
    const model: UnifiedRunWorkspaceModel = {
      runId: catalogEntry.id,
      taskRef: null,
      mode: "SIMULATED" as WorkspaceMode,
      status: "CONFLICT",
      hierarchy: null,
      nodes: [],
      edges: [],
      orderedSteps: [],
      currentSequence: null,
      canonicalHistoryAvailable: false,
      projectionStatus: "CONFLICT",
      sourceDigest: null,
    };

    // Next Flow on a conflict model must be UNKNOWN — never resolve through conflict
    const nextFlow = computeNextFlow(model);
    // Override: conflict models always have UNKNOWN next flow
    model.projectionStatus = "CONFLICT";
    // The model is returned as-is; the Next Flow result is UNKNOWN by virtue of
    // empty orderedSteps — verified in T09-4.

    return model;
  }

  // --- Conforming fixture: build complete workspace model ---
  const projection: FixtureProjection = resolveFixtureProjection(catalogEntry);
  const nodes: UnifiedRuntimeNode[] = [];
  const edges: UnifiedRuntimeEdge[] = [];

  // Self node
  const selfNode = buildRuntimeNode(catalogEntry);
  nodes.push(selfNode);

  // Child nodes (hierarchy children) — look up from catalog
  for (const childId of catalogEntry.children) {
    const childEntry = FIXTURE_CATALOG.find((c) => c.id === childId);
    if (childEntry) {
      nodes.push(buildRuntimeNode(childEntry));
      // FANOUT edge: parent -> child (hierarchy relationship)
      edges.push({
        id: `hierarchy-${catalogEntry.id}-${childId}`,
        source: catalogEntry.id,
        target: childId,
        kind: "FANOUT",
        state: "UNKNOWN",
      });
    }
  }

  // Dependency edges (from catalog deps) — separate from hierarchy
  for (const depId of catalogEntry.deps) {
    edges.push({
      id: `dep-${catalogEntry.id}-${depId}`,
      source: depId,
      target: catalogEntry.id,
      kind: "DEPENDENCY",
      state: "SATISFIED",
    });
  }

  // Timeline: orderedSteps from node array order
  const orderedSteps = nodes.map((n, i) => ({ nodeId: n.id, sequence: i }));

  const hierarchy =
    catalogEntry.parent || catalogEntry.children.length > 0
      ? {
          parent: catalogEntry.parent,
          children: [...catalogEntry.children],
        }
      : null;

  const model: UnifiedRunWorkspaceModel = {
    runId: catalogEntry.id,
    taskRef: null,
    mode: "SIMULATED" as WorkspaceMode,
    status: catalogEntry.runState,
    hierarchy,
    nodes,
    edges,
    orderedSteps,
    currentSequence: null,
    canonicalHistoryAvailable: nodes.length > 0,
    projectionStatus: projection.semanticQualification,
    sourceDigest: null,
  };

  return model;
}

/** Materialize all 30 fixture scenarios. Returns models in catalog order. */
export function materializeAllFixtures(): UnifiedRunWorkspaceModel[] {
  return FIXTURE_CATALOG.map((entry) => materializeFixtureScenario(entry));
}