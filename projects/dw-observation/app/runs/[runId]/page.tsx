// Server Component (Next.js App Router) — M2 run detail.
//
// REAL mode: reads exact stored `runs`, `run_gates`, `run_nodes` and
// `projection_events` through the publishable/RLS-compatible server path
// (lib/serverRunRead.readServerRunDetail). NO fixture fallback for run
// metadata/gates/nodes: absent fields stay UNKNOWN; a reconstructed historical
// run with zero canonical projection_events reports
// canonicalHistoryAvailable=false / PROJECTION_UNAVAILABLE.
//
// MOCK mode (OBSERVATORY_DATA_SOURCE=mock): deterministic fixture-backed
// review path — unchanged.

import { notFound } from "next/navigation";
import type { ProjectionEvent } from "@/lib/live";
import {
  getRun,
  UNKNOWN,
  DAG_EDGES,
  buildHierarchy,
  SUPABASE_READINESS,
} from "@/lib/observatory";
import type { NormalizedEvent, RunView } from "@/lib/observatory";

type Json = Record<string, unknown>;
import { readServerRunDetail } from "@/lib/serverRunRead";
import type { ServerRunDetailResult } from "@/lib/serverRunRead";
import { getMockProjectionEvents, MOCK_BACKEND } from "@/lib/mockDataSource";
import RootCard from "@/components/RootCard";
import DagView from "@/components/DagView";
import Timeline from "@/components/Timeline";
import EvidenceInspector from "@/components/EvidenceInspector";
import LiveProjectionPane from "@/components/LiveProjectionPane";
import ReplayPane from "@/components/ReplayPane";
import ReviewPane from "@/components/ReviewPane";
import RunGraphView from "@/components/RunGraphView";

// Normalize actor for real-mode events the same way observatory normalizes
// fixture actors: preserve string values; for deterministic JSON objects with
// kind/id, normalize to `kind:id` rather than dropping to UNKNOWN.
function normalizeActor(raw: unknown): string {
  if (typeof raw === "string") return raw;
  if (raw && typeof raw === "object") {
    const a = raw as Record<string, unknown>;
    const kind = typeof a.kind === "string" ? a.kind : undefined;
    const id = typeof a.id === "string" ? a.id : undefined;
    const parts = [kind, id].filter((s) => s !== undefined && s !== "");
    const joined = parts.join(":").replace(/:$/, "");
    return joined.length > 0 ? joined : UNKNOWN;
  }
  return UNKNOWN;
}

// Map a canonical ProjectionEvent to the observatory NormalizedEvent shape
// using EXACT stored values only; absent fields stay UNKNOWN (never fabricated).
function projectionToNormalized(e: ProjectionEvent): NormalizedEvent {
  return {
    sourceEventId: e.source_event_id,
    seq: typeof e.sequence === "number" ? e.sequence : null,
    occurredAt:
      typeof e.occurred_at === "string" ? (e.occurred_at as string) : UNKNOWN,
    eventType:
      typeof e.event_type === "string" ? (e.event_type as string) : UNKNOWN,
    source: e.source_system,
    actor: normalizeActor(e.actor),
    gate: typeof e.gate === "string" ? (e.gate as string) : UNKNOWN,
    nodeId: typeof e.node_id === "string" ? (e.node_id as string) : UNKNOWN,
    before: (e.before as Json) ?? {},
    after: (e.after as Json) ?? {},
    evidenceRefs: Array.isArray(e.evidence_refs)
      ? (e.evidence_refs as string[])
      : [],
    authorityRef:
      typeof e.authority_ref === "string" ? (e.authority_ref as string) : UNKNOWN,
    sourceDigest:
      typeof e.source_digest === "string" ? (e.source_digest as string) : UNKNOWN,
    annotations: {},
  };
}

// Build a RunView from the exact stored serverRunRead detail rows. Absent
// fields (lane/task/branch/...) stay UNKNOWN — never filled from fixtures.
function runViewFromDetail(
  runId: string,
  detail: ServerRunDetailResult,
): RunView {
  const run = detail.run ?? {};
  const gates: Record<string, Json> = {};
  for (const g of detail.gates) {
    if (typeof g.gate_id === "string") gates[g.gate_id as string] = g as Json;
  }
  const nodes: Record<string, Json> = {};
  for (const n of detail.nodes) {
    if (typeof n.node_id === "string") nodes[n.node_id as string] = n as Json;
  }
  const events = detail.events.map(projectionToNormalized);
  return {
    runId,
    sourceSystem:
      typeof run.source_system === "string"
        ? (run.source_system as string)
        : UNKNOWN,
    startedAt: typeof run.started_at === "string" ? (run.started_at as string) : null,
    lastEventAt: null,
    lane: UNKNOWN,
    task: UNKNOWN,
    controller: UNKNOWN,
    executor: UNKNOWN,
    branch:
      typeof run.branch === "string"
        ? (run.branch as string)
        : UNKNOWN,
    pr:
      typeof run.pr_number === "number" || typeof run.pr_number === "string"
        ? String(run.pr_number)
        : UNKNOWN,
    exactHead:
      typeof run.head_sha === "string"
        ? (run.head_sha as string)
        : UNKNOWN,
    ci:
      typeof run.ci_status === "string"
        ? (run.ci_status as string)
        : UNKNOWN,
    risk: UNKNOWN,
    blocker: UNKNOWN,
    now: UNKNOWN,
    next: UNKNOWN,
    eventCount: events.length,
    anomalyCount: 0,
    events,
    gates,
    nodes,
    anomalies: [],
  };
}

export default async function RunDetailPage({
  params,
}: {
  params: { runId: string };
}) {
  // M5 — explicit data-source switch (OBSERVATORY_DATA_SOURCE=mock|real).
  const dataSource =
    process.env.OBSERVATORY_DATA_SOURCE === "mock" ? "mock" : "real";

  // ---------------- mock mode (unchanged) ----------------
  if (dataSource === "mock") {
    const run = getRun(params.runId, "mock");
    if (!run) notFound();
    const hierarchy = buildHierarchy(run, "mock");
    const activeId =
      run.runId === "DW-OBS-M5-20260823-MOCK" ? "#80" : undefined;
    const historicalEvents = getMockProjectionEvents(params.runId);
    return (
      <section className="space-y-6">
        <RootCard run={run} unknownSentinel={UNKNOWN} supabaseReadiness={SUPABASE_READINESS} />
        <RunGraphView hierarchy={hierarchy} activeId={activeId} />
        <DagView gates={run.gates} nodes={run.nodes} edges={DAG_EDGES[run.runId]} />
        <Timeline events={run.events} unknownSentinel={UNKNOWN} />
        <EvidenceInspector events={run.events} anomalies={run.anomalies} unknownSentinel={UNKNOWN} />
        <LiveProjectionPane runId={params.runId} initialEvents={historicalEvents} storeDegraded={false} />
        <ReplayPane runId={params.runId} events={historicalEvents} storeDegraded={false} />
        <ReviewPane runId={params.runId} events={historicalEvents} storeDegraded={false} />
        <p className="text-xs text-muted">
          This is a read-only historical projection. No authority, gate, or live
          state is inferred beyond what the source records. Missing values are
          shown explicitly as &ldquo;{UNKNOWN}&rdquo;. Realtime Broadcast is
          transport only; the durable store remains the source of truth.
        </p>
        <p
          data-testid="data-source-badge"
          className="text-xs font-mono rounded border border-muted px-2 py-1 inline-block"
        >
          data-source: mock · backend: {MOCK_BACKEND} · run: {run.runId}
        </p>
      </section>
    );
  }

  // ---------------- real mode (serverRunRead, no fixture fallback) ----------------
  const detail = await readServerRunDetail(params.runId);
  if (detail.degraded) {
    // Missing config / RLS denial: explicit degraded/unavailable state.
    return (
      <section className="space-y-6">
        <div className="rounded-lg border border-edge bg-panel p-4">
          <p className="text-sm font-semibold text-accent">PROJECTION_UNAVAILABLE</p>
          <p className="mt-1 text-xs text-muted">
            Supabase is not configured or the read was denied (RLS). Real run
            detail is unavailable; no fixture fallback.
          </p>
          <p
            data-testid="projection-status"
            className="mt-3 text-xs font-mono rounded border border-muted px-2 py-1 inline-block"
          >
            canonicalHistoryAvailable: false · projection: PROJECTION_UNAVAILABLE · run:{" "}
            {params.runId}
          </p>
        </div>
      </section>
    );
  }

  if (!detail.run) notFound();

  const run = runViewFromDetail(params.runId, detail);
  const hierarchy = buildHierarchy(run, "real");
  const historicalEvents: ProjectionEvent[] = detail.events;
  const storeDegraded = false;
  const backend = detail.backend;

  return (
    <section className="space-y-6">
      <RootCard run={run} unknownSentinel={UNKNOWN} supabaseReadiness={SUPABASE_READINESS} />
      <RunGraphView hierarchy={hierarchy} activeId={undefined} />
      <DagView gates={run.gates} nodes={run.nodes} edges={DAG_EDGES[run.runId]} />
      <Timeline events={run.events} unknownSentinel={UNKNOWN} />
      <EvidenceInspector events={run.events} anomalies={run.anomalies} unknownSentinel={UNKNOWN} />

      <LiveProjectionPane
        runId={params.runId}
        initialEvents={historicalEvents}
        storeDegraded={storeDegraded}
      />
      <ReplayPane runId={params.runId} events={historicalEvents} storeDegraded={storeDegraded} />
      <ReviewPane runId={params.runId} events={historicalEvents} storeDegraded={storeDegraded} />

      <p className="text-xs text-muted">
        Real read from the publishable/RLS-compatible server path. Exact stored
        values only; genuinely absent fields shown as &ldquo;{UNKNOWN}&rdquo;.
        Reconstructed historical runs with zero canonical events surface
        PROJECTION_UNAVAILABLE; canonical history is never synthesized.
      </p>
      <p
        data-testid="data-source-badge"
        className="text-xs font-mono rounded border border-muted px-2 py-1 inline-block"
      >
        data-source: real · backend: {backend} · run: {run.runId}
      </p>
      <p
        data-testid="projection-status"
        className="text-xs font-mono rounded border border-muted px-2 py-1 inline-block"
      >
        canonicalHistoryAvailable: {String(detail.canonicalHistoryAvailable)} ·
        projection: {detail.projectionStatus}
      </p>
    </section>
  );
}
