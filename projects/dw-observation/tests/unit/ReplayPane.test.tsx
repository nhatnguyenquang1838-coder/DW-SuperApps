import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import ReplayPane from "@/components/ReplayPane";
import type { ProjectionEvent } from "@/lib/live";

// M3 — replay controls drive EVERY surface from one frame, so a rewind moves the
// whole screen. These tests assert the user-visible synchronization contract.

function ev(
  seq: number,
  eventType: string,
  extra: Record<string, unknown> = {}
): ProjectionEvent {
  return {
    run_id: "RUN-M3",
    source_system: "taskcontroller",
    source_event_id: `evt_${seq}`,
    sequence: seq,
    projection_ordinal: seq + 1,
    occurred_at: `2026-08-23T10:${String(seq).padStart(2, "0")}:00Z`,
    event_type: eventType,
    ...extra,
  } as ProjectionEvent;
}

const EVENTS: ProjectionEvent[] = [
  ev(0, "run_started", { actor: "ChatGPT TaskController" }),
  ev(1, "gate_approved", { gate: "G2", authority_ref: "G2-R1", actor: "Human" }),
  ev(2, "node_started", { node_id: "M3", outcome: "active", actor: "Hermes Mac" }),
  ev(3, "gate_passed", {
    gate: "G3",
    authority_ref: "G3-R1",
    evidence_refs: ["ci://run/1"],
    actor: "ci",
  }),
  ev(4, "node_completed", { node_id: "M3", outcome: "done", actor: "Hermes Mac" }),
];

function cursorsOfEverySurface(): string[] {
  return [
    "surface-root-card",
    "surface-dag",
    "surface-timeline",
    "surface-evidence",
    "surface-inspector",
  ].map((id) => screen.getByTestId(id).getAttribute("data-cursor") ?? "missing");
}

describe("ReplayPane", () => {
  it("opens at the tip in LIVE mode", () => {
    render(<ReplayPane runId="RUN-M3" events={EVENTS} />);
    expect(screen.getByTestId("replay-mode")).toHaveTextContent("LIVE");
    expect(screen.getByTestId("replay-cursor")).toHaveTextContent("5/5");
    expect(screen.getByTestId("replay-sync")).toHaveTextContent("SYNCHRONIZED");
  });

  it("reports every surface at the same cursor", () => {
    render(<ReplayPane runId="RUN-M3" events={EVENTS} />);
    expect(new Set(cursorsOfEverySurface()).size).toBe(1);
  });

  it("rewinding to the start moves ALL surfaces together", () => {
    render(<ReplayPane runId="RUN-M3" events={EVENTS} />);
    fireEvent.click(screen.getByTestId("replay-start"));

    expect(screen.getByTestId("replay-mode")).toHaveTextContent("REPLAY");
    expect(screen.getByTestId("replay-cursor")).toHaveTextContent("0/5");
    expect(cursorsOfEverySurface()).toEqual(["0", "0", "0", "0", "0"]);
    expect(screen.getByTestId("replay-sync")).toHaveTextContent("SYNCHRONIZED");
  });

  it("hides gates, evidence and nodes that had not happened yet", () => {
    render(<ReplayPane runId="RUN-M3" events={EVENTS} />);

    // At the tip everything recorded is visible.
    expect(screen.getByTestId("dag-gate-G3")).toBeInTheDocument();
    expect(screen.getAllByTestId("evidence-ref").length).toBe(1);
    expect(screen.getByTestId("dag-node-M3")).toHaveTextContent("done");

    // Rewind to just after G2 approval: G3 and its CI evidence must disappear.
    fireEvent.click(screen.getByTestId("replay-start"));
    fireEvent.click(screen.getByTestId("replay-forward"));
    fireEvent.click(screen.getByTestId("replay-forward"));

    expect(screen.getByTestId("replay-cursor")).toHaveTextContent("2/5");
    expect(screen.getByTestId("dag-gate-G2")).toBeInTheDocument();
    expect(screen.queryByTestId("dag-gate-G3")).toBeNull();
    expect(screen.queryAllByTestId("evidence-ref").length).toBe(0);
    expect(screen.queryByTestId("dag-node-M3")).toBeNull();
  });

  it("steps forward and back to reach identical state", () => {
    render(<ReplayPane runId="RUN-M3" events={EVENTS} />);

    fireEvent.click(screen.getByTestId("replay-start"));
    fireEvent.click(screen.getByTestId("replay-forward"));
    fireEvent.click(screen.getByTestId("replay-forward"));
    const digestAtTwo = screen.getByTestId("replay-digest").textContent;

    fireEvent.click(screen.getByTestId("replay-tip"));
    fireEvent.click(screen.getByTestId("replay-start"));
    fireEvent.click(screen.getByTestId("replay-forward"));
    fireEvent.click(screen.getByTestId("replay-forward"));

    expect(screen.getByTestId("replay-digest").textContent).toBe(digestAtTwo);
  });

  it("shows pending count while rewound", () => {
    render(<ReplayPane runId="RUN-M3" events={EVENTS} />);
    fireEvent.click(screen.getByTestId("replay-start"));
    expect(screen.getByTestId("timeline-pending")).toHaveTextContent("5 pending");
    fireEvent.click(screen.getByTestId("replay-tip"));
    expect(screen.getByTestId("timeline-pending")).toHaveTextContent("0 pending");
  });

  it("resumes LIVE at the canonical tip", () => {
    render(<ReplayPane runId="RUN-M3" events={EVENTS} />);
    const tipDigest = screen.getByTestId("replay-digest").textContent;

    fireEvent.click(screen.getByTestId("replay-start"));
    expect(screen.getByTestId("replay-mode")).toHaveTextContent("REPLAY");

    fireEvent.click(screen.getByTestId("replay-resume"));
    expect(screen.getByTestId("replay-mode")).toHaveTextContent("LIVE");
    expect(screen.getByTestId("replay-cursor")).toHaveTextContent("5/5");
    expect(screen.getByTestId("replay-digest").textContent).toBe(tipDigest);
  });

  it("disables controls at the boundaries", () => {
    render(<ReplayPane runId="RUN-M3" events={EVENTS} />);
    expect(screen.getByTestId("replay-tip")).toBeDisabled();
    expect(screen.getByTestId("replay-forward")).toBeDisabled();

    fireEvent.click(screen.getByTestId("replay-start"));
    expect(screen.getByTestId("replay-start")).toBeDisabled();
    expect(screen.getByTestId("replay-back")).toBeDisabled();
    expect(screen.getByTestId("replay-forward")).toBeEnabled();
  });

  it("scrubbing jumps the whole screen to one cursor", () => {
    render(<ReplayPane runId="RUN-M3" events={EVENTS} />);
    fireEvent.change(screen.getByTestId("replay-scrub"), { target: { value: "1" } });
    expect(screen.getByTestId("replay-cursor")).toHaveTextContent("1/5");
    expect(cursorsOfEverySurface()).toEqual(["1", "1", "1", "1", "1"]);
    expect(screen.getByTestId("replay-sync")).toHaveTextContent("SYNCHRONIZED");
  });

  it("surfaces anomalies in the inspector, never hidden", () => {
    const dup = ev(1, "node_progress", { node_id: "M3", actor: "Hermes Mac" });
    render(<ReplayPane runId="RUN-M3" events={[EVENTS[0], dup, dup]} />);
    expect(screen.getByTestId("inspector-anomaly-DUPLICATE")).toBeInTheDocument();
    expect(screen.getByTestId("root-anomaly-count")).toHaveTextContent("1");
  });

  it("states PROJECTION_UNAVAILABLE when the durable read degraded", () => {
    render(<ReplayPane runId="RUN-M3" events={[]} storeDegraded />);
    expect(screen.getByTestId("replay-empty")).toHaveTextContent(
      /PROJECTION_UNAVAILABLE/
    );
  });

  it("says there is nothing to replay for an empty non-degraded run", () => {
    render(<ReplayPane runId="RUN-M3" events={[]} />);
    expect(screen.getByTestId("replay-empty")).toHaveTextContent(
      /No projection events/
    );
  });

  it("declares replay read-only in the UI", () => {
    render(<ReplayPane runId="RUN-M3" events={EVENTS} />);
    expect(screen.getByTestId("replay-note")).toHaveTextContent(/read-only/i);
    expect(screen.getByTestId("replay-note")).toHaveTextContent(/mutates nothing/i);
  });
});
