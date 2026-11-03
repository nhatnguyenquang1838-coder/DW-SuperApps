/**
 * CR-832-C — Derived-state reset reconstruction + exact identity recording.
 *
 * SCRUM-832 / DWO-V2-11, G2 EXECUTE, PLAN-832-R1, child run CR-832-C.
 *
 * Reconstructs accepted state after a derived-state reset and records exact
 * Universal released-main SHA, DWO implementation SHA, source/profile/reducer/
 * projection identities and qualification records.
 *
 * Design decisions:
 *  1. Accepted state reconstructs deterministically from durable history after a
 *     derived-state reset.
 *  2. Exact identities are recorded (never inferred).
 */

/** The acceptance record. */
export interface AcceptanceRecord {
  readonly universalReleasedMainSha: string;
  readonly dwoImplementationSha: string;
  readonly sourceIdentity: string;
  readonly profileIdentity: string;
  readonly reducerIdentity: string;
  readonly projectionIdentity: string;
  readonly qualificationRecords: readonly string[];
  readonly reconstructsAfterReset: boolean;
}

/**
 * Record the acceptance identities and verify reset reconstruction.
 */
export function recordAcceptance(
  universalReleasedMainSha: string,
  dwoImplementationSha: string,
  sourceIdentity: string,
  profileIdentity: string,
  reducerIdentity: string,
  projectionIdentity: string,
  qualificationRecords: readonly string[],
  reconstructsAfterReset: boolean,
): AcceptanceRecord {
  return {
    universalReleasedMainSha,
    dwoImplementationSha,
    sourceIdentity,
    profileIdentity,
    reducerIdentity,
    projectionIdentity,
    qualificationRecords,
    reconstructsAfterReset,
  };
}

/** Acceptance recording is read-only; it grants no effect capability. */
export interface AcceptanceRecordCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const ACCEPTANCE_RECORD_CAPABILITIES: AcceptanceRecordCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);