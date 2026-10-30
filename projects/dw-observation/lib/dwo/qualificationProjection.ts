export const QUALIFICATION_PROJECTION_SCHEMA = "dwo.qualification-projection/1" as const;

export type SemanticQualificationStatus =
  | "UNKNOWN"
  | "QUALIFYING"
  | "QUALIFIED"
  | "FAILED"
  | "DRIFTED";

export type ProjectionSyncStatus = "LIVE" | "SYNCING" | "DEGRADED" | "GAP";
export type WorkspaceViewState = "CURRENT" | "REPLAY";

export interface QualificationProjection {
  readonly runId: string;
  readonly status: SemanticQualificationStatus;
  readonly subjectDigest: string | null;
  readonly receiptSubjectDigest: string | null;
  readonly receiptId: string | null;
  readonly graphVersion: string | null;
  readonly sourceRepository: string | null;
  readonly sourceSha: string | null;
  readonly durablePosition: string | null;
  readonly evidenceRefs: readonly string[];
  readonly authorityGranted: false;
  readonly projectionEventsMutated: false;
  readonly reasonCode: string;
}

const DIGEST = /^sha256:[0-9a-f]{64}$/;
const SOURCE_SHA = /^[0-9a-f]{40}$/;
const RECEIPT_ID = /^receipt:[0-9a-f]{64}$/;
const STATUSES = new Set<SemanticQualificationStatus>([
  "UNKNOWN",
  "QUALIFYING",
  "QUALIFIED",
  "FAILED",
  "DRIFTED",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonempty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0 && value === value.trim();
}

function unknownProjection(runId: string, reasonCode: string): QualificationProjection {
  return {
    runId,
    status: "UNKNOWN",
    subjectDigest: null,
    receiptSubjectDigest: null,
    receiptId: null,
    graphVersion: null,
    sourceRepository: null,
    sourceSha: null,
    durablePosition: null,
    evidenceRefs: [],
    authorityGranted: false,
    projectionEventsMutated: false,
    reasonCode,
  };
}

/**
 * Validate the read-only projection payload. A stale passing receipt is shown
 * as DRIFTED; malformed data or any claim of effect authority fails closed.
 */
export function parseQualificationProjection(value: unknown): QualificationProjection {
  if (!isRecord(value)) return unknownProjection("UNKNOWN", "INVALID_PROJECTION_SHAPE");
  const runId = nonempty(value.run_id) ? value.run_id : "UNKNOWN";
  const status = typeof value.status === "string" ? value.status : "UNKNOWN";
  if (
    value.schema_version !== QUALIFICATION_PROJECTION_SCHEMA ||
    !STATUSES.has(status as SemanticQualificationStatus) ||
    value.authority_granted !== false ||
    value.projection_events_mutated !== false
  ) {
    return unknownProjection(runId, "INVALID_PROJECTION_CONTRACT");
  }

  const subjectDigest = typeof value.current_subject_digest === "string"
    ? value.current_subject_digest
    : typeof value.subject_digest === "string"
      ? value.subject_digest
      : null;
  const declaredDigest = typeof value.subject_digest === "string" ? value.subject_digest : subjectDigest;
  const receiptSubjectDigest = typeof value.receipt_subject_digest === "string"
    ? value.receipt_subject_digest
    : null;
  const receiptId = typeof value.receipt_id === "string" ? value.receipt_id : null;
  const graphVersion = typeof value.graph_version === "string" ? value.graph_version : null;
  const sourceRepository = typeof value.source_repository === "string" ? value.source_repository : null;
  const sourceSha = typeof value.source_sha === "string" ? value.source_sha : null;
  const durablePosition = typeof value.durable_position === "string" ? value.durable_position : null;
  const evidenceRefs = Array.isArray(value.evidence_refs) && value.evidence_refs.every(nonempty)
    ? [...new Set(value.evidence_refs as string[])].sort()
    : null;
  const reasonCode = nonempty(value.reason_code) ? value.reason_code : "UNKNOWN_REASON";

  if (
    !nonempty(runId) ||
    subjectDigest === null ||
    !DIGEST.test(subjectDigest) ||
    declaredDigest === null ||
    !DIGEST.test(declaredDigest) ||
    evidenceRefs === null
  ) {
    return unknownProjection(runId, "INVALID_SUBJECT_BINDING");
  }

  let semanticStatus = status as SemanticQualificationStatus;
  if (declaredDigest !== subjectDigest || (receiptSubjectDigest !== null && !DIGEST.test(receiptSubjectDigest))) {
    semanticStatus = "DRIFTED";
  }
  if (receiptSubjectDigest !== null && receiptSubjectDigest !== subjectDigest && semanticStatus === "QUALIFIED") {
    semanticStatus = "DRIFTED";
  }

  if (semanticStatus === "QUALIFIED") {
    const repositoryParts = sourceRepository?.split("/") ?? [];
    if (
      receiptId === null ||
      !RECEIPT_ID.test(receiptId) ||
      !nonempty(graphVersion) ||
      repositoryParts.length !== 2 ||
      repositoryParts.some((part) => !part) ||
      sourceSha === null ||
      !SOURCE_SHA.test(sourceSha) ||
      !nonempty(durablePosition) ||
      evidenceRefs.length === 0 ||
      receiptSubjectDigest !== subjectDigest
    ) {
      return unknownProjection(runId, "QUALIFIED_RECEIPT_PROVENANCE_INCOMPLETE");
    }
  }

  if (sourceSha !== null && !SOURCE_SHA.test(sourceSha)) {
    return unknownProjection(runId, "INVALID_SOURCE_SHA");
  }
  if (sourceRepository !== null && sourceRepository.split("/").length !== 2) {
    return unknownProjection(runId, "INVALID_SOURCE_REPOSITORY");
  }

  return {
    runId,
    status: semanticStatus,
    subjectDigest,
    receiptSubjectDigest,
    receiptId,
    graphVersion,
    sourceRepository,
    sourceSha,
    durablePosition,
    evidenceRefs,
    authorityGranted: false,
    projectionEventsMutated: false,
    reasonCode,
  };
}

export function unknownQualificationProjection(
  runId: string,
  reasonCode = "QUALIFICATION_READ_UNCONFIGURED",
): QualificationProjection {
  return unknownProjection(runId, reasonCode);
}
