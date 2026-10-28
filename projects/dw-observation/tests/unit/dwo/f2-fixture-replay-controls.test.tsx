/**
 * F2 — Fixture Lab replay transport controls.
 *
 * The Fixture Lab must exercise the real ReplaySession over DWO-UR-30-V1 event
 * data: progressive event arrival, reset, forward/backward, reconnect/catch-up,
 * and CURRENT <-> REPLAY mode switch. It is read-only; no effect capability.
 */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import FixtureReplayControls from "@/components/dwo/FixtureReplayControls";
import type { ProjectionEvent } from "@/lib/live";

const events: ProjectionEvent[] = [
  { run_id: "DEV-RUN-001", source_system: "DWO-FIXTURE", source_event_id: "event-1", sequence: 1, ordinal: 1, event_type: "run_started", occurred_at: "2026-09-01T00:00:00Z" },
  { run_id: "DEV-RUN-002", source_system: "DWO-FIXTURE", source_event_id: "event-2", sequence: 2, ordinal: 2, event_type: "node_started", node_id: "DEV-RUN-002", occurred_at: "2026-09-01T00:01:00Z" },
  { run_id: "DEV-RUN-003", source_system: "DWO-FIXTURE", source_event_id: "event-3", sequence: 3, ordinal: 3, event_type: "node_completed", node_id: "DEV-RUN-003", outcome: "DONE", occurred_at: "2026-09-01T00:02:00Z" },
];

describe("F2 fixture replay controls", () => {
  it("progressively appends fixture events and reset returns to an empty CURRENT stream", () => {
    render(<FixtureReplayControls runId="DEV-RUN-001" events={events} />);
    expect(screen.getByTestId("fixture-replay-mode").textContent).toBe("CURRENT");
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("0/0");

    fireEvent.click(screen.getByTestId("fixture-event-arrive"));
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("1/1");
    expect(screen.getByTestId("fixture-replay-events").textContent).toContain("event-1");

    fireEvent.click(screen.getByTestId("fixture-event-arrive"));
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("2/2");

    fireEvent.click(screen.getByTestId("fixture-replay-reset"));
    expect(screen.getByTestId("fixture-replay-mode").textContent).toBe("CURRENT");
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("0/0");
    expect(screen.getByTestId("fixture-replay-events").textContent).not.toContain("event-1");
  });

  it("supports REPLAY rewind, backward/forward stepping, and return to CURRENT tip", () => {
    render(<FixtureReplayControls runId="DEV-RUN-001" events={events} />);
    fireEvent.click(screen.getByTestId("fixture-catch-up"));
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("3/3");
    expect(screen.getByTestId("fixture-replay-mode").textContent).toBe("CURRENT");

    fireEvent.click(screen.getByTestId("fixture-mode-replay"));
    expect(screen.getByTestId("fixture-replay-mode").textContent).toBe("REPLAY");
    fireEvent.click(screen.getByTestId("fixture-replay-start"));
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("0/3");
    fireEvent.click(screen.getByTestId("fixture-replay-forward"));
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("1/3");
    fireEvent.click(screen.getByTestId("fixture-replay-back"));
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("0/3");
    fireEvent.click(screen.getByTestId("fixture-mode-current"));
    expect(screen.getByTestId("fixture-replay-mode").textContent).toBe("CURRENT");
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("3/3");
  });

  it("reconnect catch-up appends missing events and synchronizes all surfaces", () => {
    render(<FixtureReplayControls runId="DEV-RUN-001" events={events} />);
    fireEvent.click(screen.getByTestId("fixture-event-arrive"));
    fireEvent.click(screen.getByTestId("fixture-replay-back"));
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("0/1");
    fireEvent.click(screen.getByTestId("fixture-catch-up"));
    expect(screen.getByTestId("fixture-replay-mode").textContent).toBe("CURRENT");
    expect(screen.getByTestId("fixture-replay-cursor").textContent).toBe("3/3");
    expect(screen.getByTestId("fixture-replay-sync").textContent).toBe("SYNCHRONIZED");
    expect(screen.getByTestId("fixture-replay-events").textContent).toContain("event-3");
  });

  it("fails closed when there are no fixture events", () => {
    render(<FixtureReplayControls runId="DEV-RUN-020" events={[]} />);
    expect(screen.getByTestId("fixture-replay-unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("fixture-replay-unavailable").textContent).toMatch(/no fixture events/i);
  });
});
