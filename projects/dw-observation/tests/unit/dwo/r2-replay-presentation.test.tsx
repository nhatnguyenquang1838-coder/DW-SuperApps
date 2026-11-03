import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ReplayPane from "@/components/ReplayPane";
import type { ProjectionEvent } from "@/lib/live";

const events = [{ run_id: "R", source_system: "taskcontroller", source_event_id: "e1", sequence: 1, projection_ordinal: 1, occurred_at: "2026-01-01T00:00:00Z", event_type: "run_started" }] as ProjectionEvent[];

describe("R2 replay presentation", () => {
  it("separates labelled mode, cursor, sync and full digest; contextualizes fixture LIVE", () => {
    render(<ReplayPane runId="R" events={events} fixturePreview />);
    expect(screen.getByTestId("replay-mode")).toHaveTextContent("Current fixture tip");
    expect(screen.getByTestId("replay-cursor").closest("[aria-label]")).toHaveAttribute("aria-label", "Replay cursor");
    expect(screen.getByTestId("replay-sync").closest("[aria-label]")).toHaveAttribute("aria-label", "Replay synchronization");
    expect(screen.getByTestId("replay-digest").closest("[aria-label]")).toHaveAttribute("aria-label", "Full state digest");
    expect(screen.getByTestId("replay-digest").textContent).toMatch(/.+/);
  });

  it("keeps existing synchronized five-pane surfaces and gives controls labelled targets", () => {
    render(<ReplayPane runId="R" events={events} />);
    for (const id of ["surface-root-card", "surface-dag", "surface-timeline", "surface-evidence", "surface-inspector"]) expect(screen.getByTestId(id)).toBeInTheDocument();
    for (const id of ["replay-start", "replay-back", "replay-forward", "replay-tip", "replay-resume"]) expect(screen.getByTestId(id).getAttribute("aria-label") || screen.getByTestId(id).textContent).toBeTruthy();
  });
});
