import { afterEach, describe, expect, it, vi } from "vitest";

import { readQualificationProjection } from "@/lib/dwo/qualificationRead";

const digest = `sha256:${"d".repeat(64)}`;
const responseBody = {
  schema_version: "dwo.qualification-projection/1",
  run_id: "DWO-READ-1",
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
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("readQualificationProjection", () => {
  it("returns UNKNOWN without making a request when the service is not configured", async () => {
    vi.stubEnv("DWO_QUALIFICATION_READ_URL", "");
    const fetcher = vi.fn();
    const result = await readQualificationProjection("DWO-READ-1", fetcher as never);
    expect(result.status).toBe("UNKNOWN");
    expect(result.reasonCode).toBe("QUALIFICATION_READ_UNCONFIGURED");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("uses a cache-bypassing GET and validates the read-only projection", async () => {
    vi.stubEnv("DWO_QUALIFICATION_READ_URL", "http://127.0.0.1:8123");
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => responseBody });
    const result = await readQualificationProjection("DWO-READ-1", fetcher as never);
    expect(fetcher).toHaveBeenCalledWith(
      "http://127.0.0.1:8123/v1/runs/DWO-READ-1/qualification",
      expect.objectContaining({ method: "GET", cache: "no-store" }),
    );
    expect(result.status).toBe("QUALIFIED");
  });

  it("fails closed on HTTP errors, invalid endpoints, network failures, and wrong run IDs", async () => {
    vi.stubEnv("DWO_QUALIFICATION_READ_URL", "ftp://127.0.0.1/qualifications");
    const blockedFetcher = vi.fn();
    const invalidUrl = await readQualificationProjection("DWO-READ-1", blockedFetcher as never);
    expect(invalidUrl.status).toBe("UNKNOWN");
    expect(blockedFetcher).not.toHaveBeenCalled();

    vi.stubEnv("DWO_QUALIFICATION_READ_URL", "http://127.0.0.1:8123");
    const failedHttp = await readQualificationProjection(
      "DWO-READ-1",
      vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }) as never,
    );
    expect(failedHttp.status).toBe("UNKNOWN");

    const networkFailure = await readQualificationProjection(
      "DWO-READ-1",
      vi.fn().mockRejectedValue(new Error("offline")) as never,
    );
    expect(networkFailure.status).toBe("UNKNOWN");

    const wrongRun = await readQualificationProjection(
      "DWO-READ-1",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...responseBody, run_id: "DWO-OTHER" }) }) as never,
    );
    expect(wrongRun.status).toBe("UNKNOWN");
    expect(wrongRun.reasonCode).toBe("QUALIFICATION_RUN_ID_MISMATCH");
  });
});
