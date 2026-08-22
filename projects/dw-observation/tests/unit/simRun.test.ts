import { describe, it, expect } from "vitest";
import { simRunG0G6 } from "@/fixtures/simRunG0G6";
import {
  activeGateIdAt,
  buildTimeline,
  clampCursor,
  findTask,
  selectedTaskAt,
  taskStateAt,
} from "@/lib/simRun";

const RUN = simRunG0G6;

describe("lib/simRun — pure replay engine", () => {
  it("buildTimeline flattens 7 gates x 28 tasks in order", () => {
    const tl = buildTimeline(RUN);
    expect(tl.length).toBe(28);
    expect(tl[0]).toMatchObject({ gate_id: "G0_CONTEXT", task_id: "G0-T01" });
    expect(tl[27]).toMatchObject({ gate_id: "G6_PRODUCTION_DATA", task_id: "G6-T03" });
    // strictly increasing in gate/task order
    const ids = tl.map((t) => t.task_id);
    expect(new Set(ids).size).toBe(28);
  });

  it("taskStateAt derives done/active/future from cursor", () => {
    expect(taskStateAt(RUN, "G0-T01", 0)).toBe("active");
    expect(taskStateAt(RUN, "G0-T01", 1)).toBe("done");
    expect(taskStateAt(RUN, "G6-T03", 0)).toBe("future");
    expect(taskStateAt(RUN, "G3-T02", 15)).toBe("active"); // index 15 in timeline
    expect(taskStateAt(RUN, "G3-T02", 16)).toBe("done");
  });

  it("activeGateIdAt tracks the gate of the cursor task", () => {
    expect(activeGateIdAt(RUN, 0)).toBe("G0_CONTEXT");
    expect(activeGateIdAt(RUN, 27)).toBe("G6_PRODUCTION_DATA");
    expect(activeGateIdAt(RUN, 4)).toBe("G1_ALIGNMENT"); // G1-T01
  });

  it("findTask resolves gate+task for any task_id", () => {
    const r = findTask(RUN, "G4-T02");
    expect(r?.gate.id).toBe("G4_MERGE");
    expect(r?.task.node_id).toBe("lifecycle.g4-merge-approval");
    expect(findTask(RUN, "NOPE")).toBeNull();
  });

  it("selectedTaskAt falls back to cursor task when requested invalid", () => {
    expect(selectedTaskAt(RUN, 5, undefined)).toBe("G1-T02");
    expect(selectedTaskAt(RUN, 5, "G2-T03")).toBe("G2-T03");
    expect(selectedTaskAt(RUN, 5, "MISSING")).toBe("G1-T02");
  });

  it("clampCursor keeps cursor in [0, length-1]", () => {
    expect(clampCursor(-5, 28)).toBe(0);
    expect(clampCursor(100, 28)).toBe(27);
    expect(clampCursor(10, 28)).toBe(10);
    expect(clampCursor(0, 0)).toBe(0);
  });
});
