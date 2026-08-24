// TASK 3 GREEN — server run read adapter (source of truth, REAL connection).
//
// Reads the durable Supabase tables `runs`, `run_gates`, `run_nodes` and
// `projection_events` via the PUBLISHABLE (anon) key boundary (RLS-compatible).
// This module is server-only (Next.js RSC / route handlers); it must not be
// imported by any "use client" component.
//
// CREDENTIAL BOUNDARY:
//   * The DEFAULT (and only implicit) credential is the PUBLISHABLE key,
//     RLS-compatible. There is NO service-role implicit fallback: if the
//     publishable key is absent, the read degrades instead of escalating.
//   * The service key, if present, is OPTIONAL, server-only, never required,
//     and never used as an automatic fallback.
//   * This module performs NO remote mutation (no INSERT/UPDATE/DELETE, no
//     schema/RLS/policy apply, no project creation). It only SELECTs.
//
// DEGRADED CONTRACT:
//   * When config is missing OR a read is denied (RLS), it returns an explicit
//     degraded result (`degraded: true`, `canonicalHistoryAvailable: false`,
//     `projectionStatus: "PROJECTION_UNAVAILABLE"`). The caller MUST surface
//     PROJECTION_UNAVAILABLE, NEVER a fixture-backed LIVE state.
//   * A reconstructed historical run with empty `projection_events` likewise
//     reports `canonicalHistoryAvailable=false` + PROJECTION_UNAVAILABLE —
//     we never synthesize canonical history.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { ProjectionEvent } from "@/lib/live";
import { mapRowToProjectionEvent } from "@/lib/postgresEventStore";

type Row = Record<string, unknown>;

export interface ServerReadConfig {
  url?: string;
  publishableKey?: string; // default credential (RLS-compatible)
  serviceKey?: string; // optional, server-only, never required
}

export function readServerConfig(): ServerReadConfig {
  return {
    url:
      (typeof process !== "undefined" && process.env?.SUPABASE_URL) ||
      undefined,
    publishableKey:
      (typeof process !== "undefined" &&
        process.env?.SUPABASE_READ_PUBLISHABLE_KEY) ||
      undefined,
    serviceKey:
      (typeof process !== "undefined" &&
        process.env?.SUPABASE_SERVICE_ROLE_KEY) ||
      undefined,
  };
}

// Build a real Supabase client using the PUBLISHABLE key only. NO implicit
// service-role fallback: if url or publishable key is absent we return null
// (degraded) rather than silently escalating to the service role.
export function createServerClient(
  cfg: ServerReadConfig,
): { client: SupabaseClient; backend: "supabase_publishable" } | null {
  if (!cfg.url || !cfg.publishableKey) return null;
  const client = createClient(cfg.url, cfg.publishableKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return { client, backend: "supabase_publishable" };
}

// Minimal duck-typed read client accepted by the test seam. Mirrors the shape
// of the real Supabase client's query builder (from/select/eq/order/maybeSingle).
type ReadClient = {
  from: (table: string) => {
    select: (cols: string) => unknown;
  };
};

export interface ServerRunListResult {
  degraded: boolean;
  runs: Row[];
}

export interface ServerRunDetailResult {
  degraded: boolean;
  backend: "supabase_publishable" | "none";
  run: Row | null;
  gates: Row[];
  nodes: Row[];
  events: ProjectionEvent[];
  canonicalHistoryAvailable: boolean;
  projectionStatus: "AVAILABLE" | "PROJECTION_UNAVAILABLE";
}

function toRows(data: unknown): Row[] {
  if (Array.isArray(data)) return data as Row[];
  if (data && typeof data === "object") return [data as Row];
  return [];
}

function degradedDetail(backend: "supabase_publishable" | "none"): ServerRunDetailResult {
  return {
    degraded: true,
    backend,
    run: null,
    gates: [],
    nodes: [],
    events: [],
    canonicalHistoryAvailable: false,
    projectionStatus: "PROJECTION_UNAVAILABLE",
  };
}

// Real list read: SELECT from `runs` only, read-only, ordered by started_at.
// `clientOverride` is a test seam; production callers omit it.
export async function readServerRunList(
  clientOverride?: ReadClient,
): Promise<ServerRunListResult> {
  const built = clientOverride
    ? { client: clientOverride as SupabaseClient, backend: "supabase_publishable" as const }
    : createServerClient(readServerConfig());
  if (!built) return { degraded: true, runs: [] };

  const { data, error } = await (built.client as SupabaseClient)
    .from("runs")
    .select(
      "run_id, run_kind, source_system, base_sha, head_sha, branch, pr_number, ci_run_id, ci_status, started_at, completed_at, confidence, evidence_quality",
    )
    .order("started_at", { ascending: true });

  if (error) return { degraded: true, runs: [] };
  return { degraded: false, runs: toRows(data) };
}

// Real detail read: exact stored `runs`, `run_gates`, `run_nodes` and
// `projection_events` values. Never synthesizes canonical history.
// `clientOverride` is a test seam; production callers omit it.
export async function readServerRunDetail(
  runId: string,
  clientOverride?: ReadClient,
): Promise<ServerRunDetailResult> {
  const built = clientOverride
    ? { client: clientOverride as SupabaseClient, backend: "supabase_publishable" as const }
    : createServerClient(readServerConfig());
  if (!built) return degradedDetail("none");

  const client = built.client as SupabaseClient;

  // 1) runs row (exact stored values).
  const runRes = await client
    .from("runs")
    .select(
      "run_id, run_kind, source_system, epic_id, jira_key, base_sha, head_sha, merge_sha, base_branch, branch, pr_number, ci_run_id, ci_status, started_at, completed_at, reconstruction_basis, source_refs, confidence, evidence_quality, reconstructed_by, reconstructed_at, payload",
    )
    .eq("run_id", runId)
    .maybeSingle();
  if (runRes.error) return degradedDetail(built.backend);
  const run = (runRes.data as Row | null) ?? null;

  // 2) run_gates rows (exact stored values).
  const gatesRes = await client
    .from("run_gates")
    .select(
      "gate_id, run_id, gate_label, boundary, authority_ref, state, summary, node_count, artifact_count, source_refs",
    )
    .eq("run_id", runId)
    .order("gate_id", { ascending: true });
  if (gatesRes.error) return { ...degradedDetail(built.backend), run };
  const gates = toRows(gatesRes.data);

  // 3) run_nodes rows (exact stored values).
  const nodesRes = await client
    .from("run_nodes")
    .select("node_id, run_id, gate_id, family, boundary, state, label, source_refs")
    .eq("run_id", runId)
    .order("node_id", { ascending: true });
  if (nodesRes.error) return { ...degradedDetail(built.backend), run, gates };
  const nodes = toRows(nodesRes.data);

  // 4) projection_events (canonical live history) — ordered by the durable
  //    projection_ordinal. Empty => canonicalHistoryAvailable=false.
  const eventsRes = await client
    .from("projection_events")
    .select(
      "run_id, source_system, source_event_id, sequence, projection_ordinal, event_type, occurred_at, gate, node_id, actor, outcome, before, after, evidence_refs, authority_ref, source_digest, read_only_projection",
    )
    .eq("run_id", runId)
    .order("projection_ordinal", { ascending: true });
  if (eventsRes.error) {
    return { ...degradedDetail(built.backend), run, gates, nodes };
  }
  const events = toRows(eventsRes.data).map(mapRowToProjectionEvent);
  const canonicalHistoryAvailable = events.length > 0;

  return {
    degraded: false,
    backend: built.backend,
    run,
    gates,
    nodes,
    events,
    canonicalHistoryAvailable,
    projectionStatus: canonicalHistoryAvailable
      ? "AVAILABLE"
      : "PROJECTION_UNAVAILABLE",
  };
}
