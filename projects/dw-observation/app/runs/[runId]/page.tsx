// Server Component (Next.js App Router) — M2 run detail.
//
// Runs on the server. Performs the real historical read via the server-only
// Supabase binding (lib/serverHistoricalRead.ts) using the PUBLISHABLE key
// (RLS-compatible). The server secret is consumed here and never serialized to
// the client. Only the read-only snapshot (initialEvents) and a `degraded`
// flag are passed to the browser; the browser never receives any credential.

import { notFound } from "next/navigation";
import { getRun, UNKNOWN } from "@/lib/observatory";
import { readHistoricalEvents } from "@/lib/serverHistoricalRead";
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

  // Server-side real historical read (source of truth). Degrades gracefully:
  // if config is missing or the read is denied, historical is empty and the
  // client surfaces PROJECTION_UNAVAILABLE (never a fixture-backed LIVE).
  const historical = await readHistoricalEvents(params.runId);

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
        initialEvents={historical.events}
        storeDegraded={historical.degraded}
      />

      {/* M3 — deterministic replay: one cursor drives every surface. */}
      <ReplayPane
        runId={params.runId}
        events={historical.events}
        storeDegraded={historical.degraded}
      />

      {/* M4 — review intelligence derived from the same immutable history. */}
      <ReviewPane
        runId={params.runId}
        events={historical.events}
        storeDegraded={historical.degraded}
      />

      <p className="text-xs text-muted">
        This is a read-only historical projection. No authority, gate, or live
        state is inferred beyond what the source records. Missing values are
        shown explicitly as &ldquo;{UNKNOWN}&rdquo;. Realtime Broadcast is
        transport only; the durable store remains the source of truth.
      </p>
    </section>
  );
}
