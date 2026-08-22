import { describe, it, expect } from "vitest";
import { listRuns, getRun, UNKNOWN } from "@/lib/observatory";

// Deterministic fixture rendering + explicit-unknown behaviour.
describe("observatory data layer", () => {
  it("lists both merged M0 projection runs plus the deterministic mock review run", () => {
    const runs = listRuns();
    const ids = runs.map((r) => r.runId).sort();
    expect(ids).toEqual(
      ["DW-OBS-M0-20260821-R2", "DW-OBS-M5-20260823-MOCK", "run_dw_obs_m0_r2"].sort()
    );
  });

  it("mock review run carries explicit M0-M4 metadata in mock mode (not UNKNOWN)", () => {
    const run = getRun("DW-OBS-M5-20260823-MOCK", "mock")!;
    expect(run.lane).toBe("DW Run Observatory");
    expect(run.task).toBe("SCRUM-555");
    expect(run.controller).toBe("ChatGPT TaskController");
    expect(run.executor).toBe("Hermes Mac");
    expect(run.branch).toBe("auto/SCRUM-555-dw-observation-m3m4-r1");
    expect(run.pr).toBe("#79");
    expect(run.exactHead).toBe("5e59c889039968f606d52906c5433a21a4751bd9");
    expect(run.ci).toBe("Validate workspace #32589399526 = SUCCESS");
    expect(run.risk).toBe("none (local review / explicit demo anomaly only)");
    expect(run.blocker).toBe("none");
    expect(run.now).toBe("terminal complete / M5 local review");
    expect(run.next).toBe("human review mock UI + Supabase migration proposal");
    // Mock run also carries the full node set and G2/G3/G4 gate lifecycle.
    expect(Object.keys(run.nodes).sort()).toEqual(["70", "71", "72", "73", "74", "75"]);
    expect(Object.keys(run.gates)).toEqual([
      "G2-DW-OBS-M3M4-20260823-R1",
      "G3",
      "G4-DW-OBS-M3M4-20260823-R1",
    ]);
  });

  it("mock metadata is NOT applied in real mode (fixtures stay UNKNOWN)", () => {
    const run = getRun("DW-OBS-M5-20260823-MOCK")!;
    expect(run.controller).toBe(UNKNOWN);
    expect(run.lane).toBe(UNKNOWN);
    expect(run.branch).toBe(UNKNOWN);
  });

  it("normalizes taskcontroller run events with before/after/evidence_refs", () => {
    const run = getRun("DW-OBS-M0-20260821-R2")!;
    expect(run.eventCount).toBe(7);
    const e0 = run.events[0];
    expect(e0.sourceEventId).toBe("evt_audit_run_started_0");
    expect(e0.eventType).toBe("run_started");
    expect(e0.before).toEqual({});
    expect(e0.after).toMatchObject({ jira: "SCRUM-555", node: "M0" });
    expect(Array.isArray(e0.evidenceRefs)).toBe(true);
  });

  it("normalizes gwc durable run events with actor/evidence_refs", () => {
    const run = getRun("run_dw_obs_m0_r2")!;
    expect(run.eventCount).toBe(5);
    const e0 = run.events[0];
    expect(e0.sourceEventId).toBe("evt_a1b2c3d4_run_started");
    expect(e0.actor).toContain("chatgpt");
    expect(e0.evidenceRefs).toContain("gwc://runs/run_dw_obs_m0_r2/start");
  });

  it("GWC semantic regression: payload is NOT mapped into after", () => {
    // run_gwc_durable_m0 GWC events carry `payload` but NO `after`.
    // The normalizer must NOT fabricate an after-state from payload.
    const run = getRun("run_dw_obs_m0_r2")!;
    for (const e of run.events) {
      expect(e.after).toEqual({});
      expect(JSON.stringify(e.after)).not.toContain("scope");
      expect(JSON.stringify(e.after)).not.toContain("run started");
    }
    // Sanity: before also stays empty for GWC events lacking `before`.
    expect(run.events[0].before).toEqual({});
  });

  it("renders controller/executor as explicit UNKNOWN (not inferred)", () => {
    const run = getRun("DW-OBS-M0-20260821-R2")!;
    expect(run.controller).toBe(UNKNOWN);
    expect(run.executor).toBe(UNKNOWN);
    expect(run.branch).toBe(UNKNOWN);
    expect(run.pr).toBe(UNKNOWN);
    expect(run.exactHead).toBe(UNKNOWN);
    expect(run.ci).toBe(UNKNOWN);
    expect(run.risk).toBe(UNKNOWN);
    expect(run.blocker).toBe(UNKNOWN);
    expect(run.now).toBe(UNKNOWN);
    expect(run.next).toBe(UNKNOWN);
  });

  it("renders source_digest as UNKNOWN (not invented)", () => {
    const run = getRun("DW-OBS-M0-20260821-R2")!;
    expect(run.events[0].sourceDigest).toBe(UNKNOWN);
  });

  it("returns null for unknown run id", () => {
    expect(getRun("does-not-exist")).toBeNull();
  });
});
