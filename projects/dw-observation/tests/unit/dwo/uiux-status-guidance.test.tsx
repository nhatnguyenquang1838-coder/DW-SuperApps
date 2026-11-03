import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import RunStatusAxes from "@/components/dwo/RunStatusAxes";
import WorkspaceHeader from "@/components/dwo/WorkspaceHeader";
import NextFlowPanel from "@/components/dwo/NextFlowPanel";
import { parseQualificationProjection, unknownQualificationProjection } from "@/lib/dwo/qualificationProjection";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

const digest = `sha256:${"d".repeat(64)}`;
const sourceSha = "a".repeat(40);

function qualifiedProjection() {
  return parseQualificationProjection({
    schema_version: "dwo.qualification-projection/1",
    run_id: "DWO-UX-1",
    status: "QUALIFIED",
    subject_digest: digest,
    current_subject_digest: digest,
    receipt_subject_digest: digest,
    receipt_id: `receipt:${"e".repeat(64)}`,
    graph_version: "dwo.langgraph-qualification/1",
    source_repository: "owner/gwc",
    source_sha: sourceSha,
    durable_position: "projection_ordinal=8",
    evidence_refs: ["evidence://replay/1"],
    authority_granted: false,
    projection_events_mutated: false,
    reason_code: "MATCHED_IMMUTABLE_RECEIPT",
  });
}

function model(overrides: Partial<UnifiedRunWorkspaceModel> = {}): UnifiedRunWorkspaceModel {
  return {
    runId: "DWO-UX-1",
    taskRef: null,
    mode: "SIMULATED",
    status: "ACTIVE",
    hierarchy: null,
    nodes: [],
    edges: [],
    orderedSteps: [],
    currentSequence: null,
    canonicalHistoryAvailable: false,
    projectionStatus: "FIXTURE_PROJECTION",
    projectionSyncState: "GAP",
    sourceDigest: null,
    ...overrides,
  };
}

describe("DWO status guidance", () => {
  it("separates truth-axis labels and values while preserving exact provenance identity", () => {
    render(
      <RunStatusAxes
        projectionSync="GAP"
        view="CURRENT"
        qualification={qualifiedProjection()}
      />,
    );

    expect(screen.getByTestId("axis-projection-sync")).toHaveAttribute("data-value", "GAP");
    expect(within(screen.getByTestId("axis-projection-sync")).getByText("Projection Sync")).toBeVisible();
    expect(within(screen.getByTestId("axis-projection-sync")).getByText("GAP")).toBeVisible();
    expect(screen.getByTestId("axis-projection-sync")).toHaveTextContent(/No synchronized projection is available for this view/i);
    expect(screen.getByTestId("axis-view")).toHaveTextContent(/CURRENT/i);
    expect(screen.getByTestId("axis-view")).toHaveTextContent(/Showing the current available view/i);
    expect(screen.getByTestId("axis-qualification")).toHaveTextContent("QUALIFIED");
    expect(screen.getByTestId("axis-qualification")).toHaveTextContent(sourceSha);
    expect(screen.getByTestId("axis-qualification")).toHaveTextContent("owner/gwc");
    expect(screen.getByTestId("axis-qualification")).toHaveTextContent("projection_ordinal=8");
  });

  it("explains DRIFTED and UNKNOWN without presenting either as a pass", () => {
    const drifted = parseQualificationProjection({
      schema_version: "dwo.qualification-projection/1",
      run_id: "DWO-UX-1",
      status: "QUALIFIED",
      subject_digest: digest,
      current_subject_digest: `sha256:${"f".repeat(64)}`,
      receipt_subject_digest: digest,
      receipt_id: `receipt:${"e".repeat(64)}`,
      graph_version: "dwo.langgraph-qualification/1",
      source_repository: "owner/gwc",
      source_sha: sourceSha,
      durable_position: "projection_ordinal=8",
      evidence_refs: [],
      authority_granted: false,
      projection_events_mutated: false,
      reason_code: "MATCHED_IMMUTABLE_RECEIPT",
    });
    const { rerender } = render(<RunStatusAxes projectionSync="DEGRADED" view="REPLAY" qualification={drifted} />);
    expect(screen.getByTestId("axis-qualification")).toHaveTextContent("DRIFTED");
    expect(screen.getByTestId("axis-qualification")).toHaveTextContent(/receipt does not match the current subject/i);
    expect(screen.getByTestId("axis-projection-sync")).toHaveTextContent(/Projection data is delayed or incomplete/i);
    expect(screen.getByTestId("axis-view")).toHaveTextContent(/Showing a selected historical view/i);

    rerender(<RunStatusAxes projectionSync="GAP" view="CURRENT" qualification={unknownQualificationProjection("DWO-UX-1")} />);
    expect(screen.getByTestId("axis-qualification")).toHaveTextContent("UNKNOWN");
    expect(screen.getByTestId("axis-qualification")).toHaveTextContent(/not enough evidence to determine qualification/i);
  });

  it("labels workspace modes accessibly and describes fixture/current semantics without changing values", () => {
    render(
      <WorkspaceHeader
        model={model()}
        mode="SIMULATED"
        onModeChange={() => {}}
      />,
    );
    const select = screen.getByRole("combobox", { name: "Workspace mode" });
    expect(select).toHaveValue("SIMULATED");
    expect(within(select).getByRole("option", { name: "Current fixture state" })).toHaveAttribute("value", "LIVE");
    expect(within(select).getByRole("option", { name: "Replay" })).toHaveAttribute("value", "REPLAY");
    expect(within(select).getByRole("option", { name: "Fixture preview" })).toHaveAttribute("value", "SIMULATED");
    expect(screen.getByTestId("workspace-mode-explanation")).toHaveTextContent(/read-only fixture preview/i);
    expect(screen.getByTestId("workspace-mode-explanation")).toHaveTextContent(/grant production authority/i);
  });

  it("explains unavailable next-flow source data and discloses only actual projection evidence", () => {
    render(<NextFlowPanel model={model()} />);
    expect(screen.getByTestId("nextflow-panel")).toHaveAttribute("data-status", "UNKNOWN");
    expect(screen.getByTestId("nextflow-node")).toHaveTextContent("UNKNOWN");
    expect(screen.getByTestId("nextflow-reason")).toHaveTextContent("No current sequence — source data unavailable");
    expect(screen.getByText(/sequence data is not available in this source/i)).toBeVisible();
    expect(screen.queryByText(/deliberately|retry|next run/i)).not.toBeInTheDocument();
    const disclosure = screen.getByRole("group", { name: "Source details" });
    fireEvent.click(within(disclosure).getByText("Source details"));
    expect(within(disclosure).getByText("FIXTURE")).toBeVisible();
    expect(within(disclosure).getByText("FIXTURE_PROJECTION")).toBeVisible();
    expect(within(disclosure).getByText("No current sequence supplied")).toBeVisible();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
