import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import UnifiedRunWorkspace from "@/components/dwo/UnifiedRunWorkspace";
import NodeInspector from "@/components/dwo/NodeInspector";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

const node = {
  id: "node-1", gateId: "G2_EXECUTION", title: "Collect evidence", family: "runtime", nodeType: "collector",
  authorityBoundary: "read-only", sourceStatus: "ACTIVE", maturity: "stable", declaredGates: ["G2_EXECUTION"],
  purpose: "Collect recorded evidence", fileReads: ["input.json"], fileWrites: [], artifacts: ["evidence.json"],
  runbook: [], taskControllerHistory: [], executorHistory: [], checkpoints: [], gateState: "ACTIVE",
};
const model: UnifiedRunWorkspaceModel = {
  runId: "UX-RUN", taskRef: "TASK-1", mode: "SIMULATED", status: "ACTIVE", hierarchy: null,
  nodes: [node], edges: [], orderedSteps: [{ nodeId: "node-1", sequence: 0 }], currentSequence: 0,
  canonicalHistoryAvailable: false, projectionStatus: "UNKNOWN", sourceDigest: null,
};

function renderWorkspace() {
  return render(<ReactFlowProvider><UnifiedRunWorkspace model={model} /></ReactFlowProvider>);
}

describe("DWO responsive workspace UX", () => {
  it("provides labelled collapsible hierarchy and inspector without losing selection or tab", () => {
    renderWorkspace();
    const hierarchyToggle = screen.getByRole("button", { name: "Hide hierarchy" });
    const inspectorToggle = screen.getByRole("button", { name: "Hide inspector" });
    expect(hierarchyToggle).toHaveAttribute("aria-expanded", "true");
    expect(hierarchyToggle).toHaveAttribute("aria-controls", "dwo-hierarchy-panel");
    expect(inspectorToggle).toHaveAttribute("aria-controls", "dwo-inspector-panel");
    fireEvent.click(screen.getByRole("button", { name: "Artifacts" }));
    fireEvent.click(inspectorToggle);
    expect(screen.getByTestId("node-inspector")).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Show inspector" }));
    expect(screen.getByTestId("node-inspector")).toBeVisible();
    expect(screen.getByTestId("node-inspector")).toHaveAttribute("data-state", "loaded");
    expect(screen.getByRole("button", { name: "Artifacts" })).toHaveClass("active");
    expect(screen.getByText("evidence.json")).toBeInTheDocument();
    expect(hierarchyToggle).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps follow-cursor disabled after a real viewport gesture", () => {
    renderWorkspace();
    const canvas = screen.getByTestId("runtime-graph-canvas");
    expect(canvas).toHaveAttribute("data-follow-cursor", "true");
    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 20, clientY: 20 });
    expect(canvas).toHaveAttribute("data-follow-cursor", "false");
    fireEvent.click(screen.getByTestId("player-next"));
    expect(canvas).toHaveAttribute("data-follow-cursor", "false");
  });

  it("groups overview values under state, provenance, and evidence without changing values", () => {
    render(<NodeInspector node={node} activeTab="overview" onTabChange={() => {}} />);
    const pane = screen.getByTestId("inspector-overview");
    expect(pane).toHaveTextContent("State");
    expect(pane).toHaveTextContent("Provenance");
    expect(pane).toHaveTextContent("Evidence");
    expect(pane).toHaveTextContent("ACTIVE");
    expect(pane).toHaveTextContent("read-only");
    expect(pane).toHaveTextContent("Collect recorded evidence");
  });
});
