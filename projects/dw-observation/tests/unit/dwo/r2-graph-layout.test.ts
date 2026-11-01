import { describe, expect, it } from "vitest";
import { computeRuntimeGraphLayout, type RuntimeGraphLayoutInput } from "@/components/dwo/graphLayout";

const nodes: RuntimeGraphLayoutInput[] = [
  { id: "a", gateId: "G1", title: "short", purpose: "one" },
  { id: "b", gateId: "G1", title: "long title", purpose: "A longer purpose that may wrap across the card width." },
  { id: "c", gateId: "G2", title: "third", purpose: "another purpose" },
];
const options = { direction: "LR" as const, form: "grid" as const, grouped: true };

function overlaps(a: {x:number;y:number;width:number;height:number}, b: {x:number;y:number;width:number;height:number}) {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

describe("runtime graph layout", () => {
  it("returns deterministic, non-overlapping card geometry for every option", () => {
    for (const direction of ["LR", "TD"] as const) for (const form of ["stack", "grid"] as const) for (const grouped of [true, false]) {
      const layout = computeRuntimeGraphLayout(nodes, { direction, form, grouped });
      expect(computeRuntimeGraphLayout(nodes, { direction, form, grouped })).toEqual(layout);
      const cards = Object.values(layout.nodes);
      for (let i = 0; i < cards.length; i++) for (let j = i + 1; j < cards.length; j++) expect(overlaps(cards[i], cards[j])).toBe(false);
      expect(Object.keys(layout.nodes).sort()).toEqual(["a", "b", "c"]);
      expect(layout.groups).toHaveLength(grouped ? 2 : 0);
    }
  });

  it("keeps long-content cards separated by their estimated rendered height", () => {
    const content = [
      { id: "long-a", gateId: "A", title: "A title that can wrap across the narrow card", purpose: "Evidence description ".repeat(30) },
      { id: "long-b", gateId: "A", title: "Another long title", purpose: "Another very long rendered purpose ".repeat(28) },
      { id: "long-c", gateId: "B", title: "Third long title", purpose: "Details ".repeat(55) },
    ];
    for (const direction of ["LR", "TD"] as const) for (const grouped of [true, false]) {
      const layout = computeRuntimeGraphLayout(content, { direction, form: "grid", grouped });
      const cards = Object.values(layout.nodes);
      for (let i = 0; i < cards.length; i++) for (let j = i + 1; j < cards.length; j++) expect(overlaps(cards[i], cards[j])).toBe(false);
    }
  });

  it("changes positions when direction, form, or grouping changes", () => {
    const base = computeRuntimeGraphLayout(nodes, options);
    expect(computeRuntimeGraphLayout(nodes, { ...options, direction: "TD" }).nodes).not.toEqual(base.nodes);
    expect(computeRuntimeGraphLayout(nodes, { ...options, form: "stack" }).nodes).not.toEqual(base.nodes);
    const ungrouped = computeRuntimeGraphLayout(nodes, { ...options, grouped: false });
    expect(ungrouped.nodes).not.toEqual(base.nodes);
    expect(ungrouped.groups).toEqual([]);
  });
});
