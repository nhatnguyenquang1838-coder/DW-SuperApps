import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import RunStatusAxes from "@/components/dwo/RunStatusAxes";
import {
  parseQualificationProjection,
  unknownQualificationProjection,
} from "@/lib/dwo/qualificationProjection";

const digest = `sha256:${"d".repeat(64)}`;

function projection(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "dwo.qualification-projection/1",
    run_id: "DWO-UI-1",
    status: "QUALIFIED",
    subject_digest: digest,
    current_subject_digest: digest,
    receipt_subject_digest: digest,
    receipt_id: `receipt:${"e".repeat(64)}`,
    graph_version: "dwo.langgraph-qualification/1",
    source_repository: "owner/gwc",
    source_sha: "a".repeat(40),
    durable_position: "projection_ordinal=8",
    evidence_refs: ["evidence://replay/1"],
    authority_granted: false,
    projection_events_mutated: false,
    reason_code: "MATCHED_IMMUTABLE_RECEIPT",
    ...overrides,
  };
}

describe("qualification projection parser", () => {
  it("accepts a receipt only when it matches the current source subject", () => {
    const result = parseQualificationProjection(projection());
    expect(result.status).toBe("QUALIFIED");
    expect(result.subjectDigest).toBe(digest);
    expect(result.sourceSha).toBe("a".repeat(40));
    expect(result.durablePosition).toBe("projection_ordinal=8");
    expect(result.authorityGranted).toBe(false);
  });

  it("marks a passing receipt for a different subject as DRIFTED", () => {
    const result = parseQualificationProjection(
      projection({ current_subject_digest: `sha256:${"f".repeat(64)}` }),
    );
    expect(result.status).toBe("DRIFTED");
  });

  it("fails closed on malformed or effectful projection payloads", () => {
    expect(parseQualificationProjection({ status: "QUALIFIED" }).status).toBe("UNKNOWN");
    expect(parseQualificationProjection(projection({ authority_granted: true })).status).toBe("UNKNOWN");
    expect(parseQualificationProjection(projection({ projection_events_mutated: true })).status).toBe("UNKNOWN");
  });

  it("provides explicit UNKNOWN when no read service is configured", () => {
    const result = unknownQualificationProjection("DWO-UI-1");
    expect(result.status).toBe("UNKNOWN");
    expect(result.reasonCode).toBe("QUALIFICATION_READ_UNCONFIGURED");
  });
});

describe("independent run status axes", () => {
  it("LIVE projection sync does not imply semantic qualification", () => {
    render(
      <RunStatusAxes
        projectionSync="LIVE"
        view="CURRENT"
        qualification={unknownQualificationProjection("DWO-UI-1")}
      />,
    );
    expect(screen.getByTestId("axis-projection-sync")).toHaveTextContent("LIVE");
    expect(screen.getByTestId("axis-view")).toHaveTextContent("CURRENT");
    expect(screen.getByTestId("axis-qualification")).toHaveTextContent("UNKNOWN");
    expect(screen.queryByText("QUALIFIED")).not.toBeInTheDocument();
  });

  it("replay view remains independent from a matching qualification receipt", () => {
    render(
      <RunStatusAxes
        projectionSync="DEGRADED"
        view="REPLAY"
        qualification={parseQualificationProjection(projection())}
      />,
    );
    expect(screen.getByTestId("axis-projection-sync")).toHaveTextContent("DEGRADED");
    expect(screen.getByTestId("axis-view")).toHaveTextContent("REPLAY");
    expect(screen.getByTestId("axis-qualification")).toHaveTextContent("QUALIFIED");
    expect(screen.getByText(/does not grant execution authority/i)).toBeInTheDocument();
  });
});
