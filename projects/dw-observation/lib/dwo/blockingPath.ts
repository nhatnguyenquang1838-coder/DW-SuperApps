/**
 * CR-824-C — Dependency eligibility + blocking path + fail-closed UNKNOWN/PARTIAL.
 *
 * SCRUM-824 / DWO-V2-03, G2 EXECUTE, PLAN-824-R1, child run CR-824-C.
 *
 * Dependency eligibility and the blocking path. A Run is BLOCKED when an unmet
 * dependency or denied authority prevents progress; it is WAITING when an external
 * condition is pending. Missing facts stay UNKNOWN/PARTIAL (AC-824-03).
 *
 * Design decisions:
 *  1. BLOCKED has an explicit reason (unmet dependency, denied authority).
 *  2. WAITING is for external conditions (e.g. guest confirmations), distinct from
 *     BLOCKED.
 *  3. A missing dependency fact stays UNKNOWN/PARTIAL, never fabricated as
 *     satisfied or blocked.
 */

/** Blocking reason codes. */
export type BlockReason =
  | 'UNMET_DEPENDENCY'
  | 'AUTHORITY_DENIED'
  | 'UPSTREAM_DEPENDENCY_REVALIDATION_REQUIRED'
  | 'UNKNOWN';

/** The blocking-path evaluation for a Run. */
export interface BlockingPath {
  readonly runId: string;
  readonly status: 'BLOCKED' | 'WAITING' | 'ELIGIBLE' | 'UNKNOWN';
  readonly reason: BlockReason | null;
  readonly blockedBy: readonly string[];
}

/**
 * Evaluate a Run's blocking path.
 *
 * - If a dependency is unmet (not ACCEPTED), the Run is BLOCKED with reason
 *   UNMET_DEPENDENCY.
 * - If authority is DENIED, the Run is BLOCKED with reason AUTHORITY_DENIED.
 * - If an upstream dependency requires revalidation, the Run is BLOCKED with
 *   reason UPSTREAM_DEPENDENCY_REVALIDATION_REQUIRED.
 * - If a dependency's state is UNKNOWN, the Run's blocking status is UNKNOWN
 *   (fail-closed, never fabricated).
 * - Otherwise the Run is ELIGIBLE.
 */
export function evaluateBlockingPath(
  runId: string,
  deps: readonly { depId: string; state: string; revalidationRequired?: boolean }[],
  authorityState: string | 'UNKNOWN',
): BlockingPath {
  const blockedBy: string[] = [];
  for (const dep of deps) {
    if (dep.state === 'UNKNOWN') {
      return { runId, status: 'UNKNOWN', reason: 'UNKNOWN', blockedBy: [dep.depId] };
    }
    if (dep.revalidationRequired) {
      blockedBy.push(dep.depId);
      return { runId, status: 'BLOCKED', reason: 'UPSTREAM_DEPENDENCY_REVALIDATION_REQUIRED', blockedBy };
    }
    if (dep.state !== 'ACCEPTED') {
      blockedBy.push(dep.depId);
      return { runId, status: 'BLOCKED', reason: 'UNMET_DEPENDENCY', blockedBy };
    }
  }
  if (authorityState === 'DENIED') {
    return { runId, status: 'BLOCKED', reason: 'AUTHORITY_DENIED', blockedBy: [] };
  }
  if (authorityState === 'UNKNOWN') {
    return { runId, status: 'UNKNOWN', reason: 'UNKNOWN', blockedBy: [] };
  }
  return { runId, status: 'ELIGIBLE', reason: null, blockedBy: [] };
}

/** Blocking path is read-only; it grants no effect capability. */
export interface BlockingPathCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const BLOCKING_PATH_CAPABILITIES: BlockingPathCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
