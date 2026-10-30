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
import { reduceEventPrefix, type ReducerEvent } from "./reducer";
import type { AuthorityState } from "./authorityVocabulary";
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

type FixtureEventRow = {
  event_id: string; run_id: string; ordinal: number; run_state: string;
  gate: string | null; gate_state: string | null; source_profile: string;
  sync_state: string; semantic_qualification: string; authority_state: FixtureAuthorityState;
  anomaly_count: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const AUTHORITY_STATES = ["PENDING", "GRANTED", "DENIED", "EXPIRED", "REVOKED", "NOT_REQUIRED", "UNKNOWN", "NOT_APPLICABLE"] as const;
type FixtureAuthorityState = AuthorityState | "NOT_APPLICABLE";
function isAuthorityState(value: unknown): value is FixtureAuthorityState {
  return typeof value === "string" && AUTHORITY_STATES.some((state) => state === value);
}

function parseFixtureEvent(value: unknown): FixtureEventRow {
  if (!isRecord(value) || typeof value.event_id !== "string" || !value.event_id.trim() ||
      typeof value.run_id !== "string" || !value.run_id.trim() ||
      typeof value.ordinal !== "number" || !Number.isSafeInteger(value.ordinal) || value.ordinal < 0 ||
      typeof value.run_state !== "string" ||
      !(value.gate === null || typeof value.gate === "string") ||
      !(value.gate_state === null || typeof value.gate_state === "string") ||
      typeof value.source_profile !== "string" || typeof value.sync_state !== "string" ||
      typeof value.semantic_qualification !== "string" ||
      !isAuthorityState(value.authority_state) ||
      typeof value.anomaly_count !== "number" || !Number.isSafeInteger(value.anomaly_count) || value.anomaly_count < 0) {
    throw new Error("invalid fixture projection event schema");
  }
  return {
    event_id: value.event_id, run_id: value.run_id, ordinal: value.ordinal,
    run_state: value.run_state, gate: value.gate, gate_state: value.gate_state,
    source_profile: value.source_profile, sync_state: value.sync_state,
    semantic_qualification: value.semantic_qualification,
    authority_state: value.authority_state,
    anomaly_count: value.anomaly_count,
  };
}

function loadEvents(): FixtureEventRow[] {
  const fs = _ensureFs();
  if (!fs) return [];
  const raw = fs.readFileSync(_join(FIXTURE_PACK, "events", "projection-events.jsonl"), "utf-8");
  return raw.split("\n").map((line) => line.trim()).filter(Boolean)
    .map((line) => parseFixtureEvent(JSON.parse(line)))
    .sort((a, b) => a.ordinal - b.ordinal);
}

function validateEvents(events: readonly FixtureEventRow[]): void {
  const ids = new Set<string>();
  const ordinals = new Set<string>();
  const runIds = new Set(FIXTURE_CATALOG.map((entry) => entry.id));
  for (const event of events) {
    if (!runIds.has(event.run_id)) throw new Error(`unknown fixture event run ${event.run_id}`);
    if (ids.has(event.event_id)) throw new Error(`duplicate fixture event id ${event.event_id}`);
    ids.add(event.event_id);
    const key = `${event.run_id}:${event.ordinal}`;
    if (ordinals.has(key)) throw new Error(`duplicate fixture event ordinal ${key}`);
    ordinals.add(key);
  }
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

/**
 * Reverse index: root run id -> task ref, derived from the materialized
 * TaskRunIndexV2 relation records (tasks/task-relations.jsonl).
 *
 * Deterministic and fail-closed: a run that no relation record claims gets NO
 * taskRef (null) — the model never infers a Task from a run id.
 */
function loadTaskRefByRootRun(): Map<string, string> {
  const fs = _ensureFs();
  if (!fs) return new Map();
  const map = new Map<string, string>();
  let raw: string;
  try {
    raw = fs.readFileSync(_join(FIXTURE_PACK, "tasks", "task-relations.jsonl"), "utf-8");
  } catch {
    return map;
  }
  const records: Array<{ taskRef?: unknown; rootRunIds?: unknown }> = [];
  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      records.push(JSON.parse(trimmed));
    } catch {
      continue; // malformed line: skip, never guess
    }
  }
  // Later durable positions supersede earlier ones for the same run.
  records.sort((a, b) => {
    const ap = (a as Record<string, unknown>).durablePosition;
    const bp = (b as Record<string, unknown>).durablePosition;
    const an = typeof ap === "number" ? ap : 0;
    const bn = typeof bp === "number" ? bp : 0;
    return an - bn;
  });
  for (const rec of records) {
    const taskRef = rec.taskRef;
    const rootRunIds = rec.rootRunIds;
    if (typeof taskRef !== "string" || taskRef.length === 0) continue;
    if (!Array.isArray(rootRunIds)) continue;
    for (const runId of rootRunIds) {
      if (typeof runId === "string" && runId.length > 0) map.set(runId, taskRef);
    }
  }
  return map;
}

let _taskRefCache: Map<string, string> | null = null;

function taskRefByRootRun(): Map<string, string> {
  if (_taskRefCache === null) _taskRefCache = loadTaskRefByRootRun();
  return _taskRefCache;
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
    gateState: null,
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

function collectDescendants(rootId: string): Array<typeof FIXTURE_CATALOG[number]> {
  const byId = new Map(FIXTURE_CATALOG.map((entry) => [entry.id, entry]));
  const seen = new Set([rootId]);
  const result: Array<typeof FIXTURE_CATALOG[number]> = [];
  const visit = (id: string) => {
    const entry = byId.get(id);
    if (!entry) throw new Error(`fixture hierarchy references missing run ${id}`);
    for (const childId of entry.children) {
      if (seen.has(childId)) throw new Error(`fixture hierarchy cycle or duplicate reference at ${childId}`);
      const child = byId.get(childId);
      if (!child) throw new Error(`fixture hierarchy references missing run ${childId}`);
      if (child.parent !== id) throw new Error(`fixture hierarchy parent/child mismatch ${id}->${childId}`);
      seen.add(childId);
      result.push(child);
      visit(childId);
    }
  };
  visit(rootId);
  return result;
}

function buildCatalogTree(entry: (typeof FIXTURE_CATALOG)[number], seen = new Set<string>()): { id: string; parent: string | null; atomic: boolean; children: ReturnType<typeof buildCatalogTree>[] } {
  if (seen.has(entry.id)) throw new Error(`fixture hierarchy cycle at ${entry.id}`);
  seen.add(entry.id);
  return {
    id: entry.id,
    parent: entry.parent,
    atomic: entry.kind === "ATOMIC",
    children: entry.children.map((id) => {
      const child = FIXTURE_CATALOG.find((candidate) => candidate.id === id);
      if (!child) throw new Error(`fixture hierarchy references missing run ${id}`);
      if (child.parent !== entry.id) throw new Error(`fixture hierarchy parent/child mismatch ${entry.id}->${id}`);
      return buildCatalogTree(child, new Set(seen));
    }),
  };
}

// ---------------------------------------------------------------------------
// Main materialization
// ---------------------------------------------------------------------------

export function materializeFixtureScenario(
  catalogEntry: (typeof FIXTURE_CATALOG)[number],
  options: { events?: readonly FixtureEventRow[] } = {},
): UnifiedRunWorkspaceModel {
  // --- Validate completeness (T09-5) ---
  assertCompleteCatalogEntry(catalogEntry);

  // --- DEV-RUN-020: NEGATIVE fixture — fail closed, no fabrication ---
  if (catalogEntry.id === DEV_RUN_020 || catalogEntry.runState === "INCOMPATIBLE") {
    const model: UnifiedRunWorkspaceModel = {
      runId: catalogEntry.id,
      // Task membership is a relation-record fact, independent of whether the
      // run's projection is readable. Keeping it here prevents the Task-first
      // surface (/dev/tasks/[taskId]/runs) and the run model from disagreeing.
      // The PROJECTION still fails closed: no nodes, edges, steps, or history.
      taskRef: taskRefByRootRun().get(catalogEntry.id) ?? null,
      mode: "SIMULATED" as WorkspaceMode,
      status: "INCOMPATIBLE",
      hierarchy: null,
      nodes: [],
      edges: [],
      orderedSteps: [],
      currentSequence: null,
      canonicalHistoryAvailable: false,
      projectionStatus: "INCOMPATIBLE",
      sourceDigest: null,
    };

    // Next Flow on a conflict model must be UNKNOWN — never resolve through conflict
    // Override: conflict models always have UNKNOWN next flow
    model.projectionStatus = "INCOMPATIBLE";
    // The model is returned as-is; the Next Flow result is UNKNOWN by virtue of
    // empty orderedSteps — verified in T09-4.

    return model;
  }


  // Load fixture pack evidence for this scenario
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

  // Complete descendant tree; parent links define the precise FANOUT edges.
  for (const childEntry of collectDescendants(catalogEntry.id)) {
    const childId = childEntry.id;
    const childEvidenceFiles = evidenceFilesForRun(childId);
    const childEvidenceRecords = loadEvidenceRecords(childId);
    nodes.push(buildRuntimeNode(childEntry, childEvidenceFiles, childEvidenceRecords));
    const parentId = childEntry.parent;
    if (!parentId) throw new Error(`fixture descendant ${childId} has no parent`);
    edges.push({
      id: `hierarchy-${parentId}-${childId}`,
      source: parentId,
      target: childId,
      kind: "FANOUT",
      state: "UNKNOWN",
    });
  }

  // Dependency edges (from catalog deps) — separate from hierarchy
  // Never default to SATISFIED; evidence must explicitly support it
  for (const entry of [catalogEntry, ...collectDescendants(catalogEntry.id)]) {
    for (const depId of entry.deps) {
      edges.push({
        id: `dep-${entry.id}-${depId}`,
        source: depId,
        target: entry.id,
        kind: "DEPENDENCY",
        state: "UNKNOWN",
      });
    }
  }

  const events = (options.events ? options.events.map(parseFixtureEvent) : loadEvents()).sort((a, b) => a.ordinal - b.ordinal);
  validateEvents(events);
  const byRun = (runId: string) => events.filter((event) => event.run_id === runId);
  const toReducerEvent = (event: FixtureEventRow): ReducerEvent => ({
    eventId: event.event_id,
    runId: event.run_id,
    ordinal: event.ordinal,
    gate: event.gate,
    // Legacy gate terminal values are not reducer gate states. Preserve the
    // source terminal marker separately rather than dropping or coercing it.
    gateState: event.gate_state === "CANCELLED" || event.gate_state === "SUPERSEDED" ? null : event.gate_state,
    runState: event.run_state,
    sourceProfile: event.source_profile,
    syncState: event.sync_state,
    semanticQualification: event.semantic_qualification,
    authorityState: event.authority_state,
    anomalyCount: event.anomaly_count,
  });
  const reduced = reduceEventPrefix(catalogEntry.id, byRun(catalogEntry.id).map(toReducerEvent));
  const sourceTerminalMarker = byRun(catalogEntry.id).map((event) => event.gate_state)
    .find((state): state is "CANCELLED" | "SUPERSEDED" => state === "CANCELLED" || state === "SUPERSEDED") ?? null;
  const nodeFacts = new Map(nodes.map((node) => [node.id, reduceEventPrefix(node.id, byRun(node.id).map(toReducerEvent))]));
  for (const node of nodes) {
    const facts = nodeFacts.get(node.id);
    node.gateId = facts?.gate ?? null;
    node.gateState = facts?.gateState ?? null;
    node.sourceStatus = facts?.sourceProfile && facts.sourceProfile !== "UNKNOWN" ? "ACTIVE" : "UNKNOWN";
  }
  const scenarioRunIds = new Set(nodes.map((n) => n.id));
  const scenarioEvents = events.filter((e) => scenarioRunIds.has(e.run_id));
  const orderedSteps = scenarioEvents.map((event, i) => ({ nodeId: event.run_id, sequence: i }));

  let treeRoot = catalogEntry;
  const ancestors = new Set<string>();
  while (treeRoot.parent) {
    if (ancestors.has(treeRoot.id)) throw new Error(`fixture hierarchy ancestor cycle at ${treeRoot.id}`);
    ancestors.add(treeRoot.id);
    if (treeRoot === catalogEntry && treeRoot.parent) {
      const overrideParent = treeRoot.parent;
      if (overrideParent === treeRoot.id) throw new Error(`fixture hierarchy ancestor cycle at ${treeRoot.id}`);
    }
    const parent = FIXTURE_CATALOG.find((entry) => entry.id === treeRoot.parent);
    if (!parent) throw new Error(`fixture hierarchy references missing parent ${treeRoot.parent}`);
    if (ancestors.has(parent.id)) throw new Error(`fixture hierarchy ancestor cycle at ${parent.id}`);
    if (!parent.children.includes(treeRoot.id)) throw new Error(`fixture hierarchy parent/child mismatch ${parent.id}->${treeRoot.id}`);
    treeRoot = parent;
  }
  const hierarchy = catalogEntry.parent || catalogEntry.children.length > 0 ? buildCatalogTree(treeRoot) : null;

  const model: UnifiedRunWorkspaceModel = {
    runId: catalogEntry.id,
    taskRef: taskRefByRootRun().get(catalogEntry.id) ?? null,
    mode: "SIMULATED" as WorkspaceMode,
    status: reduced.runState,
    gate: reduced.gate,
    gateState: reduced.gateState,
    sourceTerminalMarker,
    sourceProfile: reduced.sourceProfile,
    syncState: reduced.syncState,
    semanticQualification: reduced.semanticQualification,
    authorityState: reduced.authorityState,
    anomalyCount: reduced.anomalyCount,
    hierarchy,
    nodes,
    edges,
    orderedSteps,
    currentSequence: null,
    canonicalHistoryAvailable: scenarioEvents.length > 0,
    projectionStatus: scenarioEvents.length > 0 ? reduced.semanticQualification : "UNKNOWN",
    sourceDigest: null,
  };

  return model;
}

/** Materialize all 30 fixture scenarios. Returns models in catalog order. */
export function materializeAllFixtures(): UnifiedRunWorkspaceModel[] {
  return FIXTURE_CATALOG.map((entry) => materializeFixtureScenario(entry));
}