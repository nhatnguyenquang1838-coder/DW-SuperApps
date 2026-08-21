import { describe, it, expect } from "vitest";
import { listRuns, getRun, UNKNOWN } from "@/lib/observatory";

// Deterministic fixture rendering + explicit-unknown behaviour.
describe("observatory data layer", () => {
  it("lists both merged M0 projection runs deterministically", () => {
    const runs = listRuns();
    const ids = runs.map((r) => r.runId).sort();
    expect(ids).toEqual(["DW-OBS-M0-20260821-R2", "run_dw_obs_m0_r2"].sort());
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
