"use client";

// M2 live projection pane (read-only). Mounts the observer against a local,
// fixture-derived store and an inert transport. The static build performs NO
// remote DB/Supabase mutation: the durable store is read-only and the live
// transport is inert here. Realtime Broadcast wiring (and the real Postgres
// store) is supplied by the host app at runtime; the catch-up / reconcile /
// gap logic is unit-tested in tests/unit/live.test.ts.

import { useMemo } from "react";
import { getRun } from "@/lib/observatory";
import { EventStore, ProjectionEvent, RealtimeTransport } from "@/lib/live";
import { useLiveProjection } from "@/lib/useLiveProjection";
import LiveBadge from "@/components/LiveBadge";

class FixtureEventStore implements EventStore {
  constructor(private readonly events: ProjectionEvent[]) {}
  async loadAll(): Promise<ProjectionEvent[]> {
    return this.events.slice();
  }
}

class InertTransport implements RealtimeTransport {
  subscribe(): void {
    /* no live frames in the static read-only build */
  }
  close(): void {
    /* nothing to tear down */
  }
}

export default function LiveProjectionPane({ runId }: { runId: string }) {
  const { store, transport } = useMemo(() => {
    const run = getRun(runId);
    const events: ProjectionEvent[] = (run?.events ?? []).map((e) => ({
      run_id: runId,
      source_system: e.source,
      source_event_id: e.sourceEventId,
      sequence: e.seq ?? 0,
      event_type: e.eventType,
      occurred_at: e.occurredAt,
      gate: e.gate,
      node_id: e.nodeId,
      actor: e.actor,
      outcome: null,
      source_digest: e.sourceDigest,
    }));
    return { store: new FixtureEventStore(events), transport: new InertTransport() };
  }, [runId]);

  const view = useLiveProjection(runId, store, transport);

  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <div className="flex items-center justify-between">
        <h2 className="mb-2 text-base font-semibold">Live projection</h2>
        <LiveBadge state={view.state} />
      </div>
      <p className="text-xs text-muted">
        Source of truth: durable Postgres projection. Broadcast is transport
        only. Read-only; no remote mutation.
      </p>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        <div>
          <dt className="text-muted">Projected events</dt>
          <dd className="code">{view.eventCount}</dd>
        </div>
        <div>
          <dt className="text-muted">Anomalies</dt>
          <dd className="code">{view.anomalies.length}</dd>
        </div>
      </dl>
      {view.anomalies.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {view.anomalies.map((a, i) => (
            <li
              key={i}
              className="rounded border border-edge/60 bg-surface px-3 py-1.5 text-sm"
            >
              <span className="font-medium text-accent">{a.kind}</span>
              <span className="ml-2 text-xs text-muted">{a.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {view.lastError ? (
        <p className="mt-2 text-xs text-red-400">{view.lastError}</p>
      ) : null}
    </div>
  );
}
