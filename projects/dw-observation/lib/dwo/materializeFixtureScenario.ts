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

// ---------------------------------------------------------------------------
// Fixture pack — DWO-UR-30-V1 evidence source
// Uses require() so the module loads in both server and client contexts.
// On the client (no fs), evidence enrichment is skipped gracefully.
// ---------------------------------------------------------------------------

type FsModule = {
  readFileSync: typeof import("fs").readFileSync;
  readdirSync: typeof import("fs").readdirSync;
};
type PathModule = { join: typeof import("path").join };

let _fs: FsModule | null = null;
let _path: PathModule | null = null;

function _ensureFs(): FsModule | null {
  if (_fs !== null) return _fs;
  try {
    _fs = require("fs") as FsModule;
    _path = require("path") as PathModule;
  } catch {
    // fs/path not available (client-side bundle)
  }
  return _fs;
}

function _join(...segments: string[]): string {
  return _path ? _path.join(...segments) : segments.join("/");
}

const FIXTURE_PACK = _join(process.cwd(), "dwo-v2/fixtures/DWO-UR-30-V1");

function loadEvents(): Array<{
  event_id: string;
  run_id: string;
  ordinal: number;
  run_state: string;
  gate: string | null;
  gate_state: string | null;
}> {
  const fs = _ensureFs();
  if (!fs) return [];
  const raw = fs.readFileSync(_join(FIXTURE_PACK, "events", "projection-events.jsonl"), "utf-8");
  return raw
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line))
    .sort((a, b) => a.ordinal - b.ordinal);
}

function evidenceFilesForRun(runId: string): string[] {
  const fs = _ensureFs();
  if (!fs) return [];
  const dirs = ["execution", "target", "verification", "closure", "handoff", "authority"];
  const files: string[] = [];
  for (const dir of dirs) {
    const dirPath = _join(FIXTURE_PACK, "evidence", dir);
    try {
      const entries = fs.readdirSync(dirPath);
      for (const entry of entries) {
        if (entry.startsWith(`${runId}-`)) {
          files.push(`${dir}/${entry}`);
        }
      }
    } catch {
      continue;
    }
  }
  return files;
}

function loadEvidenceRecords(runId: string): unknown[] {
  const files = evidenceFilesForRun(runId);
  const fs = _ensureFs();
  if (!fs) return [];
  const records: unknown[] = [];
  for (const file of files) {
    try {
      const raw = fs.readFileSync(_join(FIXTURE_PACK, "evidence", file), "utf-8");
      records.push(JSON.parse(raw));
    } catch {
      continue;
    }
  }
  return records;
}

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
  entry: (typeof FIXTURE_CATALOG)[number],
  evidenceFiles: string[] = [],
  evidenceRecords: unknown[] = []
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
    fileReads: evidenceFiles.length > 0 ? evidenceFiles : [],
    fileWrites: [],
    artifacts: evidenceFiles,
    runbook: evidenceRecords.map((r) => JSON.stringify(r)),
    taskControllerHistory: evidenceRecords,
    executorHistory: evidenceRecords,
    checkpoints: evidenceRecords,
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
    // Override: conflict models always have UNKNOWN next flow
    model.projectionStatus = "CONFLICT";
    // The model is returned as-is; the Next Flow result is UNKNOWN by virtue of
    // empty orderedSteps — verified in T09-4.

    return model;
  }

  // --- Conforming fixture: build complete workspace model ---
  const projection: FixtureProjection = resolveFixtureProjection(catalogEntry);

  // Load fixture pack evidence for this scenario
  const events = loadEvents();
  const selfEvidenceFiles = evidenceFilesForRun(catalogEntry.id);
  const selfEvidenceRecords = loadEvidenceRecords(catalogEntry.id);

  const nodes: UnifiedRuntimeNode[] = [];
  const edges: UnifiedRuntimeEdge[] = [];

  // Self node
  const selfNode = buildRuntimeNode(
    catalogEntry,
    selfEvidenceFiles,
    selfEvidenceRecords
  );
  nodes.push(selfNode);

  // Child nodes (hierarchy children) — look up from catalog
  for (const childId of catalogEntry.children) {
    const childEntry = FIXTURE_CATALOG.find((c) => c.id === childId);
    if (childEntry) {
      const childEvidenceFiles = evidenceFilesForRun(childEntry.id);
      const childEvidenceRecords = loadEvidenceRecords(childEntry.id);
      nodes.push(
        buildRuntimeNode(childEntry, childEvidenceFiles, childEvidenceRecords)
      );
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
  // Never default to SATISFIED; evidence must explicitly support it
  for (const depId of catalogEntry.deps) {
    edges.push({
      id: `dep-${catalogEntry.id}-${depId}`,
      source: depId,
      target: catalogEntry.id,
      kind: "DEPENDENCY",
      state: "UNKNOWN",
    });
  }

  // Timeline: orderedSteps from event ordinal sequence, not node array order
  const scenarioRunIds = new Set(nodes.map((n) => n.id));
  const scenarioEvents = events.filter((e) => scenarioRunIds.has(e.run_id));
  const orderedSteps = scenarioEvents.map((event, i) => ({
    nodeId: event.run_id,
    sequence: i,
  }));

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