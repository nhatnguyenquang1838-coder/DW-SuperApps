/**
 * CR-831-B — Drift classification (frozen taxonomy) + affected-surface recording.
 *
 * SCRUM-831 / DWO-V2-10, G2 EXECUTE, PLAN-831-R1, child run CR-831-B.
 *
 * Compares released main to the last qualified development source and classifies
 * drift using the frozen taxonomy (AC-831-04). Records affected
 * adapter/reducer/UI/qualification surfaces.
 *
 * Design decisions:
 *  1. Drift classification uses the frozen taxonomy:
 *     COMPATIBLE | ADAPTER_CHANGE | REDUCER_CHANGE | UI_CHANGE |
 *     QUALIFICATION_CHANGE | BLOCKING_CONTRACT_DRIFT.
 *  2. Affected surfaces are recorded explicitly; a BLOCKING_CONTRACT_DRIFT
 *     requires requalification before RELEASE_MAIN_BOUND.
 */

/** Frozen drift classification taxonomy. */
export type DriftClassification =
  | 'COMPATIBLE'
  | 'ADAPTER_CHANGE'
  | 'REDUCER_CHANGE'
  | 'UI_CHANGE'
  | 'QUALIFICATION_CHANGE'
  | 'BLOCKING_CONTRACT_DRIFT';

/** Affected surface kinds. */
export type AffectedSurface = 'adapter' | 'reducer' | 'ui' | 'qualification';

/** The drift classification result. */
export interface DriftClassificationResult {
  readonly classification: DriftClassification;
  readonly affectedSurfaces: readonly AffectedSurface[];
  readonly blocking: boolean;
}

/**
 * Classify drift between the prior qualified dev source and the released main.
 *
 * The classification is derived from the set of changed surfaces. A
 * BLOCKING_CONTRACT_DRIFT is the most severe and requires requalification.
 */
export function classifyDrift(
  changedSurfaces: readonly AffectedSurface[],
): DriftClassificationResult {
  const surfaces = new Set(changedSurfaces);
  if (surfaces.has('qualification')) {
    return { classification: 'QUALIFICATION_CHANGE', affectedSurfaces: changedSurfaces, blocking: true };
  }
  if (surfaces.has('reducer')) {
    return { classification: 'REDUCER_CHANGE', affectedSurfaces: changedSurfaces, blocking: true };
  }
  if (surfaces.has('adapter')) {
    return { classification: 'ADAPTER_CHANGE', affectedSurfaces: changedSurfaces, blocking: false };
  }
  if (surfaces.has('ui')) {
    return { classification: 'UI_CHANGE', affectedSurfaces: changedSurfaces, blocking: false };
  }
  return { classification: 'COMPATIBLE', affectedSurfaces: [], blocking: false };
}

/** Assert a BLOCKING_CONTRACT_DRIFT requires requalification. */
export function requiresRequalification(result: DriftClassificationResult): boolean {
  return result.blocking === true;
}

/** Drift classification is read-only; it grants no effect capability. */
export interface DriftClassificationCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const DRIFT_CLASSIFICATION_CAPABILITIES: DriftClassificationCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);