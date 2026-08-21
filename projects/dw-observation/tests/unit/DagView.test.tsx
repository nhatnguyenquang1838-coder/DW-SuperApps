import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import DagView from "@/components/DagView";
import { getRun } from "@/lib/observatory";

// React Flow read-only configuration (G3 #1).
describe("DagView (React Flow read-only)", () => {
  const run = getRun("run_dw_obs_m0_r2")!;

  it("renders without crashing and shows no inferred edges message", () => {
    render(<DagView gates={run.gates} nodes={run.nodes} />);
    expect(screen.getByText(/Read-only DAG/i)).toBeInTheDocument();
    expect(screen.getByText(/No edges are inferred/i)).toBeInTheDocument();
  });

  it("renders recorded gate + node labels", () => {
    render(<DagView gates={run.gates} nodes={run.nodes} />);
    // G2_EXECUTION gate and m0 node are present in the gwc durable projection.
    expect(screen.getAllByText(/G2_EXECUTION/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/m0/).length).toBeGreaterThan(0);
  });
});
