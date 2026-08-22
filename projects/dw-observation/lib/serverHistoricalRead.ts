// M2 — server-side historical read (source of truth). REAL connection (R2).
//
// Runs ONLY on the server (Next.js RSC / route handlers — this module must not
// be imported by any "use client" component). Reads the durable
// projection_events rows for a run with a real `.from(...).select(...)`.
//
// CREDENTIAL BOUNDARY (per Controller intercept, G3_R2):
//   * The DEFAULT historical read uses the PROJECT URL + PUBLISHABLE (anon) key
//     and is RLS-compatible. This is safe read-only usage and is the required
//     path for G3 acceptance — no service-role key needed.
//   * A SERVICE/SECRET key, if provided, is OPTIONAL, server-only, never
//     NEXT_PUBLIC_*, never logged/serialized/passed to props, and never
//     REQUIRED. It is only honored when present for environments that need it;
//     it must NOT be used to bypass RLS simply to make tests pass.
//   * This module performs NO remote mutation (no INSERT/UPDATE/DELETE, no
//     schema/RLS/policy apply, no project creation). It only SELECTs.
//   * When config is missing OR the read is denied, it returns a result with
//     `events: []` and `degraded: true` — the caller must surface
//     PROJECTION_UNAVAILABLE, NOT a fixture-backed LIVE state.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { ProjectionEvent } from "@/lib/live";
import { mapRowToProjectionEvent } from "@/lib/postgresEventStore";

export interface ServerHistoricalReadResult {
  events: ProjectionEvent[];
  // How the read was satisfied (for audit / no-mutation proof).
  backend: "supabase_publishable" | "supabase_service" | "none";
  // True when no real read happened (config missing or read denied). The caller
  // MUST surface PROJECTION_UNAVAILABLE rather than fabricate a snapshot.
  degraded: boolean;
}

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
    // Default credential: publishable/anon key (server-side usage is fine and
    // respects RLS). Never a NEXT_PUBLIC_* leak.
    publishableKey:
      (typeof process !== "undefined" &&
        process.env?.SUPABASE_READ_PUBLISHABLE_KEY) ||
      undefined,
    // Optional only; never required for G3 acceptance.
    serviceKey:
      (typeof process !== "undefined" &&
        process.env?.SUPABASE_SERVICE_ROLE_KEY) ||
      undefined,
  };
}

// Build a real Supabase client. The DEFAULT (and only implicit) credential is
// the PUBLISHABLE key (RLS-compatible). Per Controller intercept (seq=15) there
// is NO implicit service-role fallback: if the publishable key is absent the
// read cannot proceed and we return null (degraded), rather than silently
// escalating to the service role. The service key, when present, is OPTIONAL,
// server-only, and never required — it is intentionally NOT used unless the
// caller explicitly opts in by passing ONLY a service key (never as a fallback).
export function createServerClient(
  cfg: ServerReadConfig
): { client: SupabaseClient; backend: "supabase_publishable" | "supabase_service" } | null {
  if (!cfg.url) return null;
  // F5 (seq=15): NO implicit service-role fallback. The DEFAULT (and only
  // implicit) credential is the publishable key. If it is absent we MUST NOT
  // silently escalate to the service role — return null (degraded) instead. The
  // service key is an explicit opt-in used ONLY when publishable is genuinely
  // absent AND a service key was deliberately supplied (never as a fallback).
  if (!cfg.publishableKey) return null;
  const key = cfg.publishableKey;
  const backend: "supabase_publishable" | "supabase_service" =
    cfg.publishableKey ? "supabase_publishable" : "supabase_service";
  // Read-only client (no write capabilities invoked here). The service key, if
  // used, is never serialized to the browser and never weakens RLS as a side
  // effect of this read.
  const client = createClient(cfg.url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return { client, backend };
}

// Real historical read. Returns a degraded result when env is absent or the
// read is denied — the caller surfaces PROJECTION_UNAVAILABLE, never a
// fixture-backed LIVE. NEVER throws on missing env.
// `clientOverride` is a test seam (real SupabaseClient) so the read path can be
// exercised without network; production callers omit it.
export async function readHistoricalEvents(
  runId: string,
  clientOverride?: SupabaseClient
): Promise<ServerHistoricalReadResult> {
  const cfg = readServerConfig();
  const built = clientOverride
    ? { client: clientOverride, backend: "supabase_publishable" as const }
    : createServerClient(cfg);
  if (!built) {
    return { events: [], backend: "none", degraded: true };
  }
  const { client, backend } = built;

  // Real SELECT against the durable projection_events table. Read-only.
  const { data, error } = await client
    .from("projection_events")
    .select(
      "run_id, source_system, source_event_id, sequence, event_type, occurred_at, gate, node_id, actor, outcome, before, after, evidence_refs, authority_ref, source_digest"
    )
    .eq("run_id", runId)
    .order("source_system", { ascending: true })
    .order("sequence", { ascending: true });

  if (error) {
    // Read denied (e.g. RLS) degrades the observer; it must not throw nor fall
    // back to fixtures as LIVE.
    return { events: [], backend: "none", degraded: true };
  }
  const rows = Array.isArray(data) ? data : [];
  return {
    events: rows.map((r) => mapRowToProjectionEvent(r as Record<string, unknown>)),
    backend,
    degraded: false,
  };
}
