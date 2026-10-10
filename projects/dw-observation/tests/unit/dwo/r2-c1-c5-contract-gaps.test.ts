/**
 * R2-A/B acceptance-hardening regression tests (Controller C1–C5).
 *
 * Each test names the contract correction it closes. A correction is only
 * closed when the test FAILS without the implementation change and PASSES
 * with it — otherwise the test is decoration, not evidence.
 *
 * Base commit for this batch: 2300e91e5a99e024d7741dcb17753da50dcccf97
 */

import { describe, expect, it } from 'vitest';

import {
  evaluateDependencySatisfactionV2,
  type DependencySpec,
} from '@/lib/dwo/dependencySatisfaction';

import {
  assertTraceabilityComplete,
  assertTraceabilityReadiness,
  buildTraceabilityChainV2,
  type DigestPinnedEvidenceRegistry,
  type EvidenceDescriptor,
} from '@/lib/dwo/traceabilityChain';

import {
  deriveV2ReducerCertified,
  deriveV2ReducerCertifiedFromChain,
  type ReducerCertificationInput,
} from '@/lib/dwo/reducerCertification';

const REV = 'rev-7';
const DIGEST = 'sha256:topology-7';

function dep(overrides: Partial<DependencySpec> = {}): DependencySpec {
  return {
    depId: 'dep-a',
    targetRunRef: 'RUN-A',
    required: true,
    reducerState: 'ACCEPTED',
    durablePosition: 1,
    durableWatermark: true,
    topologyRevision: REV,
    topologyDigest: DIGEST,
    eligibility: 'ELIGIBLE',
    ...overrides,
  };
}

function ev(ref: string, digest: string, required = true): EvidenceDescriptor {
  return { ref, digest, required };
}

describe('C1 · endpoint topology evidence must fail closed', () => {
  it('C1: topology set present + endpoint exists → endpoint check passes', () => {
    const result = evaluateDependencySatisfactionV2(
      'RUN-X',
      [dep({ targetRunRef: 'RUN-A' })],
      REV,
      DIGEST,
      { topologyNodeSet: ['RUN-A', 'RUN-B'] },
    );
    expect(result.reason).not.toBe('MISSING_ENDPOINT');
  });

  it('C1: topology set present + endpoint missing → MISSING_ENDPOINT', () => {
    const result = evaluateDependencySatisfactionV2(
      'RUN-X',
      [dep({ targetRunRef: 'RUN-GHOST' })],
      REV,
      DIGEST,
      { topologyNodeSet: ['RUN-A', 'RUN-B'] },
    );
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('MISSING_ENDPOINT');
  });

  it('C1: topology set ABSENT → fail closed, never degrade to non-empty-ref', () => {
    // The defect: a non-empty ref with no authoritative topology evidence
    // used to be accepted. Membership is unprovable, so this must not pass.
    const result = evaluateDependencySatisfactionV2('RUN-X', [dep()], REV, DIGEST, {});
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('MISSING_ENDPOINT');
  });

  it('C1: an EMPTY topology set is not authority either → fail closed', () => {
    const result = evaluateDependencySatisfactionV2('RUN-X', [dep()], REV, DIGEST, {
      topologyNodeSet: [],
    });
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('MISSING_ENDPOINT');
  });
});

describe('C2 · empty evidence must not PASS by default', () => {
  const base = {
    runId: 'RUN-1',
    projectionId: 'RUN-1',
    durablePosition: 3,
    sourceRef: 'fixture/run-1.json',
    sourceDigest: 'sha256:src-1',
    topologyRevision: REV,
    topologyDigest: DIGEST,
    reducerWatermark: 'wm-reducer-3',
    inputWatermark: 'wm-input-3',
  };

  it('C2: empty registry with NO explicit proof → UNKNOWN_UNRESOLVED', () => {
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [],
      { requiredEvidenceIds: [] },
    );
    const decision = assertTraceabilityComplete(chain);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.reason).toBe('MISSING_REQUIRED_EVIDENCE');
    expect(decision.missingRefs).toContain('evidence:no-evidence-marker');
  });

  it('C2: explicit NO_EVIDENCE_REQUIRED marker + source proof → PASS', () => {
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [],
      { requiredEvidenceIds: [], noEvidenceRequired: true },
    );
    expect(assertTraceabilityComplete(chain).status).toBe('PASS');
  });

  it('C2: malformed proof (marker set but source identity missing) → fail closed', () => {
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      '', base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [],
      { requiredEvidenceIds: [], noEvidenceRequired: true },
    );
    const decision = assertTraceabilityComplete(chain);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.missingRefs).toContain('sourceRef');
  });
});

describe('C3 · traceability readiness gates certification', () => {
  const certBase: Omit<ReducerCertificationInput, 'traceabilityDecision'> = {
    deterministic: true,
    missingFactsStayUnknown: true,
    parentCompositionIndependent: true,
    recursiveAndBlockingCorrect: true,
    fixtureConformance: true,
  };

  const chainOk = () =>
    buildTraceabilityChainV2(
      'RUN-1', 'RUN-1', 3,
      'fixture/run-1.json', 'sha256:src-1', REV, DIGEST,
      'wm-reducer-3', 'wm-input-3',
      [ev('target.json', 'sha256:target')],
      {
        requiredEvidenceIds: ['target.json'],
        entries: [{ id: 'target.json', expectedDigest: 'sha256:target' }],
      } as DigestPinnedEvidenceRegistry,
    );

  it('C3: unresolved traceability blocks the exit token', () => {
    const decision = deriveV2ReducerCertified({
      ...certBase,
      traceabilityDecision: {
        status: 'UNKNOWN_UNRESOLVED',
        reason: 'MISSING_SOURCE_REF',
        missingRefs: ['sourceRef'],
      },
    });
    expect(decision.derivable).toBe(false);
    expect(decision.token).toBeNull();
    expect(decision.reasons.join(' ')).toContain('traceability unresolved');
  });

  it('C3: proven traceability on every other criterion → token derived', () => {
    const decision = deriveV2ReducerCertified({
      ...certBase,
      traceabilityDecision: { status: 'PASS', reason: null, missingRefs: [] },
    });
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_REDUCER_CERTIFIED');
  });

  it('C3: the chain-driven path resolves traceability itself (not helper-only)', () => {
    // A real, complete chain → certification derives.
    const passDecision = deriveV2ReducerCertifiedFromChain(certBase, chainOk());
    expect(passDecision.derivable).toBe(true);
    expect(passDecision.token).toBe('V2_REDUCER_CERTIFIED');

    // A chain that fails traceability → certification must refuse, even
    // though every reducer criterion is green.
    const brokenChain = buildTraceabilityChainV2(
      'RUN-1', 'RUN-1', 3,
      '', 'sha256:src-1', REV, DIGEST,
      'wm-reducer-3', 'wm-input-3',
      [ev('target.json', 'sha256:target')],
      {
        requiredEvidenceIds: ['target.json'],
        entries: [{ id: 'target.json', expectedDigest: 'sha256:target' }],
      } as DigestPinnedEvidenceRegistry,
    );
    const blocked = deriveV2ReducerCertifiedFromChain(certBase, brokenChain);
    expect(blocked.derivable).toBe(false);
    expect(blocked.token).toBeNull();
  });

  it('C3: an id-only registry cannot prove a required evidence digest', () => {
    // Required evidence present with a digest, but the registry carries no
    // authoritative expected digest — this must NOT pass.
    const chain = buildTraceabilityChainV2(
      'RUN-1', 'RUN-1', 3,
      'fixture/run-1.json', 'sha256:src-1', REV, DIGEST,
      'wm-reducer-3', 'wm-input-3',
      [ev('target.json', 'sha256:whatever-the-caller-claimed')],
      { requiredEvidenceIds: ['target.json'] },
    );
    expect(assertTraceabilityReadiness(chain).status).toBe('UNKNOWN_UNRESOLVED');
  });
});

describe('C4 · reason classification stays exact', () => {
  it('C4: missing sourceRef → MISSING_SOURCE_REF', () => {
    const chain = buildTraceabilityChainV2(
      'RUN-1', 'RUN-1', 3, '', 'sha256:src-1', REV, DIGEST, 'wm-3', 'iw-3',
      [], { requiredEvidenceIds: [], noEvidenceRequired: true },
    );
    expect(assertTraceabilityComplete(chain).reason).toBe('MISSING_SOURCE_REF');
  });

  it('C4: missing sourceDigest → MISSING_SOURCE_DIGEST (not MISSING_SOURCE_REF)', () => {
    const chain = buildTraceabilityChainV2(
      'RUN-1', 'RUN-1', 3, 'fixture/run-1.json', '', REV, DIGEST, 'wm-3', 'iw-3',
      [], { requiredEvidenceIds: [], noEvidenceRequired: true },
    );
    const decision = assertTraceabilityComplete(chain);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.reason).toBe('MISSING_SOURCE_DIGEST');
  });

  it('C4: missing topologyRevision → MISSING_TOPOLOGY_REVISION', () => {
    const chain = buildTraceabilityChainV2(
      'RUN-1', 'RUN-1', 3, 'fixture/run-1.json', 'sha256:src-1', '', DIGEST, 'wm-3', 'iw-3',
      [], { requiredEvidenceIds: [], noEvidenceRequired: true },
    );
    expect(assertTraceabilityComplete(chain).reason).toBe('MISSING_TOPOLOGY_REVISION');
  });

  it('C4: missing topologyDigest → MISSING_TOPOLOGY_DIGEST', () => {
    const chain = buildTraceabilityChainV2(
      'RUN-1', 'RUN-1', 3, 'fixture/run-1.json', 'sha256:src-1', REV, '', 'wm-3', 'iw-3',
      [], { requiredEvidenceIds: [], noEvidenceRequired: true },
    );
    expect(assertTraceabilityComplete(chain).reason).toBe('MISSING_TOPOLOGY_DIGEST');
  });

  it('C4: missing reducerWatermark → MISSING_REDUCER_WATERMARK', () => {
    const chain = buildTraceabilityChainV2(
      'RUN-1', 'RUN-1', 3, 'fixture/run-1.json', 'sha256:src-1', REV, DIGEST, '', 'iw-3',
      [], { requiredEvidenceIds: [], noEvidenceRequired: true },
    );
    expect(assertTraceabilityComplete(chain).reason).toBe('MISSING_REDUCER_WATERMARK');
  });

  it('C4: missing inputWatermark → MISSING_INPUT_WATERMARK', () => {
    const chain = buildTraceabilityChainV2(
      'RUN-1', 'RUN-1', 3, 'fixture/run-1.json', 'sha256:src-1', REV, DIGEST, 'wm-3', '',
      [], { requiredEvidenceIds: [], noEvidenceRequired: true },
    );
    expect(assertTraceabilityComplete(chain).reason).toBe('MISSING_INPUT_WATERMARK');
  });
});

describe('C5 · required evidence needs authoritative expected digest', () => {
  const base = {
    runId: 'RUN-1',
    projectionId: 'RUN-1',
    durablePosition: 3,
    sourceRef: 'fixture/run-1.json',
    sourceDigest: 'sha256:src-1',
    topologyRevision: REV,
    topologyDigest: DIGEST,
    reducerWatermark: 'wm-3',
    inputWatermark: 'iw-3',
  };

  const mkChain = (evidence: readonly EvidenceDescriptor[], registry: unknown) =>
    buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      evidence, registry as never,
    );

  it('C5: expected digest known + actual matches → proven', () => {
    const registry: DigestPinnedEvidenceRegistry = {
      requiredEvidenceIds: ['target.json'],
      entries: [{ id: 'target.json', expectedDigest: 'sha256:correct' }],
    };
    const chain = mkChain([ev('target.json', 'sha256:correct')], registry);
    expect(assertTraceabilityComplete(chain).status).toBe('PASS');
  });

  it('C5: expected digest known + mismatch → fail closed', () => {
    const registry: DigestPinnedEvidenceRegistry = {
      requiredEvidenceIds: ['target.json'],
      entries: [{ id: 'target.json', expectedDigest: 'sha256:correct' }],
    };
    const chain = mkChain([ev('target.json', 'sha256:WRONG')], registry);
    const decision = assertTraceabilityComplete(chain);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.reason).toBe('EVIDENCE_DIGEST_MISMATCH');
  });

  it('C5: required evidence ID with NO expected-digest authority → UNKNOWN_UNRESOLVED', () => {
    const chain = mkChain([ev('target.json', 'sha256:anything')], {
      requiredEvidenceIds: ['target.json'],
    });
    const decision = assertTraceabilityComplete(chain);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.missingRefs.some((r) => r.startsWith('evidence-no-authority'))).toBe(true);
  });

  it('C5: a required ID with an EMPTY expected digest is not proof → fail closed', () => {
    const registry: DigestPinnedEvidenceRegistry = {
      requiredEvidenceIds: ['target.json'],
      entries: [{ id: 'target.json', expectedDigest: '' }],
    };
    const chain = mkChain([ev('target.json', 'sha256:correct')], registry);
    const decision = assertTraceabilityComplete(chain);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.missingRefs.some((r) => r.startsWith('evidence-empty-expected'))).toBe(true);
  });

  it('C5: supplemental evidence must not satisfy a missing required ID', () => {
    // 'extra.json' is present but not required; 'target.json' is required and absent.
    const registry: DigestPinnedEvidenceRegistry = {
      requiredEvidenceIds: ['target.json'],
      entries: [{ id: 'target.json', expectedDigest: 'sha256:correct' }],
    };
    const chain = mkChain([ev('extra.json', 'sha256:whatever', false)], registry);
    const decision = assertTraceabilityComplete(chain);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.missingRefs).toContain('required-evidence:target.json');
  });
});
