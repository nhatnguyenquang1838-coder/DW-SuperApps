import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import FixtureLabClient from "@/app/dev/fixtures/FixtureLabClient";
import type { ProjectionEvent } from "@/lib/live";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";
import { FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";

vi.mock("@/components/dwo/RuntimeGraphCanvas", () => ({
  default: ({ model, cursor, selection }: { model: UnifiedRunWorkspaceModel; cursor: number; selection: { id: string } }) => (
    <div data-testid="graph-projection" data-cursor={cursor} data-selected={selection.id}>
      {model.nodes.map((node) => <span key={node.id} data-testid={`graph-node-${node.id}`}>{node.gateState ?? "UNKNOWN"}</span>)}
    </div>
  ),
}));

const node = (id: string, title: string) => ({
  id, gateId: "G2_EXECUTION", gateState: null, title, family: "runtime", nodeType: null,
  authorityBoundary: null, sourceStatus: "ACTIVE", maturity: null, declaredGates: [],
  purpose: title, fileReads: [], fileWrites: [], artifacts: [], runbook: [],
  taskControllerHistory: [], executorHistory: [], checkpoints: [],
});
const model = (runId: string): UnifiedRunWorkspaceModel => ({
  runId, taskRef: null, mode: "SIMULATED", status: "UNKNOWN", hierarchy: null,
  nodes: [node(runId, `${runId} first`)],
  edges: [], orderedSteps: [], currentSequence: null, canonicalHistoryAvailable: true,
  projectionStatus: "UNKNOWN", sourceDigest: null,
});
const event = (runId: string, id: string, ordinal: number, runState: string, gateState: string): ProjectionEvent => ({
  event_id: id, run_id: runId, ordinal, run_state: runState, gate: "G2_EXECUTION",
  source_system: "DWO-FIXTURE", source_event_id: id,
  gate_state: gateState, source_profile: "KNOWN", sync_state: "LIVE",
  semantic_qualification: "UNKNOWN", authority_state: "UNKNOWN", anomaly_count: 0,
});
const renderLab = () => render(<FixtureLabClient
  catalog={[{ ...FIXTURE_CATALOG[0], id: "R1" }, { ...FIXTURE_CATALOG[0], id: "R2" }]}
  models={{ R1: model("R1"), R2: model("R2") }}
  replayEvents={{ R1: [event("R1", "r1e1", 1, "OPEN", "ACTIVE"), event("R1", "r1e2", 2, "ACCEPTED", "PASSED")], R2: [event("R2", "r2e1", 1, "FAILED", "FAILED")] }}
  defaultId="R1"
/>);

describe("shared fixture replay drives the workspace", () => {
  it("keeps the workspace at the shared session prefix, including the empty prefix", () => {
    renderLab();
    expect(screen.getByTestId("workspace-header")).toHaveTextContent("UNKNOWN");
    expect(screen.getByTestId("graph-projection")).toHaveAttribute("data-cursor", "0");
    expect(screen.getByTestId("node-inspector")).toHaveTextContent("No node selected");
    fireEvent.click(screen.getByTestId("fixture-event-arrive"));
    expect(screen.getByTestId("workspace-header")).toHaveTextContent("OPEN");
    expect(screen.getByTestId("graph-node-R1")).toHaveTextContent("ACTIVE");
    expect(screen.getByTestId("graph-projection")).toHaveAttribute("data-cursor", "1");
    fireEvent.click(screen.getByTestId("fixture-event-arrive"));
    expect(screen.getByTestId("workspace-header")).toHaveTextContent("ACCEPTED");
    expect(screen.getByTestId("graph-node-R1")).toHaveTextContent("PASSED");
    fireEvent.click(screen.getByTestId("fixture-replay-start"));
    expect(screen.getByTestId("workspace-header")).toHaveTextContent("UNKNOWN");
    expect(screen.getByTestId("graph-node-R1")).toHaveTextContent("UNKNOWN");
  });

  it("resets cursor, selection, and mode when the scenario changes", () => {
    renderLab();
    fireEvent.click(screen.getByTestId("fixture-event-arrive"));
    fireEvent.click(screen.getByTestId("fixture-mode-replay"));
    fireEvent.click(screen.getByRole("button", { name: /R2/ }));
    expect(screen.getByTestId("fixture-replay-cursor")).toHaveTextContent("0/0");
    expect(screen.getByTestId("fixture-replay-mode")).toHaveTextContent("CURRENT");
    expect(screen.getByTestId("graph-projection")).toHaveAttribute("data-cursor", "0");
    expect(screen.getByTestId("node-inspector")).toHaveTextContent("No node selected");
    expect(screen.getByTestId("workspace-header")).toHaveTextContent("UNKNOWN");
  });
});
