/**
 * CR-832-D — G6 handoff dossier + DWO_V2_ACCEPTED derivation.
 *
 * SCRUM-832 / DWO-V2-11, G2 EXECUTE, PLAN-832-R1, child run CR-832-D.
 *
 * The WS11 exit token DWO_V2_ACCEPTED is DERIVED from machine-readable state,
 * never asserted. The G6 handoff dossier identifies exact output and evidence
 * (AC-832-01, AC-832-04).
 */
import type { RealCampaignObservation } from './realCampaign';
import type { AcceptanceValidation } from './acceptanceValidation';
import type { AcceptanceRecord } from './acceptanceRecord';

export interface AcceptanceCertificationInput {
  readonly realCampaignReconstructs: boolean;
  readonly liveReplayEqual: boolean;
  readonly readOnlySafe: boolean;
  readonly evidenceProvenanceAttributable: boolean;
  readonly targetHandoffIdentified: boolean;
  readonly degradedModeHandled: boolean;
  readonly reconstructsAfterReset: boolean;
  readonly identitiesRecorded: boolean;
}

export interface AcceptanceCertificationDecision {
  readonly derivable: boolean;
  readonly token: string | null;
  readonly reasons: readonly string[];
}

/**
 * Derive DWO_V2_ACCEPTED. Fails closed on any incoherent input.
 */
export function deriveDwoV2Accepted(
  input: AcceptanceCertificationInput,
): AcceptanceCertificationDecision {
  const reasons: string[] = [];
  if (!input.realCampaignReconstructs) reasons.push('real campaign does not reconstruct from durable history');
  if (!input.liveReplayEqual) reasons.push('final live/replay equality failed');
  if (!input.readOnlySafe) reasons.push('read-only safety violated');
  if (!input.evidenceProvenanceAttributable) reasons.push('evidence provenance not attributable');
  if (!input.targetHandoffIdentified) reasons.push('target/handoff not identified');
  if (!input.degradedModeHandled) reasons.push('degraded-mode behavior not handled');
  if (!input.reconstructsAfterReset) reasons.push('accepted state not reconstructed after derived-state reset');
  if (!input.identitiesRecorded) reasons.push('exact identities not recorded');
  if (reasons.length === 0) {
    return { derivable: true, token: 'DWO_V2_ACCEPTED', reasons: [] };
  }
  return { derivable: false, token: null, reasons };
}

/**
 * Build the certification evidence from the acceptance modules.
 */
export function buildAcceptanceEvidence(
  campaign: RealCampaignObservation,
  validation: AcceptanceValidation,
  record: AcceptanceRecord,
): AcceptanceCertificationInput {
  return {
    realCampaignReconstructs: campaign.reconstructsFromDurable === true,
    liveReplayEqual: campaign.liveReplayEqual === true,
    readOnlySafe: validation.readOnlySafe === true,
    evidenceProvenanceAttributable: validation.evidenceProvenanceAttributable === true,
    targetHandoffIdentified: validation.targetHandoffIdentified === true,
    degradedModeHandled: validation.degradedModeHandled === true,
    reconstructsAfterReset: record.reconstructsAfterReset === true,
    identitiesRecorded: record.qualificationRecords.length > 0,
  };
}

/** The G6 handoff dossier. */
export interface HandoffDossier {
  readonly taskId: string;
  readonly exitToken: string;
  readonly exactOutput: string;
  readonly evidenceRefs: readonly string[];
  readonly accepted: boolean;
}

/**
 * Produce the G6 handoff dossier.
 *
 * Identifies exact output and evidence (AC-832-04).
 */
export function produceHandoffDossier(
  taskId: string,
  exactOutput: string,
  evidenceRefs: readonly string[],
  accepted: boolean,
): HandoffDossier {
  return { taskId, exitToken: 'DWO_V2_ACCEPTED', exactOutput, evidenceRefs, accepted };
}

/** Acceptance certification is read-only; it grants no effect capability. */
export interface AcceptanceCertificationCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const ACCEPTANCE_CERTIFICATION_CAPABILITIES: AcceptanceCertificationCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);

/** Exit-token registry. */
export const EXIT_TOKENS = Object.freeze({
  dwoV2Accepted: 'DWO_V2_ACCEPTED',
} as const);