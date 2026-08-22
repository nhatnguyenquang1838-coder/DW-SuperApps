// M2 — Postgres durable projection event store (read-only).
//
// Repository-only production binding for the durable store described in
// sql/projection_events.sql. Read-only: it performs SELECTs only and never
// mutates the database. The actual Postgres client (e.g. `pg` / `postgres`)
// is injected as a minimal query function so this module stays framework- and
// driver-agnostic, dependency-free, and fully unit-testable offline.
//
// Historical replay is the source of truth. Realtime Broadcast (lib/live.ts
// RealtimeTransport) is a separate transport and is never canonical history.

import { EventStore, ProjectionEvent } from "@/lib/live";

export interface SqlQuery {
  // Minimal, dependency-free query surface. The host supplies an implementation
  // backed by `pg`, `postgres`, or an edge runtime binding. The observer only
  // ever reads; no INSERT/UPDATE/DELETE is issued here (remote_db_mutation=false).
  query: (text: string, params: unknown[]) => Promise<Array<Record<string, unknown>>>;
}

const SELECT_BY_RUN = `
  SELECT run_id, source_system, source_event_id, sequence, event_type,
         occurred_at, gate, node_id, actor, outcome, before, after,
         evidence_refs, authority_ref, source_digest, read_only_projection
  FROM projection_events
  WHERE run_id = $1
  ORDER BY source_system, sequence`;

export function mapRowToProjectionEvent(row: Record<string, unknown>): ProjectionEvent {
  const seq = row.sequence;
  return {
    run_id: String(row.run_id),
    source_system: String(row.source_system),
    source_event_id: String(row.source_event_id),
    // Map the canonical source sequence. We never fabricate a value: if the
    // stored sequence is missing/non-numeric we EXCLUDE it from live sequencing
    // rather than emitting a fake 0 (see G3 rework item 3).
    ...(typeof seq === "number" ? { sequence: seq } : {}),
    event_type: row.event_type != null ? String(row.event_type) : "",
    occurred_at: row.occurred_at != null ? String(row.occurred_at) : "",
    gate: row.gate != null ? String(row.gate) : undefined,
    node_id: row.node_id != null ? String(row.node_id) : undefined,
    actor: row.actor ?? undefined,
    outcome: row.outcome != null ? String(row.outcome) : undefined,
    before: (row.before as object | null) ?? undefined,
    after: (row.after as object | null) ?? undefined,
    evidence_refs: Array.isArray(row.evidence_refs)
      ? (row.evidence_refs as unknown[]).map(String)
      : [],
    authority_ref: row.authority_ref != null ? String(row.authority_ref) : undefined,
    source_digest: row.source_digest != null ? String(row.source_digest) : undefined,
  };
}

export class PostgresEventStore implements EventStore {
  constructor(private readonly sql: SqlQuery, private readonly runId: string) {}

  async loadAll(_runId: string = this.runId): Promise<ProjectionEvent[]> {
    const rows = await this.sql.query(SELECT_BY_RUN, [this.runId]);
    return rows.map(mapRowToProjectionEvent);
  }
}
