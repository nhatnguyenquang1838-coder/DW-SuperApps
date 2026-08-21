import runScrum555 from "@/fixtures/run_scrum555_m0.json";
import projectionScrum555 from "@/fixtures/projection_scrum555_m0.json";
import runGwcDurable from "@/fixtures/run_gwc_durable_m0.json";
import projectionGwcDurable from "@/fixtures/projection_gwc_durable_m0.json";

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

function buildRunView(runId: string, b: Bundle): RunView {
  const run = b.run;
  const proj = b.projection;
  const rawEvents = asArray(run.events).map((e) => (e as Json));
  const events = rawEvents.map(normalizeEvent);
  const gates = asRecord(proj.gates);
  const nodes = asRecord(proj.nodes);
  const anomalies = asArray(proj.anomalies).map((a) => a as Json);

  // Controller/executor are NOT inferred from generic actor/source (per
  // Controller seq=7 clarification). They remain explicit UNKNOWN unless the
  // fixture carries a dedicated controller/executor field (it does not).
  const controller = UNKNOWN;
  const executor = UNKNOWN;

  return {
    runId: asString(proj.run_id, runId),
    sourceSystem: asString(run.source_system),
    startedAt: (proj.started_at as string | null) ?? null,
    lastEventAt: (proj.last_event_at as string | null) ?? null,
    lane: UNKNOWN,
    task: UNKNOWN,
    controller,
    executor,
    branch: UNKNOWN,
    pr: UNKNOWN,
    exactHead: UNKNOWN,
    ci: UNKNOWN,
    risk: UNKNOWN,
    blocker: UNKNOWN,
    now: UNKNOWN,
    next: UNKNOWN,
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
};

export function listRuns(): RunView[] {
  return Object.keys(BUNDLES).map((id) => buildRunView(id, BUNDLES[id]));
}

export function getRun(runId: string): RunView | null {
  const b = BUNDLES[runId];
  return b ? buildRunView(runId, b) : null;
}
