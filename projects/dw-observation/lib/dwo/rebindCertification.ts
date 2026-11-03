/**
 * CR-831-D — Warning guard + RELEASE_MAIN_BOUND derivation.
 *
 * SCRUM-831 / DWO-V2-10, G2 EXECUTE, PLAN-831-R1, child run CR-831-D.
 *
 * The WS10 exit token RELEASE_MAIN_BOUND is DERIVED from machine-readable state,
 * never asserted. A warning guard enforces that DWO main may only be merged once
 * the Universal release is merged (AC-831-08).
 *
 * Drift classification is delegated to the canonical `drift.ts` module. The
 * evidence builder computes each certification input from ACTUAL state — it never
 * hardcodes a tautology (fail-closed).
 */
import type { ReleaseMergeDetector } from './releaseMerge';
import type { DriftDecision } from './drift';
import type { RebindResult } from './rebind';

export interface RebindCertificationInput {
  readonly releaseMergeDetected: boolean;
  readonly driftClassified: boolean;
  readonly affectedSurfacesRecorded: boolean;
  readonly nativeSourceRebound: boolean;
  readonly requalificationPassed: boolean;
  readonly provenancePreserved: boolean;
  readonly priorQualificationInvalidatedOnDrift: boolean;
  readonly warningGuardEnforced: boolean;
}

export interface RebindCertificationDecision {
  readonly derivable: boolean;
  readonly token: string | null;
  readonly reasons: readonly string[];
}

/**
 * Derive RELEASE_MAIN_BOUND. Fails closed on any incoherent input.
 */
export function deriveReleaseMainBound(
  input: RebindCertificationInput,
): RebindCertificationDecision {
  const reasons: string[] = [];
  if (!input.releaseMergeDetected) reasons.push('release merge not detected from durable evidence');
  if (!input.driftClassified) reasons.push('drift not classified');
  if (!input.affectedSurfacesRecorded) reasons.push('affected surfaces not recorded');
  if (!input.nativeSourceRebound) reasons.push('native source not rebound');
  if (!input.requalificationPassed) reasons.push('affected requalification did not pass');
  if (!input.provenancePreserved) reasons.push('historical provenance collapsed');
  if (!input.priorQualificationInvalidatedOnDrift) reasons.push('prior qualification reused after material drift');
  if (!input.warningGuardEnforced) reasons.push('DWO main merge not gated on Universal release merge');
  if (reasons.length === 0) {
    return { derivable: true, token: 'RELEASE_MAIN_BOUND', reasons: [] };
  }
  return { derivable: false, token: null, reasons };
}

/**
 * Build the certification evidence from the rebind modules.
 *
 * Each input is computed from ACTUAL state. No tautology: a surface is recorded
 * only when the drift decision actually lists surfaces to revalidate; prior
 * qualification is invalidated only when the rebind actually invalidated records.
 */
export function buildRebindEvidence(
  detector: ReleaseMergeDetector,
  drift: DriftDecision,
  rebind: RebindResult,
  requalificationPassed: boolean,
  universalReleaseMerged: boolean,
): RebindCertificationInput {
  return {
    releaseMergeDetected: detector.state === 'MAIN_REBIND_PENDING' && detector.receipt !== null,
    driftClassified: drift.classification !== 'COMPATIBLE' || drift.surfacesToRevalidate.length > 0,
    affectedSurfacesRecorded: drift.surfacesToRevalidate.length > 0,
    nativeSourceRebound: rebind.nativeSourceRebound === true,
    requalificationPassed,
    provenancePreserved: rebind.provenancePreserved === true,
    priorQualificationInvalidatedOnDrift: rebind.invalidatedPriorQualifications.length > 0,
    warningGuardEnforced: detector.state === 'MAIN_REBIND_PENDING' && universalReleaseMerged === true,
  };
}

/**
 * The warning guard: DWO main may only be merged once the Universal release is
 * merged AND the rebind is certified (RELEASE_MAIN_BOUND derivable). Returns true
 * when the guard permits a DWO main merge.
 */
export function warningGuardAllowsDwoMainMerge(
  universalReleaseMerged: boolean,
  detector: ReleaseMergeDetector,
  certified: boolean,
): boolean {
  return universalReleaseMerged === true && detector.state === 'MAIN_REBIND_PENDING' && certified === true;
}

/** Rebind certification is read-only; it grants no effect capability. */
export interface RebindCertificationCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const REBIND_CERTIFICATION_CAPABILITIES: RebindCertificationCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);

/** Exit-token registry. */
export const EXIT_TOKENS = Object.freeze({
  releaseMainBound: 'RELEASE_MAIN_BOUND',
} as const);