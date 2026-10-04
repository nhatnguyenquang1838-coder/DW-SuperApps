/**
 * T06 — Real replay reducer + same-shell replay mode; remove mock event fallback.
 *
 * Verifies:
 *   1. Source guard: mock fallback expression gone from replay path
 *   2. Snapshot at beginning / middle / end of history
 *   3. Event with sequence > selected never appears in replay
 *   4. Invalid sequence fails closed (REPLAY_POSITION_UNAVAILABLE)
 *   5. Missing history yields PROJECTION_UNAVAILABLE
 */

import { describe, expect, it } from "vitest";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import fs from "node:fs";
import path from "node:path";
import { reduceEvents } from "@/lib/replay";
import type { ProjectionEvent } from "@/lib/live";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEvent(
  seq: number,
  eventType: string,
  overrides: Partial<ProjectionEvent> = {}
): ProjectionEvent {
  return {
    run_id: "RUN-T06",
    source_system: "taskcontroller",
    source_event_id: `evt_${seq}`,
    sequence: seq,
    projection_ordinal: seq + 1,
    occurred_at: `2026-08-23T10:${String(seq).padStart(2, "0")}:00Z`,
    event_type: eventType,
    ...overrides,
  } as ProjectionEvent;
}

/** Canonical stream: sequences 0..9 */
function canonicalStream(): ProjectionEvent[] {
  return Array.from({ length: 10 }, (_, i) =>
    makeEvent(i, i === 0 ? "run_started" : "node_progress")
  );
}

// ---------------------------------------------------------------------------
// Mock Supabase client (mirrors serverRunRead.test.ts pattern)
// ---------------------------------------------------------------------------

function mockSupabaseClient(events: ProjectionEvent[]) {
  const rows = events.map((e) => ({
    run_id: e.run_id,
    source_system: e.source_system,
    source_event_id: e.source_event_id,
    sequence: typeof e.sequence === "number" ? e.sequence : null,
    projection_ordinal: typeof e.projection_ordinal === "number" ? e.projection_ordinal : null,
    event_type: e.event_type,
    occurred_at: e.occurred_at ?? null,
    gate: (e as Record<string, unknown>).gate ?? null,
    node_id: (e as Record<string, unknown>).node_id ?? null,
    actor: (e as Record<string, unknown>).actor ?? null,
    outcome: (e as Record<string, unknown>).outcome ?? null,
    before: (e as Record<string, unknown>).before ?? null,
    after: (e as Record<string, unknown>).after ?? null,
    evidence_refs: Array.isArray((e as Record<string, unknown>).evidence_refs)
      ? (e as Record<string, unknown>).evidence_refs
      : null,
    authority_ref: (e as Record<string, unknown>).authority_ref ?? null,
    source_digest: (e as Record<string, unknown>).source_digest ?? null,
  }));
  const result = { data: rows, error: null };
  return {
    from: (_table: string) => ({
      select: (_cols: string) => ({
        eq: (_col: string, _val: string) => ({
          order: async () => result,
        }),
      }),
    }),
  };
}

// ---------------------------------------------------------------------------
// Lazy module loader (mirrors serverRunRead.test.ts pattern)
// ---------------------------------------------------------------------------

const REPLAY_MOD_PATH = resolve(process.cwd(), "lib/runtime/replay.ts");

async function loadReplayMod() {
  if (!existsSync(REPLAY_MOD_PATH)) {
    throw new Error(
      "T06 RED: lib/runtime/replay.ts is not implemented yet (missing replay module)"
    );
  }
  return import(/* @vite-ignore */ REPLAY_MOD_PATH);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("T06 · Replay isolation", () => {
  // --- Source guard: mock fallback must be gone ---
  describe("source guard", () => {
    const replayPagePath = path.resolve(
      process.cwd(),
      "app/runs/[runId]/replay/page.tsx"
    );
    const replayPageContent = fs.readFileSync(replayPagePath, "utf-8");

    it('source guard: mock fallback expression removed from replay path', () => {
      expect(replayPageContent).not.toContain("getMockProjectionEvents");
    });
  });

  // --- Snapshot at beginning / middle / end of history ---
  describe("snapshot at beginning / middle / end of history", () => {
    const events = canonicalStream();

    it("snapshot at beginning (seq=0) applies only run_started", () => {
      const historicalEvents = events.filter(
        (e) => typeof e.sequence === "number" && e.sequence <= 0
      );
      const snapshot = reduceEvents(historicalEvents);
      expect(snapshot.events).toHaveLength(1);
      expect(snapshot.runId).toBe("RUN-T06");
    });

    it("snapshot at middle (seq=4) applies 5 events (0..4)", () => {
      const historicalEvents = events.filter(
        (e) => typeof e.sequence === "number" && e.sequence <= 4
      );
      const snapshot = reduceEvents(historicalEvents);
      expect(snapshot.events).toHaveLength(5);
    });

    it("snapshot at end (seq=9) applies all 10 events", () => {
      const historicalEvents = events.filter(
        (e) => typeof e.sequence === "number" && e.sequence <= 9
      );
      const snapshot = reduceEvents(historicalEvents);
      expect(snapshot.events).toHaveLength(10);
    });
  });

  // --- Event with sequence > selected never appears ---
  describe("event sequence filter", () => {
    const events = canonicalStream();

    it("event with sequence > selected never appears in replay snapshot", () => {
      const selectedSequence = 3;
      const historicalEvents = events.filter(
        (e) => typeof e.sequence === "number" && e.sequence <= selectedSequence
      );
      const snapshot = reduceEvents(historicalEvents);
      for (const e of snapshot.events) {
        const seq = typeof e.sequence === "number" ? e.sequence : Infinity;
        expect(seq).toBeLessThanOrEqual(selectedSequence);
      }
    });
  });

  // --- Failure states (module-dependent) ---
  describe("failure states", () => {
    it("missing history yields PROJECTION_UNAVAILABLE", async () => {
      const mod = await loadReplayMod();
      const result = await mod.getReplaySnapshot("NONEXISTENT-RUN", 0);
      expect(result.status).toBe(mod.PROJECTION_UNAVAILABLE);
    });

    it("invalid sequence fails closed: REPLAY_POSITION_UNAVAILABLE", async () => {
      const mod = await loadReplayMod();
      const events = canonicalStream();
      const mockClient = mockSupabaseClient(events);
      // Request a sequence far beyond the max (9) → must fail closed.
      const result = await mod.getReplaySnapshot("RUN-T06", 99999, mockClient);
      expect(result.status).toBe(mod.REPLAY_POSITION_UNAVAILABLE);
    });
  });
});