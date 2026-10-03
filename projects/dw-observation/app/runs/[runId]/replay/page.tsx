// Server Component — Run Replay isolation.
//
// /runs/[runId]/replay isolates replay into its own route.
// No live/future event mixing: replay shows only canonical historical events
// for the selected run. Read-only. Grants no effect capability.

import { notFound } from "next/navigation";
import { getRun, UNKNOWN, DAG_EDGES } from "@/lib/observatory";
import { getMockProjectionEvents } from "@/lib/mockDataSource";
import type { ProjectionEvent } from "@/lib/live";
import ReplayPane from "@/components/ReplayPane";
import DagView from "@/components/DagView";
import Timeline from "@/components/Timeline";

export default function RunReplayPage({ params }: { params: { runId: string } }) {
  const dataSource =
    process.env.OBSERVATORY_DATA_SOURCE === "mock" ? "mock" : "real";

  const run = getRun(params.runId, dataSource);
  if (!run) notFound();

  // REPLAY ISOLATION: only canonical events, no live projection mixing.
  const events: ProjectionEvent[] =
    dataSource === "mock"
      ? getMockProjectionEvents(params.runId)
      : []; // real mode replay uses server-sourced events — not yet wired here

  return (
    <div
      className="min-h-screen"
      style={{
        background: "#ffffff",
        color: "#37352f",
        fontFamily:
          'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif',
      }}
    >
      <style>{`
        .notion-run-card { border-color: #e9e9e7; background: #ffffff; }
        .notion-link-btn { border-color: #d3d1cb; background: #f7f7f5; color: #37352f; }
        .notion-link-btn:hover { background: #efefed; }
      `}</style>
      <div className="mx-auto max-w-5xl px-6 py-10">
        <nav className="mb-6 text-xs" style={{ color: "#9b9a97" }}>
          <a href="/tasks" style={{ color: "#787774" }}>Tasks</a> /{" "}
          <a href="/runs" style={{ color: "#787774" }}>Run Explorer</a> /{" "}
          <span style={{ color: "#37352f" }}>{run.runId}</span> /{" "}
          <span style={{ color: "#37352f" }}>Replay</span>
        </nav>

        <h1 className="mb-1 text-2xl font-bold tracking-tight" style={{ color: "#37352f" }}>
          {run.runId} — Replay
        </h1>
        <p className="mb-6 text-xs" style={{ color: "#787774" }}>
          Canonical replay only — no live or future event mixing.
        </p>

        <DagView gates={run.gates} nodes={run.nodes} edges={DAG_EDGES[run.runId]} />
        <Timeline events={run.events} unknownSentinel={UNKNOWN} />
        <ReplayPane runId={params.runId} events={events} storeDegraded={false} />

        <a
          href={`/runs/${encodeURIComponent(run.runId)}`}
          className="notion-link-btn mt-8 inline-block rounded border px-3 py-1.5 text-sm"
        >
          ← Back to run detail
        </a>

        <p
          data-testid="replay-data-source-badge"
          className="mt-4 inline-block rounded border px-2 py-1 font-mono text-xs"
          style={{ borderColor: "#e9e9e7", color: "#787774" }}
        >
          data-source: {dataSource} · mode: replay-only
        </p>
      </div>
    </div>
  );
}
