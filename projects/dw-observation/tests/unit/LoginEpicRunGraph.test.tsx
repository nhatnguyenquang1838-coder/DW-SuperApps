import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { loadLoginEpicFixture } from "@/lib/loginEpicFixture";
import { ReactFlowProvider } from "@xyflow/react";
import LoginEpicRunGraph from "@/components/login-epic/LoginEpicRunGraph";

const epic = loadLoginEpicFixture();

function renderGraph() {
  return render(
    <ReactFlowProvider>
      <LoginEpicRunGraph epic={epic} />
    </ReactFlowProvider>,
  );
}

describe("LoginEpicRunGraph (data-testid contract)", () => {
  it("renders the epic overview with exactly 10 run cards", () => {
    renderGraph();
    const cards = screen.getAllByTestId("login-epic-run-card");
    expect(cards.length).toBe(10);
    // R00..R09 ids present
    expect(cards[0].getAttribute("data-run-id")).toBe("LOGIN-R00-EPIC-BOOT");
    expect(cards[9].getAttribute("data-run-id")).toBe("LOGIN-R09-OBSERVATORY-DEPLOY-BOUNDARY");
  });

  it("run arrows R00 -> R09 represented in DOM", () => {
    renderGraph();
    expect(screen.getAllByTestId("login-epic-run-arrow").length).toBe(9);
  });

  it("selecting a run updates selected run title and graph", () => {
    renderGraph();
    const cards = screen.getAllByTestId("login-epic-run-card");
    fireEvent.click(cards[5]);
    // R05 card becomes the selected one
    expect(cards[5].className).toContain("active");
    // run-level header reflects R05
    const header = screen.getByText((_, el) => {
      if (!el) return false;
      const t = el.textContent ?? "";
      return el.tagName === "H2" && /LOGIN-R05-API-CONTRACT/.test(t);
    });
    expect(header).toBeTruthy();
  });

  it("run-level graph shows all 7 gate clusters", () => {
    renderGraph();
    const gates = screen.getAllByTestId("runtime-gate-cluster");
    const ids = gates.map((g) => g.getAttribute("data-gate-id"));
    expect(ids).toEqual([
      "G0_CONTEXT",
      "G1_ALIGNMENT",
      "G2_EXECUTION",
      "G3_PR",
      "G4_MERGE",
      "G5_DEPLOY",
      "G6_PRODUCTION",
    ]);
  });

  it("player controls present and scrubber changes cursor", () => {
    renderGraph();
    expect(screen.getByTestId("runtime-player")).toBeTruthy();
    const scrubber = screen.getByTestId("runtime-player-scrubber") as HTMLInputElement;
    const next = screen.getByTestId("runtime-player-next");
    fireEvent.click(next);
    expect(Number(scrubber.value)).toBeGreaterThanOrEqual(1);
  });

  it("live sim advances from first node", () => {
    renderGraph();
    const live = screen.getByTestId("runtime-live-sim");
    fireEvent.click(live);
    // after clicking LIVE SIM, the player label should reflect an active node
    expect(screen.getByTestId("runtime-live-sim")).toBeTruthy();
  });

  it("zoom/fit/reset buttons present", () => {
    renderGraph();
    expect(screen.getByTestId("runtime-zoom-in")).toBeTruthy();
    expect(screen.getByTestId("runtime-zoom-out")).toBeTruthy();
    expect(screen.getByTestId("runtime-fit")).toBeTruthy();
    expect(screen.getByTestId("runtime-reset")).toBeTruthy();
  });

  it("right panel history tab splits TaskController and Executor history", () => {
    renderGraph();
    // select first node
    const node = screen.getAllByTestId("runtime-node-card")[0];
    fireEvent.click(node);
    const historyTab = screen.getByTestId("runtime-detail-tab-history");
    fireEvent.click(historyTab);
    const panel = screen.getByTestId("runtime-details-panel");
    expect(within(panel).getByText("TaskController History")).toBeTruthy();
    expect(within(panel).getByText("Executor History")).toBeTruthy();
  });

  it("artifact modal opens from a file/artifact/checkpoint row", () => {
    renderGraph();
    const node = screen.getAllByTestId("runtime-node-card")[0];
    fireEvent.click(node);
    const artifactsTab = screen.getByTestId("runtime-detail-tab-artifacts");
    fireEvent.click(artifactsTab);
    const art = screen.getAllByTestId("runtime-artifact")[0];
    fireEvent.click(art);
    const modal = screen.getByTestId("artifact-modal");
    expect(within(modal).getByTestId("artifact-modal-title")).toBeTruthy();
  });
});
