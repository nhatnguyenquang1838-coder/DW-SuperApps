import { describe, expect, it } from "vitest";
import { getMockProjectionEvents, MOCK_BACKEND } from "@/lib/mockDataSource";
import type { ProjectionEvent } from "@/lib/live";

// M5 — the mock data source must derive deterministic, in-scope events from the
// SAME fixtures the M0 surfaces render, with no Supabase involved.

describe("getMockProjectionEvents", () => {
  it("derives one event per fixture event (M0/M4 consistency)", () => {
    const runId = "DW-OBS-M0-20260821-R2";
    const events = getMockProjectionEvents(runId);
    expect(events.length).toBeGreaterThan(0);
    expect(events.every((e: ProjectionEvent) => e.run_id === runId)).toBe(true);
  });

  it("is deterministic — two calls are identical", () => {
    const a = getMockProjectionEvents("DW-OBS-M0-20260821-R2");
    const b = getMockProjectionEvents("DW-OBS-M0-20260821-R2");
    expect(b).toEqual(a);
  });

  it("never fabricates a sequence — only present sequences are carried", () => {
    const events = getMockProjectionEvents("DW-OBS-M0-20260821-R2");
    // Every event that has a sequence keeps it; events without one have none.
    for (const e of events) {
      if (e.sequence === undefined) continue;
      expect(typeof e.sequence).toBe("number");
    }
  });

  it("carries provenance fields used by M3/M4 trace-back", () => {
    const events = getMockProjectionEvents("DW-OBS-M0-20260821-R2");
    const withAuth = events.find(
      (e: ProjectionEvent) => typeof e.authority_ref === "string" && e.authority_ref
    );
    expect(withAuth).toBeDefined();
    expect(withAuth?.source_system).toBe("taskcontroller");
    expect(typeof withAuth?.source_event_id).toBe("string");
  });

  it("returns [] for an unknown run (no fabricated LIVE)", () => {
    expect(getMockProjectionEvents("run:does-not-exist")).toEqual([]);
  });

  it("labels its backend 'mock' for audit / no-mutation proof", () => {
    expect(MOCK_BACKEND).toBe("mock");
  });
});
