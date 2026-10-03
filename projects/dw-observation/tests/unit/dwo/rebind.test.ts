/**
 * CR-831-A/B/C/D verification — Universal release main rebind.
 *
 * AC-831-01 RELEASE_MAIN_BOUND derivable
 * AC-831-02 exact prior qualified UR-DEV SHA and exact released gwc/main SHA recorded
 * AC-831-03 release/merge receipt is durable and attributable
 * AC-831-04 drift classification and affected surfaces recorded using frozen taxonomy
 * AC-831-05 all required affected qualification suites pass against the released-main subject
 * AC-831-06 no silent collapse of historical development-source provenance
 * AC-831-07 prior qualification whose subject materially drifted is not reused as current qualification without fresh evidence
 * AC-831-08 warning guard enforced — DWO main merge gated on Universal release merge
 */
import { describe, expect, it } from 'vitest';
import {
  RELEASE_MERGE_CAPABILITIES,
  detectReleaseMerge,
  initialReleaseTracking,
  isMainRebindPending,
  type ReleaseMergeReceipt,
} from '@/lib/dwo/releaseMerge';
import {
  DRIFT_CAPABILITIES,
  classifyDrift,
  requiresReplan,
  type DriftDecision,
  type DriftEvidence,
} from '@/lib/dwo/drift';
import {
  REBIND_CAPABILITIES,
  performRebind,
  type QualificationRecord,
} from '@/lib/dwo/rebind';
import {
  REBIND_CERTIFICATION_CAPABILITIES,
  buildRebindEvidence,
  deriveReleaseMainBound,
  warningGuardAllowsDwoMainMerge,
  type RebindCertificationInput,
} from '@/lib/dwo/rebindCertification';

const receipt: ReleaseMergeReceipt = {
  universalReleaseRef: 'PR-578',
  mergeReceiptRef: 'merge-receipt-578',
  releasedMainSha: '414002f92d48083e7133236346b26e3a2a047e33',
  attributable: true,
};

/** Build canonical drift evidence for a set of changed surfaces. */
function driftEvidence(changedSurfaces: DriftEvidence['changedSurfaces']): DriftEvidence {
  return {
    previousSha: '5c4e4a53fe6ceaceac05f233409c3dd20f17f4f3',
    currentSha: '414002f92d48083e7133236346b26e3a2a047e33',
    previousContractDigest: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    currentContractDigest: changedSurfaces.length > 0
      ? 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
      : 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    changedSurfaces,
    lifecycleProfileChanged: false,
  };
}

function certInput(overrides: Partial<RebindCertificationInput> = {}): RebindCertificationInput {
  return {
    releaseMergeDetected: true,
    driftClassified: true,
    affectedSurfacesRecorded: true,
    nativeSourceRebound: true,
    requalificationPassed: true,
    provenancePreserved: true,
    priorQualificationInvalidatedOnDrift: true,
    warningGuardEnforced: true,
    ...overrides,
  };
}

describe('AC-831-03 · release/merge receipt is durable and attributable', () => {
  it('enters MAIN_REBIND_PENDING only from durable attributable evidence', () => {
    const d = detectReleaseMerge(initialReleaseTracking(), receipt);
    expect(d.state).toBe('MAIN_REBIND_PENDING');
    expect(isMainRebindPending(d)).toBe(true);
  });

  it('a moving branch name alone (no receipt) is not evidence', () => {
    const d = detectReleaseMerge(initialReleaseTracking(), null);
    expect(d.state).toBe('RELEASE_DEV_TRACKING');
    expect(isMainRebindPending(d)).toBe(false);
  });

  it('a non-attributable receipt is not evidence', () => {
    const d = detectReleaseMerge(initialReleaseTracking(), { ...receipt, attributable: false });
    expect(d.state).toBe('RELEASE_DEV_TRACKING');
  });

  it('a malformed released main SHA is not durable evidence (fail-closed)', () => {
    const d = detectReleaseMerge(initialReleaseTracking(), { ...receipt, releasedMainSha: 'not-a-sha' });
    expect(d.state).toBe('RELEASE_DEV_TRACKING');
  });
});

describe('AC-831-04 · drift classification and affected surfaces recorded using frozen taxonomy', () => {
  it('classifies COMPATIBLE when no surfaces changed', () => {
    const r = classifyDrift(driftEvidence([]));
    expect(r.classification).toBe('COMPATIBLE');
    expect(requiresReplan(r.classification)).toBe(false);
  });

  it('classifies ADAPTER_CHANGE and records the surface', () => {
    const r = classifyDrift(driftEvidence(['ADAPTER']));
    expect(r.classification).toBe('ADAPTER_CHANGE');
    expect(r.surfacesToRevalidate).toContain('ADAPTER');
  });

  it('classifies REDUCER_CHANGE (revalidation, not replan)', () => {
    const r = classifyDrift(driftEvidence(['REDUCER']));
    expect(r.classification).toBe('REDUCER_CHANGE');
    expect(requiresReplan(r.classification)).toBe(false);
  });

  it('classifies BLOCKING_CONTRACT_DRIFT as replan-required', () => {
    const r = classifyDrift({ ...driftEvidence([]), lifecycleProfileChanged: true });
    expect(r.classification).toBe('BLOCKING_CONTRACT_DRIFT');
    expect(requiresReplan(r.classification)).toBe(true);
  });
});

describe('AC-831-02 · exact prior qualified UR-DEV SHA and exact released gwc/main SHA recorded', () => {
  it('records both exact SHAs on rebind', () => {
    const drift = classifyDrift(driftEvidence(['REDUCER']));
    const r = performRebind('5c4e4a53fe6ceaceac05f233409c3dd20f17f4f3', receipt.releasedMainSha, drift, [], 'SUBJ');
    expect(r.priorQualifiedDevSha).toBe('5c4e4a53fe6ceaceac05f233409c3dd20f17f4f3');
    expect(r.releasedMainSha).toBe('414002f92d48083e7133236346b26e3a2a047e33');
  });
});

describe('AC-831-05 · all required affected qualification suites pass against the released-main subject', () => {
  it('requires DEV-NATIVE-QUALIFICATION when drift is blocking', () => {
    const drift = classifyDrift({ ...driftEvidence([]), lifecycleProfileChanged: true });
    const r = performRebind('dev', 'main', drift, [], 'SUBJ');
    expect(r.requiredQualificationSuites).toContain('DEV-NATIVE-QUALIFICATION');
  });
});

describe('AC-831-06 · no silent collapse of historical development-source provenance', () => {
  it('preserves provenance on rebind', () => {
    const drift = classifyDrift(driftEvidence(['ADAPTER']));
    const r = performRebind('dev', 'main', drift, [], 'SUBJ');
    expect(r.provenancePreserved).toBe(true);
  });
});

describe('AC-831-07 · prior qualification whose subject materially drifted is not reused as current qualification without fresh evidence', () => {
  it('invalidates prior qualification bound to a different subject', () => {
    const prior: QualificationRecord[] = [
      { subject: 'OLD-SUBJ', qualified: true, evidenceRef: 'ev-1' },
    ];
    const drift = classifyDrift(driftEvidence(['REDUCER']));
    const r = performRebind('dev', 'main', drift, prior, 'NEW-SUBJ');
    expect(r.invalidatedPriorQualifications).toContain('OLD-SUBJ');
  });

  it('keeps prior qualification bound to the current subject', () => {
    const prior: QualificationRecord[] = [
      { subject: 'SUBJ', qualified: true, evidenceRef: 'ev-1' },
    ];
    const drift = classifyDrift(driftEvidence(['ADAPTER']));
    const r = performRebind('dev', 'main', drift, prior, 'SUBJ');
    expect(r.invalidatedPriorQualifications).toEqual([]);
  });
});

describe('AC-831-08 · warning guard enforced — DWO main merge gated on Universal release merge', () => {
  it('does NOT allow DWO main merge before the Universal release merge', () => {
    const d = detectReleaseMerge(initialReleaseTracking(), receipt);
    expect(warningGuardAllowsDwoMainMerge(false, d, true)).toBe(false);
  });

  it('allows DWO main merge only after the Universal release merge AND certification', () => {
    const d = detectReleaseMerge(initialReleaseTracking(), receipt);
    expect(warningGuardAllowsDwoMainMerge(true, d, true)).toBe(true);
  });

  it('does NOT allow DWO main merge when the rebind is not certified', () => {
    const d = detectReleaseMerge(initialReleaseTracking(), receipt);
    expect(warningGuardAllowsDwoMainMerge(true, d, false)).toBe(false);
  });
});

describe('AC-831-01 · RELEASE_MAIN_BOUND derivation', () => {
  it('derives the token from a coherent rebind', () => {
    const decision = deriveReleaseMainBound(certInput());
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('RELEASE_MAIN_BOUND');
    expect(decision.reasons).toEqual([]);
  });

  it('derives from the rebind module evidence', () => {
      const d = detectReleaseMerge(initialReleaseTracking(), receipt);
      const drift = classifyDrift(driftEvidence(['REDUCER']));
      const prior: QualificationRecord[] = [
        { subject: 'OLD-SUBJ', qualified: true, evidenceRef: 'ev-1' },
      ];
      const rebind = performRebind('dev', 'main', drift, prior, 'NEW-SUBJ');
            const evidence = buildRebindEvidence(d, drift, rebind, true, true);
            const decision = deriveReleaseMainBound(evidence);
            expect(decision.derivable).toBe(true);
            expect(decision.token).toBe('RELEASE_MAIN_BOUND');
    });

  it('fails closed when the release merge is not detected', () => {
      expect(deriveReleaseMainBound(certInput({ releaseMergeDetected: false })).derivable).toBe(false);
    });

    it('a BLOCKING_CONTRACT_DRIFT intentionally cannot derive RELEASE_MAIN_BOUND (replan, not rebind)', () => {
      const d = detectReleaseMerge(initialReleaseTracking(), receipt);
      const drift = classifyDrift({ ...driftEvidence([]), lifecycleProfileChanged: true });
      expect(drift.classification).toBe('BLOCKING_CONTRACT_DRIFT');
      expect(drift.surfacesToRevalidate).toEqual([]);
      const rebind = performRebind('dev', 'main', drift, [], 'SUBJ');
      const evidence = buildRebindEvidence(d, drift, rebind, true, true);
      const decision = deriveReleaseMainBound(evidence);
      expect(decision.derivable).toBe(false);
      expect(decision.reasons).toContain('affected surfaces not recorded');
    });

  it('fails closed when requalification did not pass', () => {
    expect(deriveReleaseMainBound(certInput({ requalificationPassed: false })).derivable).toBe(false);
  });

  it('fails closed when the warning guard is not enforced', () => {
    expect(deriveReleaseMainBound(certInput({ warningGuardEnforced: false })).derivable).toBe(false);
  });

  it('fails closed when affected surfaces are not recorded (no tautology)', () => {
    expect(deriveReleaseMainBound(certInput({ affectedSurfacesRecorded: false })).derivable).toBe(false);
  });

  it('fails closed when prior qualification was not invalidated on drift (no tautology)', () => {
    expect(deriveReleaseMainBound(certInput({ priorQualificationInvalidatedOnDrift: false })).derivable).toBe(false);
  });
});

describe('capabilities — rebind modules are read-only', () => {
  it('exposes no effect capability anywhere', () => {
    for (const caps of [RELEASE_MERGE_CAPABILITIES, REBIND_CAPABILITIES, REBIND_CERTIFICATION_CAPABILITIES]) {
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

  it('canonical drift module exposes observe/classify only (no effect capability)', () => {
    expect(DRIFT_CAPABILITIES).toEqual({
      observe: true,
      classify: true,
      resolveRef: false,
      rebind: false,
      writeBinding: false,
      consumeAuthority: false,
    });
    expect(Object.isFrozen(DRIFT_CAPABILITIES)).toBe(true);
  });
});