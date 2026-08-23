import runScrum555 from "@/fixtures/run_scrum555_m0.json";
import projectionScrum555 from "@/fixtures/projection_scrum555_m0.json";
import runGwcDurable from "@/fixtures/run_gwc_durable_m0.json";
import projectionGwcDurable from "@/fixtures/projection_gwc_durable_m0.json";
import runScrum555M5Mock from "@/fixtures/run_scrum555_m5_mock.json";
import projectionScrum555M5Mock from "@/fixtures/projection_scrum555_m5_mock.json";

// ---------------------------------------------------------------------------
// Read-only historical data layer for the DW Run Observatory M1 UI.
//
// Source of truth = the merged M0 projection contract fixtures
// (projects/dw-observation/fixtures/*.json). This module loads them and
// exposes typed, source-backed views. It NEVER infers authority/gate state
// that is not explicitly present in a fixture; unknown/missing values stay
// explicit (rendered as UNKNOWN in the UI).
//
// Fixture topology (verified against the merged M0 fixtures):
//   <id>.run    -> carries the real event stream (before/after, event_id,
//                  evidence_refs, authority_ref, actor, source) — two different
//                  schemas (taskcontroller vs gwc) are normalized below.
//   <id>.projection -> carries run_id/started_at/last_event_at/gates/nodes/
//                  anomalies (events: [] there; events come from the run stream).
// Both share run_id per pair, so they are merged by run_id.
// ---------------------------------------------------------------------------

export const UNKNOWN = "—";

// M5 — explicit data-source flag so the mock-reviewed run can carry source-backed
// M0-M4 metadata (lane/task/controller/executor/branch/PR/HEAD/CI/...) WITHOUT
// corrupting the real fixtures, which remain genuinely UNKNOWN.
export type DataSource = "real" | "mock";

type Json = Record<string, unknown>;

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}
function asRecord(v: unknown): Record<string, Json> {
  if (v && typeof v === "object" && !Array.isArray(v)) {
    return v as Record<string, Json>;
  }
  return {};
}
function asString(v: unknown, fallback = UNKNOWN): string {
  return typeof v === "string" && v.length > 0 ? v : fallback;
}

// Normalized event: every field that is absent in a fixture is UNKNOWN.
export type NormalizedEvent = {
  sourceEventId: string;
  seq: number | null;
  occurredAt: string;
  eventType: string;
  source: string;
  actor: string;
  gate: string;
  nodeId: string;
  before: Json;
  after: Json;
  evidenceRefs: string[];
  authorityRef: string;
  sourceDigest: string; // not present in fixtures -> UNKNOWN (no invention)
  annotations: Json;
};

function normalizeEvent(raw: Json): NormalizedEvent {
  // taskcontroller schema
  const eventId = asString(raw.event_id, asString(raw.source_event_id));
  const occurred =
    asString(raw.timestamp, asString(raw.occurred_at_utc)) !== UNKNOWN
      ? asString(raw.timestamp, asString(raw.occurred_at_utc))
      : UNKNOWN;
  const actorRaw = raw.actor;
  let actor = UNKNOWN;
  if (typeof actorRaw === "string") actor = actorRaw;
  else if (actorRaw && typeof actorRaw === "object") {
    const a = actorRaw as Json;
    actor = [asString(a.kind), asString(a.id)]
      .filter((s) => s !== UNKNOWN)
      .join(":")
      .replace(/:$/, "") || UNKNOWN;
  }
  return {
    sourceEventId: eventId,
    seq: typeof raw.sequence === "number" ? (raw.sequence as number) : null,
    occurredAt: occurred,
    eventType: asString(raw.event_type, asString(raw.decision_kind)),
    source: asString(raw.source),
    actor,
    gate: asString(raw.gate),
    nodeId: asString(raw.node_id),
    before: (raw.before as Json) ?? {},
    // G3 seq=8: `after` uses ONLY an explicit `after` field. GWC `payload` is a
    // distinct source field and must NOT be silently mapped into `after` (that
    // would fabricate an after-state for GWC DurableEvent records). When absent,
    // `after` is empty — never payload.
    after: (raw.after as Json) ?? {},
    evidenceRefs: asArray(raw.evidence_refs)
      .map((r) => (typeof r === "string" ? r : JSON.stringify(r)))
      .filter((r) => r.length > 0),
    authorityRef: asString(raw.authority_ref),
    sourceDigest: UNKNOWN, // not present in any fixture -> explicit unknown
    annotations: (raw.annotations as Json) ?? {},
  };
}

export type RunView = {
  runId: string;
  sourceSystem: string;
  startedAt: string | null;
  lastEventAt: string | null;
  lane: string; // UNKNOWN unless present
  task: string; // UNKNOWN unless present
  controller: string; // UNKNOWN unless present
  executor: string; // UNKNOWN unless present
  branch: string; // UNKNOWN unless present
  pr: string; // UNKNOWN unless present
  exactHead: string; // UNKNOWN unless present
  ci: string; // UNKNOWN unless present
  risk: string; // UNKNOWN unless present
  blocker: string; // UNKNOWN unless present
  now: string; // UNKNOWN unless present
  next: string; // UNKNOWN unless present
  eventCount: number;
  anomalyCount: number;
  events: NormalizedEvent[];
  gates: Record<string, Json>;
  nodes: Record<string, Json>;
  anomalies: Array<Json>;
};

type Bundle = { run: Json; projection: Json };

// M5 — explicit, source-backed M0-M4 metadata for the deterministic mock review
// run. This is the ONLY place mock values live; real fixtures remain genuinely
// UNKNOWN. Approved values are taken from the Controller's correction (seq=2):
// lane DW Run Observatory, task SCRUM-555, controller ChatGPT TaskController,
// executor Hermes Mac, branch auto/SCRUM-555-dw-observation-m3m4-r1, PR #79,
// exactHead 5e59c889039968f606d52906c5433a21a4751bd9, CI Validate workspace
// #32589399526 = SUCCESS, now "terminal complete / M5 local review", next
// "human review mock UI + Supabase migration proposal".
type MockMeta = {
  lane: string;
  task: string;
  controller: string;
  executor: string;
  branch: string;
  pr: string;
  exactHead: string;
  ci: string;
  risk: string;
  blocker: string;
  now: string;
  next: string;
};

const MOCK_RUN_ID = "DW-OBS-M5-20260823-MOCK";
const MOCK_META: MockMeta = {
  lane: "DW Run Observatory",
  task: "SCRUM-555",
  controller: "ChatGPT TaskController",
  executor: "Hermes Mac",
  branch: "auto/SCRUM-555-dw-observation-m3m4-r1",
  pr: "#79",
  exactHead: "5e59c889039968f606d52906c5433a21a4751bd9",
  ci: "Validate workspace #32589399526 = SUCCESS",
  risk: "none (local review / explicit demo anomaly only)",
  blocker: "none",
  now: "terminal complete / M5 local review",
  next: "human review mock UI + Supabase migration proposal",
};

// Explicit DAG edges for the mock run (NOT inferred). Only recorded relationships
// are shown; the DAG shape is consumed from here, never invented from node ids.
export const DAG_EDGES: Record<string, Array<{ from: string; to: string; label: string }>> = {
  [MOCK_RUN_ID]: [
    { from: "node:70", to: "node:71", label: "parent -> M0" },
    { from: "node:71", to: "node:72", label: "M0 -> M1" },
    { from: "node:72", to: "node:73", label: "M1 -> M2" },
    { from: "node:73", to: "node:74", label: "M2 -> M3" },
    { from: "node:74", to: "node:75", label: "M3 -> M4" },
    { from: "gate:G2-DW-OBS-M3M4-20260823-R1", to: "node:71", label: "G2 approves M0" },
    { from: "gate:G3", to: "node:74", label: "G3 reviews M3" },
    { from: "gate:G4-DW-OBS-M3M4-20260823-R1", to: "node:74", label: "G4 consumes M3" },
  ],
};

function buildRunView(runId: string, b: Bundle, dataSource: DataSource = "real"): RunView {
  const run = b.run;
  const proj = b.projection;
  const rawEvents = asArray(run.events).map((e) => (e as Json));
  const events = rawEvents.map(normalizeEvent);
  const gates = asRecord(proj.gates);
  const nodes = asRecord(proj.nodes);
  const anomalies = asArray(proj.anomalies).map((a) => a as Json);

  // Controller/executor are NOT inferred from generic actor/source (per
  // Controller seq=7 clarification). They remain explicit UNKNOWN in real
  // fixtures. In mock mode the approved M0-M4 metadata is applied explicitly.
  const controller = dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.controller : UNKNOWN;
  const executor = dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.executor : UNKNOWN;

  return {
    runId: asString(proj.run_id, runId),
    sourceSystem: asString(run.source_system),
    startedAt: (proj.started_at as string | null) ?? null,
    lastEventAt: (proj.last_event_at as string | null) ?? null,
    lane: dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.lane : UNKNOWN,
    task: dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.task : UNKNOWN,
    controller,
    executor,
    branch: dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.branch : UNKNOWN,
    pr: dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.pr : UNKNOWN,
    exactHead: dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.exactHead : UNKNOWN,
    ci: dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.ci : UNKNOWN,
    risk: dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.risk : UNKNOWN,
    blocker: dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.blocker : UNKNOWN,
    now: dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.now : UNKNOWN,
    next: dataSource === "mock" && runId === MOCK_RUN_ID ? MOCK_META.next : UNKNOWN,
    eventCount: events.length,
    anomalyCount: anomalies.length,
    events,
    gates,
    nodes,
    anomalies,
  };
}

// Keyed by run_id (shared by run + projection pairs).
const BUNDLES: Record<string, Bundle> = {
  "DW-OBS-M0-20260821-R2": {
    run: runScrum555 as Json,
    projection: projectionScrum555 as Json,
  },
  "run_dw_obs_m0_r2": {
    run: runGwcDurable as Json,
    projection: projectionGwcDurable as Json,
  },
  [MOCK_RUN_ID]: {
    run: runScrum555M5Mock as Json,
    projection: projectionScrum555M5Mock as Json,
  },
};

export function listRuns(dataSource: DataSource = "real"): RunView[] {
  return Object.keys(BUNDLES).map((id) => buildRunView(id, BUNDLES[id], dataSource));
}

export function getRun(runId: string, dataSource: DataSource = "real"): RunView | null {
  const b = BUNDLES[runId];
  return b ? buildRunView(runId, b, dataSource) : null;
}

// ---------------------------------------------------------------------------
// M5 — animated hierarchical run flow (source-backed, not hardcoded layout).
// A RunHierarchy is derived from the run's recorded gates/nodes and the
// explicit MOCK hierarchy descriptor. All card content is sourced from the
// fixtures; the layout/order lives in one place so the UI never invents it.
// ---------------------------------------------------------------------------

export type HierarchyNodeKind = "root" | "gate" | "node" | "issue";

export type HierarchyNode = {
  id: string; // "#70", "G2-...", "#80", etc. (display + connector key)
  kind: HierarchyNodeKind;
  label: string; // human label
  status: string; // recorded status (or UNKNOWN)
  detail?: string; // optional sub-line (e.g. which gate approves)
  // source-backed evidence that this node exists in the data (true = recorded)
  sourceBacked: boolean;
};

export type RunHierarchy = {
  rootId: string;
  chain: string[]; // ordered display ids: root, #71..#75, #80
  gateIds: string[]; // ["G2...", "G3", "G4..."]
  // ordered flat list (root -> gates interleaved -> chain -> #80) for rendering
  nodes: HierarchyNode[];
  // explicit connectors (recorded relationships, NOT inferred)
  connectors: Array<{ from: string; to: string; label: string }>;
};

export const SUPABASE_READINESS = {
  project: "dw-observatory",
  status: "ACTIVE_HEALTHY",
  readiness: "NO_MIGRATION_READY",
  publicTables: 0,
  migrations: 0,
  remoteApplyPerformed: false,
} as const;

// Explicit, source-backed mock hierarchy. The Controller (seq=3) requires the
// chain #70 -> #71 -> #72 -> #73 -> #74 -> #75 -> #80 with gates G2/G3/G4 as a
// visible hierarchy. Card content is sourced from the mock fixture; this
// descriptor only defines the ORDER and CONNECTORS (which are recorded, not
// inferred).
const MOCK_HIERARCHY: Omit<RunHierarchy, "nodes"> = {
  rootId: "#70",
  chain: ["#70", "#71", "#72", "#73", "#74", "#75", "#80"],
  gateIds: ["G2-DW-OBS-M3M4-20260823-R1", "G3", "G4-DW-OBS-M3M4-20260823-R1"],
  connectors: [
    { from: "#70", to: "#71", label: "parent -> M0" },
    { from: "#71", to: "#72", label: "M0 -> M1" },
    { from: "#72", to: "#73", label: "M1 -> M2" },
    { from: "#73", to: "#74", label: "M2 -> M3" },
    { from: "#74", to: "#75", label: "M3 -> M4" },
    { from: "#75", to: "#80", label: "M4 -> review issue" },
    { from: "G2-DW-OBS-M3M4-20260823-R1", to: "#71", label: "G2 approves M0" },
    { from: "G3", to: "#74", label: "G3 reviews M3" },
    { from: "G4-DW-OBS-M3M4-20260823-R1", to: "#74", label: "G4 consumes M3" },
  ],
};

const MOCK_NODE_LABELS: Record<string, string> = {
  "#70": "Parent SCRUM-555",
  "#71": "M0",
  "#72": "M1",
  "#73": "M2",
  "#74": "M3",
  "#75": "M4",
  "#80": "M5 review issue",
};

function statusOf(map: Record<string, Json>, id: string, prefix: string): string {
  const entry = map[id];
  if (!entry) return UNKNOWN;
  const e = entry as Json;
  const s = (e.status as string) ?? (e.node as string);
  return typeof s === "string" ? s : UNKNOWN;
}

export function buildHierarchy(run: RunView, dataSource: DataSource = "real"): RunHierarchy {
  if (dataSource === "mock" && run.runId === MOCK_RUN_ID) {
    const nodes: HierarchyNode[] = MOCK_HIERARCHY.chain.map((id) => ({
      id,
      kind: id === "#70" ? "root" : id === "#80" ? "issue" : "node",
      label: MOCK_NODE_LABELS[id] ?? id,
      status: id === "#80" ? "correction_required (active)" : statusOf(run.nodes, id.replace("#", ""), "node"),
      sourceBacked: true,
    }));
    const gateNodes: HierarchyNode[] = MOCK_HIERARCHY.gateIds.map((g) => ({
      id: g,
      kind: "gate",
      label: g.startsWith("G2") ? "G2" : g === "G3" ? "G3" : "G4",
      status: statusOf(run.gates, g, "gate"),
      detail:
        g.startsWith("G2")
          ? "lane approval"
          : g === "G3"
          ? "independent review"
          : "consumed/merged",
      sourceBacked: true,
    }));
    // Render order: root -> G2 -> chain nodes -> G3/G4 gates (interleaved as
    // recorded). Keep a stable, readable vertical sequence.
    const ordered: HierarchyNode[] = [
      nodes[0], // #70 root
      gateNodes[0], // G2
      nodes[1], // #71
      nodes[2], // #72
      nodes[3], // #73
      nodes[4], // #74
      gateNodes[1], // G3
      gateNodes[2], // G4
      nodes[5], // #75
      nodes[6], // #80
    ];
    return { ...MOCK_HIERARCHY, nodes: ordered };
  }

  // Real fixtures: build a best-effort hierarchy from recorded gates/nodes,
  // never inventing connectors. If there is no recorded structure, return an
  // empty-but-valid hierarchy (the UI shows "no recorded hierarchy").
  const nodeIds = Object.keys(run.nodes);
  const chain = nodeIds.length ? nodeIds.map((n) => `#${n}`) : [];
  const gateIds = Object.keys(run.gates);
  const nodes: HierarchyNode[] = [
    ...chain.map((id) => ({
      id,
      kind: "node" as HierarchyNodeKind,
      label: id,
      status: statusOf(run.nodes, id.replace("#", ""), "node"),
      sourceBacked: true,
    })),
    ...gateIds.map((g) => ({
      id: g,
      kind: "gate" as HierarchyNodeKind,
      label: g,
      status: statusOf(run.gates, g, "gate"),
      sourceBacked: true,
    })),
  ];
  return { rootId: chain[0] ?? UNKNOWN, chain, gateIds, nodes, connectors: [] };
}
