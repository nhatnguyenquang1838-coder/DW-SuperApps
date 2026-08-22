"use client";

// M2 live projection pane (read-only client component).
//
// Receives the server-read historical snapshot (initialEvents) and a
// storeDegraded flag as props — NO credential ever crosses this boundary.
// It wires the real browser Supabase Broadcast transport (lib/supabaseRealtime,
// which creates its own browser client from NEXT_PUBLIC_* publishable key) and
// feeds the durable snapshot into the observer as the source of truth.
//
// If the server read was denied/missing (storeDegraded), the observer is seeded
// with an empty store and surfaces PROJECTION_UNAVAILABLE — it must NOT fall
// back to fixtures as a LIVE state (per Controller credential-boundary rule).

import { useMemo } from "react";
import {
  EventStore,
  ProjectionEvent,
  RealtimeTransport,
} from "@/lib/live";
import { PostgresEventStore } from "@/lib/postgresEventStore";
import { SupabaseRealtimeTransport, realtimeTopic, readBrowserConfig } from "@/lib/supabaseRealtime";
import { useLiveProjection } from "@/lib/useLiveProjection";
import LiveBadge from "@/components/LiveBadge";

// Read-only in-memory store over the server-provided snapshot. This is the
// durable snapshot; it is passed in from the server component, never fetched
// here with a credential.
class SnapshotEventStore implements EventStore {
  constructor(private readonly events: ProjectionEvent[]) {}
  async loadAll(): Promise<ProjectionEvent[]> {
    return this.events.slice();
  }
}

function buildStore(initialEvents: ProjectionEvent[]): EventStore {
  // Real adapter over the server snapshot. If empty (degraded), the observer
  // will surface PROJECTION_UNAVAILABLE — no fixture substitution.
  return new PostgresEventStore(async () => initialEvents.slice(), "");
}

function buildTransport(runId: string): RealtimeTransport {
  const cfg = readBrowserConfig();
  if (cfg.url && cfg.anonKey) {
    // Real browser transport: owns its own createClient() + channel lifecycle.
    return new SupabaseRealtimeTransport(realtimeTopic(cfg.topicPrefix, runId));
  }
  // Inert fallback: no NEXT_PUBLIC_* env -> snapshot-only, no live frames.
  return {
    subscribe: () => {},
    close: () => {},
  };
}

export default function LiveProjectionPane({
  runId,
  initialEvents = [],
  storeDegraded = false,
}: {
  runId: string;
  initialEvents?: ProjectionEvent[];
  storeDegraded?: boolean;
}) {
  const { store, transport } = useMemo(
    () => ({
      store: buildStore(storeDegraded ? [] : initialEvents),
      transport: buildTransport(runId),
    }),
    [runId, initialEvents, storeDegraded]
  );

  const view = useLiveProjection(runId, store, transport);

  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <div className="flex items-center justify-between">
        <h2 className="mb-2 text-base font-semibold">Live projection</h2>
        <LiveBadge state={view.state} />
      </div>
      <p className="text-xs text-muted">
        Source of truth: durable Postgres projection (server read). Broadcast is
        transport only. Read-only; no remote mutation.
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
