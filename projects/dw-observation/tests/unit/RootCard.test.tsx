import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RootCard from "@/components/RootCard";
import { getRun, UNKNOWN } from "@/lib/observatory";

// RootCard completeness + explicit-unknown behaviour (G3 #2).
describe("RootCard", () => {
  const run = getRun("DW-OBS-M0-20260821-R2")!;

  it("renders source-backed identity fields", () => {
    render(<RootCard run={run} unknownSentinel={UNKNOWN} />);
    expect(screen.getByText("DW-OBS-M0-20260821-R2")).toBeInTheDocument();
    expect(screen.getByText("taskcontroller")).toBeInTheDocument();
  });

  it("renders explicit UNKNOWN for absent fields (no inference)", () => {
    render(<RootCard run={run} unknownSentinel={UNKNOWN} />);
    // Controller/Executor/Branch/PR/Exact HEAD/CI/Risk/Blocker/Now/Next absent
    const unknowns = screen.getAllByText(UNKNOWN);
    expect(unknowns.length).toBeGreaterThanOrEqual(9);
  });

  it("renders read-only badge", () => {
    render(<RootCard run={run} unknownSentinel={UNKNOWN} />);
    expect(screen.getByText("read-only")).toBeInTheDocument();
  });
});
