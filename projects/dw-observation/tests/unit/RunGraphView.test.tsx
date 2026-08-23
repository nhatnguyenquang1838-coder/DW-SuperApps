import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RunGraphView from "@/components/RunGraphView";
import { getRun, buildHierarchy } from "@/lib/observatory";

// M5 seq=3 (design-first, Context7 React Flow) — deterministic verification.
// Node cards mount in jsdom (HTML). Edges require measured viewport (browser),
// so edge existence is asserted on the source-backed connector contract
// (deterministic, no inference) AND proven via localhost DOM capture.
describe("RunGraphView (hierarchical graph, React Flow)", () => {
  const run = getRun("DW-OBS-M5-20260823-MOCK", "mock")!;
  const h = buildHierarchy(run, "mock");

  // Full node ids as they appear in the DOM (gates carry their full key).
  const EXPECTED_NODE_IDS = [
    "#70",
    "G2-DW-OBS-M3M4-20260823-R1",
    "#71",
    "#72",
    "#73",
    "#74",
    "G3",
    "G4-DW-OBS-M3M4-20260823-R1",
    "#75",
    "#80",
  ];

  it("renders all 10 graph node cards via data-node-id selector", () => {
    render(<RunGraphView hierarchy={h} activeId="#80" />);
    const cards = screen.getAllByTestId("runflow-node");
    expect(cards.length).toBe(EXPECTED_NODE_IDS.length);
    for (const id of EXPECTED_NODE_IDS) {
      expect(
        cards.some((n) => n.getAttribute("data-node-id") === id),
        `node ${id} should exist`
      ).toBe(true);
    }
  });

  it("active card (#80) flagged data-active=true; exactly one", () => {
    render(<RunGraphView hierarchy={h} activeId="#80" />);
    const active = screen
      .getAllByTestId("runflow-node")
      .filter((n) => n.getAttribute("data-active") === "true");
    expect(active).toHaveLength(1);
    expect(active[0].getAttribute("data-node-id")).toBe("#80");
  });

  it("graph view container carries testid for evidence capture", () => {
    render(<RunGraphView hierarchy={h} activeId="#80" />);
    expect(screen.getByTestId("run-graph-view")).toBeTruthy();
  });

  it("no PROJECTION_UNAVAILABLE in mock-mode graph DOM", () => {
    const { container } = render(<RunGraphView hierarchy={h} activeId="#80" />);
    expect(container.textContent).not.toMatch(/PROJECTION_UNAVAILABLE/i);
  });

  it("React Flow is read-only (no draggable/connectable/selectable nodes)", () => {
    const { container } = render(<RunGraphView hierarchy={h} activeId="#80" />);
    expect(container.querySelector(".react-flow")).toBeTruthy();
    expect(container.querySelector(".react-flow__node.draggable")).toBeNull();
    expect(container.querySelector(".react-flow__node.connectable")).toBeNull();
    expect(container.querySelector(".react-flow__node.selectable")).toBeNull();
  });

  it("edge contract: 9 explicit, source-backed connectors (no inference)", () => {
    // Deterministic: every required edge is recorded, none invented.
    const labels = h.connectors.map((c) => `${c.from}->${c.to}:${c.label}`);
    expect(h.connectors.length).toBe(9);
    expect(labels).toContain("#75->#80:M4 -> review issue");
    expect(labels).toContain("G2-DW-OBS-M3M4-20260823-R1->#71:G2 approves M0");
    expect(labels).toContain("G3->#74:G3 reviews M3");
    expect(labels).toContain("G4-DW-OBS-M3M4-20260823-R1->#74:G4 consumes M3");
  });

  it("edge labels exist in source-backed connector contract (rendered in-browser)", () => {
    // Edge labels (visible directional edges) render via EdgeLabelRenderer in
    // the browser; jsdom cannot measure React Flow viewport. Assert the
    // deterministic contract instead, proven by localhost DOM capture.
    expect(h.connectors.every((c) => typeof c.label === "string" && c.label.length > 0)).toBe(true);
  });
});
