// Server Component (Next.js App Router) — M2 run detail.
//
// Runs on the server. Performs the real historical read via the server-only
// Supabase binding (lib/serverHistoricalRead.ts) using the PUBLISHABLE key
// (RLS-compatible). The server secret is consumed here and never serialized to
// the client. Only the read-only snapshot (initialEvents) and a `degraded`
// flag are passed to the browser; the browser never receives any credential.

import { notFound } from "next/navigation";
import type { ProjectionEvent } from "@/lib/live";
import { getRun, UNKNOWN } from "@/lib/observatory";
import { readHistoricalEvents } from "@/lib/serverHistoricalRead";
import { getMockProjectionEvents, MOCK_BACKEND } from "@/lib/mockDataSource";
import RootCard from "@/components/RootCard";
import DagView from "@/components/DagView";
import Timeline from "@/components/Timeline";
import EvidenceInspector from "@/components/EvidenceInspector";
import LiveProjectionPane from "@/components/LiveProjectionPane";
import ReplayPane from "@/components/ReplayPane";
import ReviewPane from "@/components/ReviewPane";

export default async function RunDetailPage({
  params,
}: {
  params: { runId: string };
}) {
  const run = getRun(params.runId);
  if (!run) {
    notFound();
  }

  // M5 — explicit data-source switch (OBSERVATORY_DATA_SOURCE=mock|real).
  //   * mock: deterministic, derived from the SAME in-repo fixtures the M0
  //     surfaces render, with zero Supabase calls. The whole screen
  //     (M0..M4) is internally consistent and reviewable offline.
  //   * real: genuine Supabase historical read; degrades to
  //     PROJECTION_UNAVAILABLE when unconfigured/denied (never a mock-backed
  //     LIVE). This is the default when the env is unset/unknown.
  const dataSource =
    process.env.OBSERVATORY_DATA_SOURCE === "mock" ? "mock" : "real";

  let historicalEvents: ProjectionEvent[] = [];
  let storeDegraded = false;
  let backend: "supabase_publishable" | "supabase_service" | "none" | "mock" =
    "none";

  if (dataSource === "mock") {
    historicalEvents = getMockProjectionEvents(params.runId);
    backend = MOCK_BACKEND;
  } else {
    const historical = await readHistoricalEvents(params.runId);
    historicalEvents = historical.events;
    storeDegraded = historical.degraded;
    backend = historical.backend;
  }

  return (
    <section className="space-y-6">
      <RootCard run={run} unknownSentinel={UNKNOWN} />

      <DagView gates={run.gates} nodes={run.nodes} />

      <Timeline events={run.events} unknownSentinel={UNKNOWN} />

      <EvidenceInspector
        events={run.events}
        anomalies={run.anomalies}
        unknownSentinel={UNKNOWN}
      />

      <LiveProjectionPane
        runId={params.runId}
        initialEvents={historicalEvents}
        storeDegraded={storeDegraded}
      />

      {/* M3 — deterministic replay: one cursor drives every surface. */}
      <ReplayPane
        runId={params.runId}
        events={historicalEvents}
        storeDegraded={storeDegraded}
      />

      {/* M4 — review intelligence derived from the same immutable history. */}
      <ReviewPane
        runId={params.runId}
        events={historicalEvents}
        storeDegraded={storeDegraded}
      />

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
        data-source: {dataSource} · backend: {backend} · run: {run?.runId}
      </p>
    </section>
  );
}
