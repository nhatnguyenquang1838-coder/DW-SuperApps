import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import ReviewPane from "@/components/ReviewPane";
import type { ProjectionEvent } from "@/lib/live";

// M4 — the review surface must show trace-back refs and mark unknown/incomplete
// history explicitly, never presenting an assumed value as a fact.

function ev(
  seq: number,
  eventType: string,
  extra: Record<string, unknown> = {}
): ProjectionEvent {
  return {
    run_id: "RUN-M4",
    source_system: "taskcontroller",
    source_event_id: `evt_${seq}`,
    sequence: seq,
    projection_ordinal: seq + 1,
    occurred_at: `2026-08-23T10:${String(seq).padStart(2, "0")}:00Z`,
    event_type: eventType,
    ...extra,
  } as ProjectionEvent;
}

const COMPLETE: ProjectionEvent[] = [
  ev(0, "run_started", { actor: "ChatGPT TaskController", occurred_at: "2026-08-23T10:00:00Z" }),
  ev(1, "gate_failed", {
    gate: "G3",
    actor: "ci",
    evidence_refs: ["ci://run/1"],
    occurred_at: "2026-08-23T10:05:00Z",
  }),
  ev(2, "gate_passed", {
    gate: "G3",
    actor: "ci",
    authority_ref: "G3-R1",
    evidence_refs: ["ci://run/2"],
    occurred_at: "2026-08-23T10:12:00Z",
  }),
  ev(3, "run_completed", {
    actor: "ChatGPT TaskController",
    occurred_at: "2026-08-23T10:15:00Z",
  }),
];

describe("ReviewPane", () => {
  it("renders the derivation version and event count", () => {
    render(<ReviewPane runId="RUN-M4" events={COMPLETE} />);
    expect(screen.getByTestId("review-reducer-version")).toHaveTextContent(
      "m4-review-intelligence/1"
    );
    expect(screen.getByTestId("review-event-count")).toHaveTextContent("4 events");
  });

  it("marks a complete history as complete", () => {
    render(<ReviewPane runId="RUN-M4" events={COMPLETE} />);
    expect(screen.getByTestId("review-complete")).toHaveTextContent("HISTORY_COMPLETE");
    expect(screen.queryByTestId("review-markers")).toBeNull();
  });

  it("shows the derived duration", () => {
    render(<ReviewPane runId="RUN-M4" events={COMPLETE} />);
    expect(screen.getByTestId("metric-duration-value")).toHaveTextContent("15m 0s");
    expect(screen.getByTestId("metric-duration-confidence")).toHaveTextContent("EXACT");
  });

  it("shows the recovery span with its measured time", () => {
    render(<ReviewPane runId="RUN-M4" events={COMPLETE} />);
    expect(screen.getByTestId("metric-recoveries-value")).toHaveTextContent(
      /gate:G3: recovered in 7m 0s/
    );
  });

  it("shows retries per target", () => {
    render(<ReviewPane runId="RUN-M4" events={COMPLETE} />);
    expect(screen.getByTestId("metric-retries-value")).toHaveTextContent(
      /gate:G3: 2 attempts/
    );
  });

  it("shows handoffs between recorded actors", () => {
    render(<ReviewPane runId="RUN-M4" events={COMPLETE} />);
    expect(screen.getByTestId("metric-handoffs-value")).toHaveTextContent(
      /ChatGPT TaskController → ci/
    );
  });

  it("renders trace-back refs including evidence and authority", () => {
    render(<ReviewPane runId="RUN-M4" events={COMPLETE} />);
    const refs = screen.getAllByTestId("metric-recoveries-trace-ref");
    expect(refs.length).toBeGreaterThanOrEqual(2);
    const text = refs.map((r) => r.textContent ?? "").join(" | ");
    expect(text).toMatch(/taskcontroller\/evt_1/);
    expect(text).toMatch(/ci:\/\/run\/2/);
    expect(text).toMatch(/authority G3-R1/);
  });

  it("marks an unterminated run as incomplete instead of implying completion", () => {
    render(<ReviewPane runId="RUN-M4" events={COMPLETE.slice(0, 2)} />);
    expect(screen.getByTestId("review-complete")).toHaveTextContent("HISTORY_INCOMPLETE");
    expect(screen.getByTestId("review-markers")).toHaveTextContent(/UNTERMINATED/);
    expect(screen.getByTestId("metric-duration-value")).toHaveTextContent(
      /not terminated/
    );
  });

  it("shows UNKNOWN rather than zero when a metric is not computable", () => {
    render(<ReviewPane runId="RUN-M4" events={[ev(0, "run_started")]} />);
    expect(screen.getByTestId("metric-wait-value")).toHaveTextContent("—");
    expect(screen.getByTestId("metric-wait-confidence")).toHaveTextContent("UNKNOWN");
    expect(screen.getByTestId("metric-retries-value")).toHaveTextContent("—");
  });

  it("reports an unrecovered failure explicitly", () => {
    render(<ReviewPane runId="RUN-M4" events={COMPLETE.slice(0, 2)} />);
    expect(screen.getByTestId("metric-recoveries-value")).toHaveTextContent(
      /NOT RECOVERED/
    );
  });

  it("surfaces anomaly counts from the reducer", () => {
    const dup = ev(1, "node_progress", { node_id: "M4", actor: "hermes" });
    render(<ReviewPane runId="RUN-M4" events={[COMPLETE[0], dup, dup]} />);
    expect(screen.getByTestId("review-anomaly-count")).toHaveTextContent("1 anomalies");
    expect(screen.getByTestId("review-markers")).toHaveTextContent(/ANOMALIES_PRESENT/);
  });

  it("states PROJECTION_UNAVAILABLE when the durable read degraded", () => {
    render(<ReviewPane runId="RUN-M4" events={[]} storeDegraded />);
    expect(screen.getByTestId("review-empty")).toHaveTextContent(
      /PROJECTION_UNAVAILABLE/
    );
  });

  it("derives nothing for an empty run", () => {
    render(<ReviewPane runId="RUN-M4" events={[]} />);
    expect(screen.getByTestId("review-empty")).toHaveTextContent(/no metrics derived/i);
  });

  it("declares itself read-only and non-authoritative", () => {
    render(<ReviewPane runId="RUN-M4" events={COMPLETE} />);
    expect(screen.getByTestId("review-note")).toHaveTextContent(/read-only/i);
    expect(screen.getByTestId("review-note")).toHaveTextContent(/creates no authority/i);
  });
});
