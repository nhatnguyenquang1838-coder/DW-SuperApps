import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import DagView from "@/components/DagView";
import { getRun, DAG_EDGES } from "@/lib/observatory";

// React Flow read-only configuration (G3 #1).
describe("DagView (React Flow read-only)", () => {
  const run = getRun("run_dw_obs_m0_r2")!;

  it("renders without crashing and states edges are never inferred", () => {
    render(<DagView gates={run.gates} nodes={run.nodes} />);
    expect(screen.getByText(/Read-only DAG/i)).toBeInTheDocument();
    expect(screen.getByText(/never inferred/i)).toBeInTheDocument();
  });

  it("renders recorded gate + node labels", () => {
    render(<DagView gates={run.gates} nodes={run.nodes} />);
    // G2_EXECUTION gate and m0 node are present in the gwc durable projection.
    expect(screen.getAllByText(/G2_EXECUTION/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/m0/).length).toBeGreaterThan(0);
  });

  it("receives the 8 explicitly recorded edges for the mock run (never inferred)", () => {
    const mockRunId = "DW-OBS-M5-20260823-MOCK";
    const mockRun = getRun(mockRunId, "mock")!;
    const edges = DAG_EDGES[mockRunId] ?? [];
    // Explicit, recorded relationships only — exactly 8, none invented.
    expect(edges.length).toBe(8);
    render(<DagView gates={mockRun.gates} nodes={mockRun.nodes} edges={edges} />);
    expect(screen.getByText(/never inferred/i)).toBeInTheDocument();
    // The gwc durable fixture supplies NO edges -> explicit-none, not inferred.
    const gwcRun = getRun("run_dw_obs_m0_r2")!;
    expect(DAG_EDGES[gwcRun.runId]).toBeUndefined();
  });
});
