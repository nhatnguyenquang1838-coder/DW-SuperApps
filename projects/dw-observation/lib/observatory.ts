import runScrum555 from "@/fixtures/run_scrum555_m0.json";
import projectionScrum555 from "@/fixtures/projection_scrum555_m0.json";
import runGwcDurable from "@/fixtures/run_gwc_durable_m0.json";
import projectionGwcDurable from "@/fixtures/projection_gwc_durable_m0.json";

// ---------------------------------------------------------------------------
// Read-only historical data layer for the DW Run Observatory M1 UI.
//
// Source of truth = the merged M0 projection contract fixtures
// (projects/dw-observation/fixtures/*.json). This module loads them and
// exposes typed views. It NEVER infers authority/gate state that is not
// explicitly present in the fixture; unknown/missing values stay explicit.
//
// Fixtures are imported as JSON and read through a permissive structural shape
// (Record<string, unknown>) so we never over-assert their exact schema here.
// ---------------------------------------------------------------------------

// The projection bundle is what the UI consumes; the raw run stream is kept
// only as provenance and is not deeply typed in this layer.
export type RunSummary = {
  runId: string;
  lane: string;
  startedAt: string | null;
  lastEventAt: string | null;
  eventCount: number;
  anomalyCount: number;
  gates: string[];
  nodes: string[];
};

type ProjectionLike = Record<string, unknown>;
type RunLike = Record<string, unknown>;

type FixtureBundle = {
  run: RunLike;
  projection: ProjectionLike;
};

const BUNDLES: Record<string, FixtureBundle> = {
  run_scrum555_m0: {
    run: runScrum555 as RunLike,
    projection: projectionScrum555 as ProjectionLike,
  },
  run_gwc_durable_m0: {
    run: runGwcDurable as RunLike,
    projection: projectionGwcDurable as ProjectionLike,
  },
};

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function asRecord(v: unknown): Record<string, Record<string, unknown>> {
  if (v && typeof v === "object" && !Array.isArray(v)) {
    return v as Record<string, Record<string, unknown>>;
  }
  return {};
}

function toSummary(runId: string, b: FixtureBundle): RunSummary {
  const proj = b.projection;
  const events = asArray(proj.events);
  const anomalies = asArray(proj.anomalies);
  const gates = asRecord(proj.gates);
  const nodes = asRecord(proj.nodes);
  return {
    runId,
    lane: "DW Run Observatory",
    startedAt: (proj.started_at as string | null) ?? null,
    lastEventAt: (proj.last_event_at as string | null) ?? null,
    eventCount: events.length,
    anomalyCount: anomalies.length,
    gates: Object.keys(gates),
    nodes: Object.keys(nodes),
  };
}

export function listRuns(): RunSummary[] {
  return Object.keys(BUNDLES).map((id) => toSummary(id, BUNDLES[id]));
}

export function getRun(runId: string): FixtureBundle | null {
  return BUNDLES[runId] ?? null;
}

// Explicit "unknown" sentinel so the UI never fakes a value.
export const UNKNOWN = "—";
