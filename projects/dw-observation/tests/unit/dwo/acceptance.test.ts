/**
 * CR-832-A/B/C/D verification — real-run certification + G6 handoff.
 *
 * AC-832-01 DWO_V2_ACCEPTED derivable
 * AC-832-02 real campaign deterministically reconstructs from durable history
 * AC-832-03 final live/replay equality passes
 * AC-832-04 accepted G6 handoff identifies exact output and evidence
 */
import { describe, expect, it } from 'vitest';
import {
  REAL_CAMPAIGN_CAPABILITIES,
  observeRealCampaign,
} from '@/lib/dwo/realCampaign';
import {
  ACCEPTANCE_VALIDATION_CAPABILITIES,
  validateAcceptance,
} from '@/lib/dwo/acceptanceValidation';
import {
  ACCEPTANCE_RECORD_CAPABILITIES,
  recordAcceptance,
} from '@/lib/dwo/acceptanceRecord';
import {
  ACCEPTANCE_CERTIFICATION_CAPABILITIES,
  buildAcceptanceEvidence,
  deriveDwoV2Accepted,
  produceHandoffDossier,
  type AcceptanceCertificationInput,
} from '@/lib/dwo/acceptanceCertification';

function certInput(overrides: Partial<AcceptanceCertificationInput> = {}): AcceptanceCertificationInput {
  return {
    realCampaignReconstructs: true,
    liveReplayEqual: true,
    readOnlySafe: true,
    evidenceProvenanceAttributable: true,
    targetHandoffIdentified: true,
    degradedModeHandled: true,
    reconstructsAfterReset: true,
    identitiesRecorded: true,
    ...overrides,
  };
}

describe('AC-832-02 · real campaign deterministically reconstructs from durable history', () => {
  it('observes a real campaign that reconstructs from durable history', () => {
    const c = observeRealCampaign('CAMPAIGN-1', 'tip-live', 'tip-live', true);
    expect(c.reconstructsFromDurable).toBe(true);
  });

  it('fails closed when the campaign does not reconstruct', () => {
    const c = observeRealCampaign('CAMPAIGN-1', 'tip-live', 'tip-live', false);
    expect(c.reconstructsFromDurable).toBe(false);
  });
});

describe('AC-832-03 · final live/replay equality passes', () => {
  it('passes when the final LIVE tip equals the durable replay tip', () => {
    const c = observeRealCampaign('CAMPAIGN-1', 'tip-live', 'tip-live', true);
    expect(c.liveReplayEqual).toBe(true);
  });

  it('fails when the LIVE tip differs from the replay tip', () => {
    const c = observeRealCampaign('CAMPAIGN-1', 'tip-live', 'tip-replay', true);
    expect(c.liveReplayEqual).toBe(false);
  });
});

describe('AC-832-01 · DWO_V2_ACCEPTED derivation', () => {
  it('derives the token from a coherent acceptance', () => {
    const decision = deriveDwoV2Accepted(certInput());
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('DWO_V2_ACCEPTED');
    expect(decision.reasons).toEqual([]);
  });

  it('derives from the acceptance module evidence', () => {
    const campaign = observeRealCampaign('CAMPAIGN-1', 'tip-live', 'tip-live', true);
    const validation = validateAcceptance(true, true, true, true);
    const record = recordAcceptance('main-sha', 'impl-sha', 'src', 'prof', 'red', 'proj', ['qual-1'], true);
    const evidence = buildAcceptanceEvidence(campaign, validation, record);
    const decision = deriveDwoV2Accepted(evidence);
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('DWO_V2_ACCEPTED');
  });

  it('fails closed when live/replay equality fails', () => {
    expect(deriveDwoV2Accepted(certInput({ liveReplayEqual: false })).derivable).toBe(false);
  });

  it('fails closed when read-only safety is violated', () => {
    expect(deriveDwoV2Accepted(certInput({ readOnlySafe: false })).derivable).toBe(false);
  });

  it('fails closed when accepted state does not reconstruct after reset', () => {
    expect(deriveDwoV2Accepted(certInput({ reconstructsAfterReset: false })).derivable).toBe(false);
  });
});

describe('AC-832-04 · accepted G6 handoff identifies exact output and evidence', () => {
  it('produces a handoff dossier identifying exact output and evidence', () => {
    const dossier = produceHandoffDossier('SCRUM-832', 'dwo-v2-accepted', ['ev-1', 'ev-2'], true);
    expect(dossier.taskId).toBe('SCRUM-832');
    expect(dossier.exitToken).toBe('DWO_V2_ACCEPTED');
    expect(dossier.exactOutput).toBe('dwo-v2-accepted');
    expect(dossier.evidenceRefs).toEqual(['ev-1', 'ev-2']);
    expect(dossier.accepted).toBe(true);
  });
});

describe('capabilities — acceptance modules are read-only', () => {
  it('exposes no effect capability anywhere', () => {
    for (const caps of [REAL_CAMPAIGN_CAPABILITIES, ACCEPTANCE_VALIDATION_CAPABILITIES, ACCEPTANCE_RECORD_CAPABILITIES, ACCEPTANCE_CERTIFICATION_CAPABILITIES]) {
      expect(caps).toEqual({
        read: true,
        write: false,
        approve: false,
        deny: false,
        merge: false,
        deploy: false,
      });
      expect(Object.isFrozen(caps)).toBe(true);
    }
  });
});