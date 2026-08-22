// M2 — durable projection event store (read-only adapter).
//
// Repository-only, framework-agnostic adapter over the durable store. The actual
// read is performed by a real backend (lib/serverHistoricalRead.ts -> Supabase
// service-role SELECT, or a host-injected SqlQuery). This adapter performs NO
// remote mutation; it only maps rows. There is intentionally NO dummy empty
// fallback query path — the store requires a genuine read function.

import { EventStore, ProjectionEvent } from "@/lib/live";

export interface SqlQuery {
  // Minimal, dependency-free query surface for hosts that prefer a raw driver
  // (pg / postgres / edge runtime). The observer only ever reads; no
  // INSERT/UPDATE/DELETE is issued here (remote_db_mutation = false).
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
    // Never fabricate a sequence: if the stored sequence is missing/non-numeric
    // we EXCLUDE it from live sequencing rather than emitting a fake 0.
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
  // `read` performs the real historical read for a run. It is supplied by the
  // host (server-side Supabase SELECT or an injected SqlQuery) — never a dummy.
  constructor(
    private readonly read: (runId: string) => Promise<ProjectionEvent[]>,
    private readonly runId: string
  ) {}

  // Convenience factory: build from a real SqlQuery binding (host driver).
  static fromSql(sql: SqlQuery, runId: string): PostgresEventStore {
    return new PostgresEventStore(async (id) => {
      const rows = await sql.query(SELECT_BY_RUN, [id]);
      return rows.map(mapRowToProjectionEvent);
    }, runId);
  }

  async loadAll(): Promise<ProjectionEvent[]> {
    // Genuine read through the injected backend. No empty-fallback path.
    return this.read(this.runId);
  }
}
