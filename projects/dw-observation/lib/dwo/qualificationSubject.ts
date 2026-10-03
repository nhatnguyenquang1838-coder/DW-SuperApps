/**
 * CR-830-A — Qualification subject binding.
 *
 * SCRUM-830 / DWO-V2-09, G2 EXECUTE, PLAN-830-R1, child run CR-830-A.
 *
 * Every DWO v2 qualification result MUST bind to the exact qualification
 * subject: source repo/ref/exact SHA, source profile, lifecycle profile/version,
 * reducer version, projection-contract version, comparison-contract version,
 * and the qualification record/evidence bundle. A stale or materially drifted
 * subject cannot remain QUALIFIED without fresh qualification evidence
 * (SCRUM-830 brief, "Qualification subject binding").
 *
 * Design decisions:
 *  1. The subject is a single immutable record; its digest is deterministic
 *     (JCS sorted keys) so a change to any bound field changes the digest.
 *  2. A subject is COMPLETE only when every required field is present and the
 *     exact SHA is a 40-hex lowercase string.
 *  3. A subject is CURRENT only when its exact SHA matches the live source SHA
 *     AND its contract digests match the live offered digests. Otherwise the
 *     subject is STALE and cannot remain QUALIFIED.
 */

/** The lifecycle profile identity (kernel §1.2). */
export interface LifecycleProfileIdentity {
  readonly id: string;
  readonly version: number;
}

/** The canonical Universal Run lifecycle profile. */
export const UNIVERSAL_RUN_LIFECYCLE_PROFILE_V1: LifecycleProfileIdentity = Object.freeze({
  id: 'gwc.universal-run',
  version: 1,
} as const);

/** The qualification subject — every bound field is required. */
export interface QualificationSubject {
  /** Source repository full name, e.g. nhatnguyenquang1838-coder/gwc. */
  readonly sourceRepository: string;
  /** Logical release-development ref (e.g. fix/SCRUM-781-m1-runtime-contract-convergence). */
  readonly sourceRef: string;
  /** Exact 40-hex lowercase SHA of the consumed source. */
  readonly sourceSha: string;
  /** Source profile namespace (DEV_NATIVE | COMPATIBILITY | ...). */
  readonly sourceProfile: string;
  /** Lifecycle profile identity. */
  readonly lifecycleProfile: LifecycleProfileIdentity;
  /** Reducer version (e.g. 'gwc.dwo.reducer/1'). */
  readonly reducerVersion: string;
  /** Projection-contract version (e.g. 'gwc.dwo.projection-contract-v2/2'). */
  readonly projectionContractVersion: string;
  /** Comparison-contract version (e.g. 'gwc.dwo.fnr02-comparison/1'). */
  readonly comparisonContractVersion: string;
  /** Qualification record / evidence bundle id. */
  readonly qualificationRecordRef: string;
  /** When the subject was bound (ISO timestamp). */
  readonly boundAt: string;
}

/** A subject validation result. */
export interface SubjectValidation {
  readonly complete: boolean;
  readonly current: boolean;
  readonly digest: string;
  readonly reasons: readonly string[];
}

/** True when a value is a 40-hex lowercase SHA. */
export function isExactSha(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{40}$/.test(value);
}

/** Deterministic JCS-style canonical stringify (sorted keys at every level). */
function canonicalStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalStringify).join(',')}]`;
  }
  if (value !== null && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalStringify(obj[k])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

/** Compute the deterministic subject digest (JCS sorted keys). */
export function subjectDigest(subject: QualificationSubject): string {
  return canonicalStringify(subject);
}

/**
 * Validate a qualification subject.
 *
 * COMPLETE requires every field present and a valid exact SHA. CURRENT requires
 * the subject's sourceSha to equal the live source SHA and its contract digests
 * to equal the live offered digests. Fails closed: any missing/invalid field
 * makes the subject incomplete and therefore not qualifiable.
 */
export function validateQualificationSubject(
  subject: QualificationSubject,
  live: { sourceSha: string; reducerVersion: string; projectionContractVersion: string; comparisonContractVersion: string },
): SubjectValidation {
  const reasons: string[] = [];

  if (!subject.sourceRepository) reasons.push('sourceRepository is required');
  if (!subject.sourceRef) reasons.push('sourceRef is required');
  if (!isExactSha(subject.sourceSha)) reasons.push('sourceSha must be 40-hex lowercase');
  if (!subject.sourceProfile) reasons.push('sourceProfile is required');
  if (!subject.lifecycleProfile || !subject.lifecycleProfile.id || typeof subject.lifecycleProfile.version !== 'number') {
    reasons.push('lifecycleProfile id/version is required');
  }
  if (!subject.reducerVersion) reasons.push('reducerVersion is required');
  if (!subject.projectionContractVersion) reasons.push('projectionContractVersion is required');
  if (!subject.comparisonContractVersion) reasons.push('comparisonContractVersion is required');
  if (!subject.qualificationRecordRef) reasons.push('qualificationRecordRef is required');
  if (!subject.boundAt) reasons.push('boundAt is required');

  const complete = reasons.length === 0;

  // Currency: exact SHA + contract versions must match the live offered subject.
  let current = complete;
  if (complete) {
    if (subject.sourceSha !== live.sourceSha) {
      reasons.push(`source SHA ${subject.sourceSha} != live ${live.sourceSha}`);
      current = false;
    }
    if (subject.reducerVersion !== live.reducerVersion) {
      reasons.push(`reducer version ${subject.reducerVersion} != live ${live.reducerVersion}`);
      current = false;
    }
    if (subject.projectionContractVersion !== live.projectionContractVersion) {
      reasons.push(`projection contract ${subject.projectionContractVersion} != live ${live.projectionContractVersion}`);
      current = false;
    }
    if (subject.comparisonContractVersion !== live.comparisonContractVersion) {
      reasons.push(`comparison contract ${subject.comparisonContractVersion} != live ${live.comparisonContractVersion}`);
      current = false;
    }
  }

  return { complete, current, digest: subjectDigest(subject), reasons };
}

/** The qualification subject surface is read-only; it grants no effect capability. */
export interface QualificationSubjectCapabilities {
  readonly read: true;
  readonly write: false;
  readonly grantsAuthority: false;
}

export const QUALIFICATION_SUBJECT_CAPABILITIES: QualificationSubjectCapabilities = Object.freeze({
  read: true,
  write: false,
  grantsAuthority: false,
} as const);
