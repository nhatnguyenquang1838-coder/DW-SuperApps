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
 *
 * R2-D: authority consumption via the verified authority vocabulary.
 * Authority is DERIVED from evidence, not inferred. GRANTED only when source/scope/time
 * evidence is proven; everything else is not granted.
 */

import { deriveAuthorityState, AUTHORITY_STATES, type AuthorityDecision, type AuthorityEvidence, type AuthorityState, type AuthorityReason } from './authorityVocabulary';

/** Blocking reason codes. */
export type BlockReason =
  | 'UNMET_DEPENDENCY'
  | 'AUTHORITY_DENIED'
  | 'UPSTREAM_DEPENDENCY_REVALIDATION_REQUIRED'
  | 'EXTERNAL_CONDITION_PENDING'
  | 'UNKNOWN';

/** The blocking-path evaluation for a Run. */
export interface BlockingPath {
  readonly runId: string;
  readonly status: 'BLOCKED' | 'WAITING' | 'ELIGIBLE' | 'UNKNOWN';
  readonly reason: BlockReason | null;
  readonly blockedBy: readonly string[];
  /** R2-D: authority state provenance — the decision state that gated this path. */
  readonly authorityState: AuthorityState;
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
 * - If an EXTERNAL condition is pending (waitingFor non-empty), the Run is
 *   WAITING with reason EXTERNAL_CONDITION_PENDING — distinct from BLOCKED.
 * - Otherwise the Run is ELIGIBLE.
 */
export function evaluateBlockingPath(
  runId: string,
  deps: readonly { depId: string; state: string; revalidationRequired?: boolean }[],
  authorityState: string | 'UNKNOWN',
  waitingFor: readonly string[] = [],
): BlockingPath {
  // Fail-closed: reject authority states outside the closed vocabulary.
  if (!AUTHORITY_STATES.includes(authorityState as AuthorityState)) {
    return { runId, status: 'UNKNOWN', reason: 'UNKNOWN', blockedBy: [], authorityState: 'UNKNOWN' as AuthorityState };
  }
  return evaluateBlockingPathWithDecision(runId, { state: authorityState as AuthorityState, granted: authorityState === 'GRANTED', reason: authorityState as AuthorityReason }, deps, waitingFor);
}

/**
 * Evaluate a Run's blocking path from raw dependency/authority state.
 * Legacy API — delegates to the decision-based path for consistent fail-closed semantics.
 */
export function evaluateBlockingPathLegacy(
  runId: string,
  deps: readonly { depId: string; state: string; revalidationRequired?: boolean }[],
  authorityState: string | 'UNKNOWN',
  waitingFor: readonly string[] = [],
): BlockingPath {
  // Fail-closed: reject authority states outside the closed vocabulary.
  if (!AUTHORITY_STATES.includes(authorityState as AuthorityState)) {
    return { runId, status: 'UNKNOWN', reason: 'UNKNOWN', blockedBy: [], authorityState: 'UNKNOWN' as AuthorityState };
  }
  return evaluateBlockingPathWithDecision(runId, { state: authorityState as AuthorityState, granted: authorityState === 'GRANTED', reason: authorityState as AuthorityReason }, deps, waitingFor);
}

/**
 * Evaluate a Run's blocking path from an explicit authority decision.
 *
 * Semantics:
 *  - GRANTED / NOT_REQUIRED → proceed to dependency checks only.
 *  - PENDING → WAITING (external decision outstanding).
 *  - DENIED / EXPIRED / REVOKED → BLOCKED with AUTHORITY_DENIED.
 *  - UNKNOWN / malformed / unavailable required decision → UNKNOWN (fail closed).
 */
export function evaluateBlockingPathWithDecision(
  runId: string,
  authority: AuthorityDecision,
  deps: readonly { depId: string; state: string; revalidationRequired?: boolean }[],
  waitingFor: readonly string[] = [],
): BlockingPath {
  const blockedBy: string[] = [];
  for (const dep of deps) {
    if (dep.state === 'UNKNOWN') {
      return { runId, status: 'UNKNOWN', reason: 'UNKNOWN', blockedBy: [dep.depId], authorityState: authority.state };
    }
    if (dep.revalidationRequired) {
      blockedBy.push(dep.depId);
      return { runId, status: 'BLOCKED', reason: 'UPSTREAM_DEPENDENCY_REVALIDATION_REQUIRED', blockedBy, authorityState: authority.state };
    }
    if (dep.state !== 'ACCEPTED') {
      blockedBy.push(dep.depId);
      return { runId, status: 'BLOCKED', reason: 'UNMET_DEPENDENCY', blockedBy, authorityState: authority.state };
    }
  }
  if (authority.state === 'GRANTED' && !authority.granted) {
    return { runId, status: 'UNKNOWN', reason: 'UNKNOWN', blockedBy: [], authorityState: 'UNKNOWN' as AuthorityState };
  }

  switch (authority.state as string) {
    case 'UNKNOWN':
      return { runId, status: 'UNKNOWN', reason: 'UNKNOWN', blockedBy: [], authorityState: authority.state };
    case 'DENIED':
    case 'EXPIRED':
    case 'REVOKED':
      return { runId, status: 'BLOCKED', reason: 'AUTHORITY_DENIED', blockedBy: [], authorityState: authority.state };
    case 'PENDING':
      return { runId, status: 'WAITING', reason: 'EXTERNAL_CONDITION_PENDING', blockedBy: [], authorityState: authority.state };
    case 'NOT_REQUIRED':
    case 'GRANTED':
      if (waitingFor.length > 0) {
        return { runId, status: 'WAITING', reason: 'EXTERNAL_CONDITION_PENDING', blockedBy: waitingFor, authorityState: authority.state };
      }
      return { runId, status: 'ELIGIBLE', reason: null, blockedBy: [], authorityState: authority.state };
    default:
      return { runId, status: 'UNKNOWN', reason: 'UNKNOWN', blockedBy: [], authorityState: authority.state };
  }
}

/**
 * Reconcile a Run's gateState with its blocking status (F2).
 *
 * The kernel gate-state enum includes BLOCKED and WAITING. This folds the blocking
 * path back into the run's authoritative gateState so a BLOCKED/WAITING run never
 * carries gateState ACTIVE. Returns the reconciled gateState.
 */
export function reconcileGateState(
  currentGateState: string | null,
  blocking: BlockingPath,
): string | null {
  if (blocking.status === 'BLOCKED') return 'BLOCKED';
  if (blocking.status === 'WAITING') return 'WAITING';
  if (blocking.status === 'UNKNOWN') return currentGateState ?? 'UNKNOWN';
  return currentGateState;
}

/**
 * R2-D: evaluate the blocking path from explicit authority evidence.
 *
 * Derives the authority decision first, then delegates to the
 * decision-based path so the evidence→decision→gate chain is one
 * auditable line rather than two independent derivations.
 */
export function evaluateBlockingPathWithAuthority(
  runId: string,
  authorityEvidence: AuthorityEvidence | null | undefined,
  now: string | 'UNKNOWN',
  deps: readonly { depId: string; state: string; revalidationRequired?: boolean }[],
  waitingFor: readonly string[] = [],
): BlockingPath {
  const authority = deriveAuthorityState(authorityEvidence, now);
  return evaluateBlockingPathWithDecision(runId, authority, deps, waitingFor);
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
