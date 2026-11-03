import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import NodeInspector from "@/components/dwo/NodeInspector";
import { materializeFixtureScenario } from "@/lib/dwo/materializeFixtureScenario";
import { projectFixtureReplayView } from "@/lib/dwo/fixtureReplayView";
import { FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";

describe("R5 raw evidence and typed inspector tabs", () => {
  it("shows raw full-tip receipts only in Raw and clears them on an unbound replay prefix", () => {
    const model = materializeFixtureScenario(FIXTURE_CATALOG.find((entry) => entry.id === "DEV-RUN-025")!);
    const fullTip = model.nodes.find((entry) => entry.id === "DEV-RUN-025")!;
    expect(fullTip.rawEvidence?.length).toBeGreaterThan(0);
    const onTabChange = (tab: "overview" | "files" | "artifacts" | "runbook" | "history" | "checkpoints" | "raw") => {
      rerender(<NodeInspector node={fullTip} activeTab={tab} onTabChange={onTabChange} />);
    };
    const { rerender } = render(<NodeInspector node={fullTip} activeTab="runbook" onTabChange={onTabChange} />);
    expect(screen.getByText(/Runbook unavailable.*canonical source contract/)).toBeVisible();
    onTabChange("history");
    expect(screen.getByText(/TaskController history unavailable/)).toBeVisible();
    expect(screen.getByText(/Executor history unavailable/)).toBeVisible();
    onTabChange("checkpoints");
    expect(screen.getByText(/Checkpoints unavailable.*canonical source contract/)).toBeVisible();
    onTabChange("raw");
    const raw = screen.getByText(/ExecutionReceipt/).textContent ?? "";
    expect(raw).toContain("NO_CANONICAL_SOURCE_CONTRACT");

    const prefix = projectFixtureReplayView(model, []);
    expect(prefix.canonicalHistoryAvailable).toBe(false);
    expect(prefix.nodes[0]?.rawEvidence).toEqual([]);
    expect(prefix.nodes[0]?.artifacts).toEqual([]);
    rerender(<NodeInspector node={prefix.nodes[0]} activeTab="raw" onTabChange={onTabChange} />);
    expect(screen.queryByText(/ExecutionReceipt/)).toBeNull();
    for (const activeTab of ["runbook", "history", "checkpoints"] as const) {
      rerender(<NodeInspector node={prefix.nodes[0]} activeTab={activeTab} onTabChange={onTabChange} />);
      expect(screen.queryByText(/ExecutionReceipt/)).toBeNull();
      expect(document.querySelector(`[data-pane="${activeTab}"]`)?.textContent).toMatch(/unavailable/i);
    }
  });

  it("leaves every unsupported semantic source tab explicitly empty", () => {
    const model = materializeFixtureScenario(FIXTURE_CATALOG.find((entry) => entry.id === "DEV-RUN-025")!);
    const node = model.nodes[0]!;
    const { rerender } = render(<NodeInspector node={node} activeTab="runbook" onTabChange={() => undefined} />);
    expect(screen.getByText(/Runbook unavailable.*canonical source contract/)).toBeVisible();
    rerender(<NodeInspector node={node} activeTab="history" onTabChange={() => undefined} />);
    expect(screen.getByText(/TaskController history unavailable/)).toBeVisible();
    expect(screen.getByText(/Executor history unavailable/)).toBeVisible();
    rerender(<NodeInspector node={node} activeTab="checkpoints" onTabChange={() => undefined} />);
    expect(screen.getByText(/Checkpoints unavailable.*canonical source contract/)).toBeVisible();
  });
});
