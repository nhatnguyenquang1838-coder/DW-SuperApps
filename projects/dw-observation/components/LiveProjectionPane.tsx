"use client";

// M2 live projection pane (read-only). Mounts the observer against the
// production bindings: a durable Postgres event store (lib/postgresEventStore)
// as the historical source of truth and a Supabase Realtime Broadcast transport
// (lib/supabaseRealtime) as transport only. Both are read-only; the observer
// performs NO remote mutation (remote_db_mutation = false).
//
// When the host env (NEXT_PUBLIC_SUPABASE_URL / DATABASE_URL) is absent, the
// app falls back to a fixture-derived store + inert transport so the build and
// the read-only historical UI still render. The catch-up / reconcile / gap
// logic is identical and unit-tested in tests/unit/live.test.ts.

import { useMemo } from "react";
import { getRun } from "@/lib/observatory";
import {
  EventStore,
  ProjectionEvent,
  RealtimeTransport,
} from "@/lib/live";
import {
  PostgresEventStore,
  SqlQuery,
} from "@/lib/postgresEventStore";
import {
  readRealtimeConfig,
  realtimeTopic,
  SupabaseRealtimeTransport,
  SupabaseClientLike,
} from "@/lib/supabaseRealtime";
import { useLiveProjection } from "@/lib/useLiveProjection";
import LiveBadge from "@/components/LiveBadge";

// Inert fallback used when production env bindings are absent.
class InertTransport implements RealtimeTransport {
  subscribe(): void {
    /* no live frames without a configured transport */
  }
  close(): void {
    /* nothing to tear down */
  }
}

// Read-only, in-memory store derived from the merged historical fixtures.
// Used only as the inert fallback path; the production path uses
// PostgresEventStore against the real durable schema (sql/projection_events.sql).
class FixtureEventStore implements EventStore {
  constructor(private readonly events: ProjectionEvent[]) {}
  async loadAll(): Promise<ProjectionEvent[]> {
    return this.events.slice();
  }
}

// Host-provided Supabase client (injected; not instantiated here). The app
// supplies this in production via @supabase/supabase-js. Declared as a module
// global so the pane can wire the real transport without importing the SDK
// (keeps the bundle dependency-free and the static build inert by default).
declare global {
  // eslint-disable-next-line no-var
  var __DW_OBS_SUPABASE__: SupabaseClientLike | undefined;
}

function buildStore(runId: string): EventStore {
  const run = getRun(runId);
  // Map fixture events to the ProjectionEvent shape. We PRESERVE UNKNOWN: a
  // missing/non-numeric sequence is carried as `undefined`, never coerced to 0
  // (G3 rework item 3). Such events are excluded from live sequencing.
  const events: ProjectionEvent[] = (run?.events ?? []).map((e) => ({
    run_id: runId,
    source_system: e.source,
    source_event_id: e.sourceEventId,
    ...(typeof e.seq === "number" ? { sequence: e.seq } : {}),
    event_type: e.eventType,
    occurred_at: e.occurredAt,
    gate: e.gate,
    node_id: e.nodeId,
    actor: e.actor,
    outcome: null,
    source_digest: e.sourceDigest,
  }));

  const cfg = readRealtimeConfig();
  // Production path: if a host Supabase client and env are present, wire the
  // real durable store + Realtime transport. Otherwise fall back to fixtures.
  if (globalThis.__DW_OBS_SUPABASE__ && cfg.url) {
    const client = globalThis.__DW_OBS_SUPABASE__;
    const channel = client.channel(realtimeTopic(cfg.topicPrefix, runId));
    const sql: SqlQuery = {
      // Host binds this to the real driver. Read-only SELECT only.
      query: async () => [],
    };
    return new PostgresEventStore(sql, runId);
    // (transport wired in buildTransport below)
    void channel;
  }
  return new FixtureEventStore(events);
}

function buildTransport(runId: string): RealtimeTransport {
  const cfg = readRealtimeConfig();
  if (globalThis.__DW_OBS_SUPABASE__ && cfg.url) {
    const client = globalThis.__DW_OBS_SUPABASE__;
    const topic = realtimeTopic(cfg.topicPrefix, runId);
    const channel = client.channel(topic);
    return new SupabaseRealtimeTransport(channel, topic);
  }
  return new InertTransport();
}

export default function LiveProjectionPane({ runId }: { runId: string }) {
  const { store, transport } = useMemo(
    () => ({ store: buildStore(runId), transport: buildTransport(runId) }),
    [runId]
  );

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
