import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import EvidenceInspector from "@/components/EvidenceInspector";
import { getRun, UNKNOWN } from "@/lib/observatory";

// Evidence Inspector provenance fields (G3 #3).
describe("EvidenceInspector", () => {
  const run = getRun("DW-OBS-M0-20260821-R2")!;

  it("renders source_event_id, before/after, authority_ref per event", () => {
    render(<EvidenceInspector events={run.events} anomalies={run.anomalies} unknownSentinel={UNKNOWN} />);
    expect(screen.getByText("evt_audit_run_started_0")).toBeInTheDocument();
    expect(screen.getAllByText(/before/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/after/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/authority_ref:/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/source_digest:/i).length).toBeGreaterThan(0);
  });

  it("renders evidence_refs when present", () => {
    const gwc = getRun("run_dw_obs_m0_r2")!;
    render(<EvidenceInspector events={gwc.events} anomalies={gwc.anomalies} unknownSentinel={UNKNOWN} />);
    expect(screen.getByText("gwc://runs/run_dw_obs_m0_r2/start")).toBeInTheDocument();
  });

  it("shows explicit UNKNOWN for missing evidence_refs", () => {
    render(<EvidenceInspector events={run.events} anomalies={run.anomalies} unknownSentinel={UNKNOWN} />);
    // taskcontroller run event[0] has empty evidence_refs -> UNKNOWN sentinel
    expect(screen.getAllByText(UNKNOWN).length).toBeGreaterThan(0);
  });
});
