import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import AnimatedRunFlow from "@/components/AnimatedRunFlow";
import { getRun, buildHierarchy } from "@/lib/observatory";

// M5 seq=3 — animated hierarchical run flow (source-backed, not hardcoded).
describe("hierarchical run flow (seq=3)", () => {
  const run = getRun("DW-OBS-M5-20260823-MOCK", "mock")!;
  const h = buildHierarchy(run, "mock");

  it("includes the full source-backed chain #70..#75 then #80", () => {
    expect(h.chain).toEqual(["#70", "#71", "#72", "#73", "#74", "#75", "#80"]);
  });

  it("includes every required card: root #70, gates G2/G3/G4, nodes, #80", () => {
    const ids = h.nodes.map((n) => n.id);
    expect(ids).toContain("#70");
    expect(ids).toContain("G2-DW-OBS-M3M4-20260823-R1");
    expect(ids).toContain("G3");
    expect(ids).toContain("G4-DW-OBS-M3M4-20260823-R1");
    expect(ids).toContain("#71");
    expect(ids).toContain("#72");
    expect(ids).toContain("#73");
    expect(ids).toContain("#74");
    expect(ids).toContain("#75");
    expect(ids).toContain("#80");
  });

  it("uses explicit (recorded) connectors, never infers", () => {
    // 6 chain edges + 3 gate edges = 9 explicit connectors.
    expect(h.connectors.length).toBe(9);
    expect(h.connectors.some((c) => c.from === "#75" && c.to === "#80")).toBe(true);
    expect(h.connectors.some((c) => c.from === "G2-DW-OBS-M3M4-20260823-R1" && c.to === "#71")).toBe(true);
  });

  it("the #80 card is the active correction-required node", () => {
    const issue = h.nodes.find((n) => n.id === "#80")!;
    expect(issue.kind).toBe("issue");
    expect(issue.status.toLowerCase()).toContain("correction");
  });

  it("renders all cards in the UI (no PROJECTION_UNAVAILABLE)", () => {
    const { container } = render(<AnimatedRunFlow hierarchy={h} activeId="#80" />);
    for (const id of ["#70", "#71", "#72", "#73", "#74", "#75", "#80", "G2", "G3", "G4"]) {
      expect(screen.getAllByText(new RegExp(id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))).length).toBeGreaterThan(0);
    }
    expect(container.querySelector(".runflow-active")).toBeTruthy();
    expect(screen.queryByText(/PROJECTION_UNAVAILABLE/i)).toBeNull();
  });
});
