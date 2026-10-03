/**
 * CR-827-D — V2_EVIDENCE_REPLAY_READY derivation.
 *
 * SCRUM-827 / DWO-V2-06, G2 EXECUTE, PLAN-827-R1, child run CR-827-D.
 *
 * The WS exit token V2_EVIDENCE_REPLAY_READY is DERIVED from machine-readable
 * state, never asserted. It holds exactly when:
 *   1. fixture replay is deterministic (AC-827-01);
 *   2. durable replay is deterministic under the accepted ordering/rebuild
 *      contract (AC-827-02);
 *   3. recovery generations are immutable and navigable (AC-827-03);
 *   4. evidence provenance is visible without inventing missing facts (AC-827-04);
 *   5. fixture and durable replay produce deterministic comparison evidence under
 *      FNR-02 (AC-827-05).
 */

/** Inputs from which V2_EVIDENCE_REPLAY_READY is derived. */
export interface EvidenceReplayInput {
  readonly fixtureReplayDeterministic: boolean;
  readonly durableReplayDeterministic: boolean;
  readonly recoveryImmutable: boolean;
  readonly provenanceVisible: boolean;
  readonly fnr02ComparisonEvidence: boolean;
}

export interface EvidenceReplayDecision {
  readonly derivable: boolean;
  readonly token: string | null;
  readonly reasons: readonly string[];
}

/**
 * Derive V2_EVIDENCE_REPLAY_READY. Fails closed on any incoherent input.
 */
export function deriveV2EvidenceReplayReady(
  input: EvidenceReplayInput,
): EvidenceReplayDecision {
  const reasons: string[] = [];
  if (!input.fixtureReplayDeterministic) reasons.push('fixture replay is not deterministic');
  if (!input.durableReplayDeterministic) reasons.push('durable replay is not deterministic under the ordering/rebuild contract');
  if (!input.recoveryImmutable) reasons.push('recovery generations are not immutable/navigable');
  if (!input.provenanceVisible) reasons.push('evidence provenance invents missing facts');
  if (!input.fnr02ComparisonEvidence) reasons.push('fixture/durable replay comparison evidence is absent (FNR-02)');
  if (reasons.length === 0) {
    return { derivable: true, token: 'V2_EVIDENCE_REPLAY_READY', reasons: [] };
  }
  return { derivable: false, token: null, reasons };
}

/** Exit-token registry. */
export const EXIT_TOKENS = Object.freeze({
  v2EvidenceReplayReady: 'V2_EVIDENCE_REPLAY_READY',
} as const);
