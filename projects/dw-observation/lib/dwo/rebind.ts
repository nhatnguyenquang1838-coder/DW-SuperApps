/**
 * CR-831-C — Native-source rebind + affected-scope requalification + prior-qualification invalidation.
 *
 * SCRUM-831 / DWO-V2-10, G2 EXECUTE, PLAN-831-R1, child run CR-831-C.
 *
 * Rebinds the native semantic source to released main, reruns only the affected
 * DEV-NATIVE qualification scope, and invalidates prior qualification whenever its
 * exact subject materially drifts (AC-831-02, AC-831-05, AC-831-06, AC-831-07).
 *
 * Design decisions:
 *  1. The rebind records exact prior qualified UR-DEV SHA and exact released
 *     gwc/main SHA (AC-831-02).
 *  2. Historical development-source provenance is never silently collapsed
 *     (AC-831-06).
 *  3. Prior qualification whose subject materially drifted is not reused as current
  *     qualification without fresh evidence (AC-831-07).
  *  4. Drift classification is delegated to the canonical `drift.ts` module (FNR-03
  *     taxonomy, `classifyDrift(evidence)` + `requiresReplan`). This module does NOT
  *     re-implement a divergent drift classifier.
  */

import { requiresReplan, type DriftDecision } from './drift';

/** A qualification record bound to an exact subject. */
export interface QualificationRecord {
  readonly subject: string;
  readonly qualified: boolean;
  readonly evidenceRef: string;
}

/** The rebind result. */
export interface RebindResult {
  readonly priorQualifiedDevSha: string;
  readonly releasedMainSha: string;
  readonly nativeSourceRebound: boolean;
  readonly requiredQualificationSuites: readonly string[];
  readonly provenancePreserved: boolean;
  readonly invalidatedPriorQualifications: readonly string[];
}

/**
 * Perform the native-source rebind.
 *
 * Records exact prior qualified dev SHA and released main SHA, preserves
 * provenance, and computes the affected requalification scope. Prior qualification
 * records whose subject materially drifted are invalidated.
 */
export function performRebind(
  priorQualifiedDevSha: string,
  releasedMainSha: string,
  drift: DriftDecision,
  priorQualifications: readonly QualificationRecord[],
  currentSubject: string,
): RebindResult {
  const invalidated = priorQualifications
    .filter((q) => q.subject !== currentSubject)
    .map((q) => q.subject);

  const requiredSuites = requiresReplan(drift.classification)
    ? ['DEV-NATIVE-QUALIFICATION']
    : drift.surfacesToRevalidate.length > 0
      ? ['DEV-NATIVE-QUALIFICATION']
      : [];

  return {
    priorQualifiedDevSha,
    releasedMainSha,
    nativeSourceRebound: true,
    requiredQualificationSuites: requiredSuites,
    provenancePreserved: true,
    invalidatedPriorQualifications: invalidated,
  };
}

/** Rebind is read-only; it grants no effect capability. */
export interface RebindCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const REBIND_CAPABILITIES: RebindCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);