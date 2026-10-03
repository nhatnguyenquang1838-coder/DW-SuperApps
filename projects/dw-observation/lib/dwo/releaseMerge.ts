/**
 * CR-831-A — Release-merge detection + MAIN_REBIND_PENDING entry from durable evidence.
 *
 * SCRUM-831 / DWO-V2-10, G2 EXECUTE, PLAN-831-R1, child run CR-831-A.
 *
 * MAIN_REBIND_PENDING is entered ONLY from durable release evidence, not
 * prose/manual inference (AC-831-03). A moving branch name alone is not evidence.
 *
 * Design decisions:
 *  1. A release merge is detected only when a durable, attributable merge receipt
 *     is present (exact released main SHA + merge identity).
 *  2. Without durable evidence, the state stays RELEASE_DEV_TRACKING.
  *  3. The released main SHA must be an exact 40-hex SHA (fail-closed, matching the
  *     codebase `isExactSha` convention in `releaseBinding.ts`).
  */

import { isExactSha } from './releaseBinding';

/** Release-train state. */
export type ReleaseTrainState = 'RELEASE_DEV_TRACKING' | 'MAIN_REBIND_PENDING' | 'RELEASE_MAIN_BOUND';

/** Durable, attributable release-merge evidence. */
export interface ReleaseMergeReceipt {
  readonly universalReleaseRef: string;
  readonly mergeReceiptRef: string;
  readonly releasedMainSha: string;
  readonly attributable: boolean;
}

/** The release-merge detector. */
export interface ReleaseMergeDetector {
  readonly state: ReleaseTrainState;
  readonly receipt: ReleaseMergeReceipt | null;
}

/** Initial state: tracking the release-development line, no merge evidence. */
export function initialReleaseTracking(): ReleaseMergeDetector {
  return { state: 'RELEASE_DEV_TRACKING', receipt: null };
}

/**
 * Detect a release merge from durable evidence.
 *
 * Enters MAIN_REBIND_PENDING only when a durable, attributable receipt is present.
 * A moving branch name alone (no receipt) is not evidence.
 */
export function detectReleaseMerge(
  detector: ReleaseMergeDetector,
  receipt: ReleaseMergeReceipt | null,
): ReleaseMergeDetector {
  if (!receipt || !receipt.attributable || !isExactSha(receipt.releasedMainSha)) {
    return { state: 'RELEASE_DEV_TRACKING', receipt: null };
  }
  return { state: 'MAIN_REBIND_PENDING', receipt };
}

/** Assert MAIN_REBIND_PENDING was entered from durable evidence. */
export function isMainRebindPending(detector: ReleaseMergeDetector): boolean {
  return detector.state === 'MAIN_REBIND_PENDING' && detector.receipt !== null;
}

/** Release-merge detection is read-only; it grants no effect capability. */
export interface ReleaseMergeCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const RELEASE_MERGE_CAPABILITIES: ReleaseMergeCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);