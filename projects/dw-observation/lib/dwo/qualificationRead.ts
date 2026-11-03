import {
  parseQualificationProjection,
  unknownQualificationProjection,
  type QualificationProjection,
} from "@/lib/dwo/qualificationProjection";

export type QualificationFetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

/**
 * Read a semantic-qualification projection from the internal GET-only service.
 * This module is used by server components only; it never reads checkpoints or
 * exposes a receipt-writing endpoint. Missing/unavailable service stays UNKNOWN.
 */
export async function readQualificationProjection(
  runId: string,
  fetcher: QualificationFetch = fetch,
): Promise<QualificationProjection> {
  if (!runId.trim()) return unknownQualificationProjection("UNKNOWN", "INVALID_RUN_ID");
  const configuredBase = process.env.DWO_QUALIFICATION_READ_URL?.trim();
  if (!configuredBase) {
    return unknownQualificationProjection(runId, "QUALIFICATION_READ_UNCONFIGURED");
  }

  let base: URL;
  try {
    base = new URL(configuredBase);
  } catch {
    return unknownQualificationProjection(runId, "QUALIFICATION_READ_INVALID_URL");
  }
  if (
    (base.protocol !== "http:" && base.protocol !== "https:") ||
    base.username.length > 0 ||
    base.password.length > 0 ||
    base.search.length > 0 ||
    base.hash.length > 0
  ) {
    return unknownQualificationProjection(runId, "QUALIFICATION_READ_INVALID_URL");
  }

  const basePath = base.toString().replace(/\/+$/, "");
  const endpoint = `${basePath}/v1/runs/${encodeURIComponent(runId)}/qualification`;
  try {
    const response = await fetcher(endpoint, {
      method: "GET",
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      return unknownQualificationProjection(runId, "QUALIFICATION_READ_UNAVAILABLE");
    }
    const projection = parseQualificationProjection(await response.json());
    if (projection.runId !== runId) {
      return unknownQualificationProjection(runId, "QUALIFICATION_RUN_ID_MISMATCH");
    }
    return projection;
  } catch {
    return unknownQualificationProjection(runId, "QUALIFICATION_READ_UNAVAILABLE");
  }
}
