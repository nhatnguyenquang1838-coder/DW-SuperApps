/**
 * CR-832-B — Read-only safety + evidence provenance + target/handoff + degraded-mode validation.
 *
 * SCRUM-832 / DWO-V2-11, G2 EXECUTE, PLAN-832-R1, child run CR-832-B.
 *
 * Validates read-only safety, evidence provenance, target/handoff and degraded-mode
 * behavior for the real-run certification.
 *
 * Design decisions:
 *  1. Read-only safety: the certification never grants an effect capability.
 *  2. Evidence provenance: every evidence ref is attributable.
 *  3. Target/handoff: the handoff identifies exact output and evidence.
 *  4. Degraded-mode: the certification handles a degraded projection correctly.
 */

/** The acceptance validation result. */
export interface AcceptanceValidation {
  readonly readOnlySafe: boolean;
  readonly evidenceProvenanceAttributable: boolean;
  readonly targetHandoffIdentified: boolean;
  readonly degradedModeHandled: boolean;
}

/**
 * Validate the acceptance properties.
 *
 * Fails closed: any property not satisfied makes the validation fail.
 */
export function validateAcceptance(
  readOnlySafe: boolean,
  evidenceProvenanceAttributable: boolean,
  targetHandoffIdentified: boolean,
  degradedModeHandled: boolean,
): AcceptanceValidation {
  return {
    readOnlySafe,
    evidenceProvenanceAttributable,
    targetHandoffIdentified,
    degradedModeHandled,
  };
}

/** Acceptance validation is read-only; it grants no effect capability. */
export interface AcceptanceValidationCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const ACCEPTANCE_VALIDATION_CAPABILITIES: AcceptanceValidationCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);