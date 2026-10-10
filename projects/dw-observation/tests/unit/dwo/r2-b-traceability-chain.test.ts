/**
 * R2-B focused tests — traceability chain materialization.
 *
 * Covers: fully valid PASS, each independently missing required
 * field/evidence artifact, wrong source/topology/reducer identity,
 * omitted required evidence (registry), unresolved gap, and
 * read-only capability conventions.
 */
import { describe, expect, it } from 'vitest';
import {
  assertTraceabilityComplete,
  assertTraceabilityReadiness,
  buildTraceabilityChainV2,
  TRACEABILITY_CHAIN_CAPABILITIES,
  type EvidenceDescriptor,
  type RequiredEvidenceRegistry,
} from '@/lib/dwo/traceabilityChain';

function registry(overrides: Partial<{ requiredEvidenceIds: readonly string[]; noEvidenceRequired: boolean; entries: readonly { id: string; expectedDigest: string }[] }> = {}) {
  return {
    requiredEvidenceIds: overrides.requiredEvidenceIds ?? ['e1'],
    noEvidenceRequired: overrides.noEvidenceRequired ?? false,
    ...(overrides.entries ? { entries: overrides.entries } : {}),
  };
}

function chain(overrides: Partial<{
  runId: string; projectionId: string; durablePosition: number;
  sourceRef: string; sourceDigest: string; topologyRevision: string;
  topologyDigest: string; reducerWatermark: string; inputWatermark: string;
  evidence: readonly EvidenceDescriptor[];
  requiredEvidenceRegistry: RequiredEvidenceRegistry;
}> = {}) {
  return buildTraceabilityChainV2(
    overrides.runId ?? 'R1',
    overrides.projectionId ?? 'R1',
    overrides.durablePosition ?? 0,
    overrides.sourceRef ?? 'src-1',
    overrides.sourceDigest ?? 'd1',
    overrides.topologyRevision ?? 'rev-1',
    overrides.topologyDigest ?? 't1',
    overrides.reducerWatermark ?? 'rw-1',
    overrides.inputWatermark ?? 'iw-1',
    overrides.evidence ?? [{ ref: 'e1', digest: 'ed1', required: true }],
    overrides.requiredEvidenceRegistry ?? registry({
      requiredEvidenceIds: ['e1'],
      entries: [{ id: 'e1', expectedDigest: 'ed1' }],
    }),
  );
}

describe('R2-B · fully valid → PASS', () => {
  it('complete chain with all fields returns PASS', () => {
    const result = assertTraceabilityComplete(chain());
    expect(result.status).toBe('PASS');
    expect(result.reason).toBeNull();
    expect(result.missingRefs).toEqual([]);
  });

  it('multiple evidence descriptors all required and present', () => {
    const result = assertTraceabilityComplete(chain({
      evidence: [
        { ref: 'e1', digest: 'ed1', required: true },
        { ref: 'e2', digest: 'ed2', required: true },
        { ref: 'e3', digest: 'ed3', required: false },
      ],
      requiredEvidenceRegistry: registry({
        requiredEvidenceIds: ['e1', 'e2'],
        entries: [
          { id: 'e1', expectedDigest: 'ed1' },
          { id: 'e2', expectedDigest: 'ed2' },
        ],
      }),
    }));
    expect(result.status).toBe('PASS');
  });

  it('certification/readiness returns PASS for complete chain', () => {
    const result = assertTraceabilityReadiness(chain());
    expect(result.status).toBe('PASS');
  });
});

describe('R2-B · missing required field → UNKNOWN_UNRESOLVED', () => {
  it('negative durable position → UNKNOWN_UNRESOLVED', () => {
    const result = assertTraceabilityComplete(chain({ durablePosition: -1 }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('NEGATIVE_DURABLE_POSITION');
  });

  it('missing sourceRef → UNKNOWN_UNRESOLVED', () => {
    const result = assertTraceabilityComplete(chain({ sourceRef: '' }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('MISSING_SOURCE_REF');
    expect(result.missingRefs).toContain('sourceRef');
  });

  it('missing sourceDigest → UNKNOWN_UNRESOLVED', () => {
    const result = assertTraceabilityComplete(chain({ sourceDigest: '' }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.missingRefs).toContain('sourceDigest');
  });

  it('missing topologyRevision → UNKNOWN_UNRESOLVED', () => {
    const result = assertTraceabilityComplete(chain({ topologyRevision: '' }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.missingRefs).toContain('topologyRevision');
  });

  it('missing topologyDigest → UNKNOWN_UNRESOLVED', () => {
    const result = assertTraceabilityComplete(chain({ topologyDigest: '' }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.missingRefs).toContain('topologyDigest');
  });

  it('missing reducerWatermark → UNKNOWN_UNRESOLVED', () => {
    const result = assertTraceabilityComplete(chain({ reducerWatermark: '' }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.missingRefs).toContain('reducerWatermark');
  });

  it('missing inputWatermark → UNKNOWN_UNRESOLVED', () => {
    const result = assertTraceabilityComplete(chain({ inputWatermark: '' }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.missingRefs).toContain('inputWatermark');
  });

  it('missing required evidence descriptor → UNKNOWN_UNRESOLVED', () => {
    const result = assertTraceabilityComplete(chain({
      evidence: [{ ref: '', digest: '', required: true }],
      requiredEvidenceRegistry: registry({
        requiredEvidenceIds: ['e1'],
        entries: [{ id: 'e1', expectedDigest: 'ed1' }],
      }),
    }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    // The descriptor has an empty ref, so the required registry ID 'e1' is
    // also unsatisfied. OMITTED_REQUIRED_EVIDENCE outranks the empty-descriptor
    // marker in classifyMissingRefs — both violations are reported in
    // missingRefs; the reason names the more specific one.
    expect(result.reason).toBe('OMITTED_REQUIRED_EVIDENCE');
    expect(result.missingRefs).toContain('required-evidence:e1');
    expect(result.missingRefs.some((r) => r.startsWith('evidence:'))).toBe(true);
  });
});

describe('R2-B · omitted required evidence (registry) → UNKNOWN_UNRESOLVED', () => {
  it('required evidence ID missing from evidence array → UNKNOWN_UNRESOLVED', () => {
    const result = assertTraceabilityComplete(chain({
      evidence: [{ ref: 'e1', digest: 'ed1', required: true }],
      requiredEvidenceRegistry: registry({
        requiredEvidenceIds: ['e1', 'e2'],
        entries: [
          { id: 'e1', expectedDigest: 'ed1' },
          { id: 'e2', expectedDigest: 'ed2' },
        ],
      }),
    }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('OMITTED_REQUIRED_EVIDENCE');
    expect(result.missingRefs).toContain('required-evidence:e2');
  });

  it('empty evidence with non-empty registry → UNKNOWN_UNRESOLVED', () => {
    const result = assertTraceabilityComplete(chain({
      evidence: [],
      requiredEvidenceRegistry: registry({
        requiredEvidenceIds: ['e1'],
        entries: [{ id: 'e1', expectedDigest: 'ed1' }],
      }),
    }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.missingRefs).toContain('required-evidence:e1');
  });
});

describe('R2-B · identity mismatch → UNKNOWN_UNRESOLVED', () => {
  it('runId and projectionId inconsistent → IDENTITY_MISMATCH', () => {
    const result = assertTraceabilityComplete(chain({
      runId: 'RUN-A',
      projectionId: 'PROJ-B',
    }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('IDENTITY_MISMATCH');
  });
});

describe('R2-B · certification/readiness deny-closed', () => {
  it('readiness returns UNKNOWN_UNRESOLVED when required evidence is missing', () => {
    const result = assertTraceabilityReadiness(chain({
      evidence: [],
      requiredEvidenceRegistry: registry({ requiredEvidenceIds: ['e1'] }),
    }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
  });

  it('readiness returns UNKNOWN_UNRESOLVED on negative durable position', () => {
    const result = assertTraceabilityReadiness(chain({ durablePosition: -1 }));
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('NEGATIVE_DURABLE_POSITION');
  });
});

describe('R2-B · capability marker', () => {
  it('read-only, no effect affordance', () => {
    expect(TRACEABILITY_CHAIN_CAPABILITIES).toEqual({
      read: true, write: false, approve: false, deny: false, merge: false, deploy: false,
    });
    expect(Object.isFrozen(TRACEABILITY_CHAIN_CAPABILITIES)).toBe(true);
  });
});
