// M5 — deterministic mock data source for local review (no Supabase).
//
// The M0-M4 surfaces must be reviewable locally without a live Supabase
// `projection_events` table. This module derives a STABLE, deterministic
// ProjectionEvent[] from the SAME in-repo fixtures already used by the M0
// surfaces (lib/observatory.ts), so the whole screen is internally consistent
// in `mock` mode — M0 (fixtures) and M3/M4 (these derived events) describe the
// identical run.
//
// Determinism contract: pure mapping of the fixture bundles, no clock, no
// randomness, no I/O. Two calls for the same runId yield byte-identical output.
// This is the property the M5 review requires: a reviewer sees the same thing
// every load.
//
// This module performs NO remote mutation and never contacts Supabase.

import type { ProjectionEvent } from "@/lib/live";
import { getRun } from "@/lib/observatory";

/**
 * Build the deterministic mock ProjectionEvent[] for a run.
 *
 * In mock mode, the M5 review run (DW-OBS-M5-20260823-MOCK) replays its full
 * material event stream (G2/G3/G4 lifecycle, node progresses, CI, PR, G4 merge,
 * issue closure, Supabase boundary) so the M3/M4 panes derive from the SAME
 * events the M0 surfaces render — never PROJECTION_UNAVAILABLE.
 *
 * Returns [] when the runId is unknown to the fixture bundles (so the M3/M4
 * panes simply have nothing to show rather than fabricating a LIVE state).
 */
export function getMockProjectionEvents(runId: string): ProjectionEvent[] {
  const run = getRun(runId, "mock");
  if (!run) return [];

  return run.events.map((e) => {
    const ev: ProjectionEvent = {
      run_id: runId,
      source_system: e.source,
      source_event_id: e.sourceEventId,
      occurred_at: e.occurredAt,
      event_type: e.eventType,
      actor: e.actor,
      before: e.before,
      after: e.after,
      evidence_refs: e.evidenceRefs,
    };
    // Preserve source sequence only when explicitly present; never fabricate.
    if (e.seq !== null) ev.sequence = e.seq;
    if (e.gate) ev.gate = e.gate;
    if (e.nodeId) ev.node_id = e.nodeId;
    if (e.authorityRef) ev.authority_ref = e.authorityRef;
    return ev;
  });
}

/** Stable backend label for audit / no-mutation proof. */
export const MOCK_BACKEND = "mock" as const;
