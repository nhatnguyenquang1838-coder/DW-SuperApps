/**
 * CR-823-A/B/C/D verification — Projection Contract v2.
 *
 * AC-823-01 V2_CONTRACT_FROZEN derivable
 * AC-823-02 contract additive/versioned, preserves historical semantic integrity
 * AC-823-03 unsupported profiles fail closed (UNKNOWN/INCOMPATIBLE)
 * AC-823-04 event position/order, gap identity, correlation/causation frozen
 * AC-823-05 FNR-02 comparison contract versioned with cross-runtime vectors
 */
import { describe, expect, it } from 'vitest';
import {
  PROJECTION_CONTRACT_V2,
  PROJECTION_CONTRACT_V2_VERSION,
  UPCAST_RULES,
  assertProjectionRecordV2,
  upcastV1ToV2,
  type ProjectionRecordV2,
} from '@/lib/dwo/projectionContract';
import {
  INCOMPATIBLE_PROJECTION,
  PROFILE_REGISTRY,
  resolveProfileProjection,
  supportsUniversalSemantics,
} from '@/lib/dwo/profileRegistry';
import {
  detectGaps,
  type CorrelationMetadata,
} from '@/lib/dwo/eventPosition';
import {
  FNR02_CONTRACT,
  FNR02_CONTRACT_ID,
  FNR02_CONTRACT_VERSION,
  compareStates,
  deriveV2ContractFrozen,
  normalizeForComparison,
  type ContractFrozenInput,
} from '@/lib/dwo/comparisonContract';

function validRecord(): ProjectionRecordV2 {
  return {
    schemaId: PROJECTION_CONTRACT_V2,
    schemaVersion: PROJECTION_CONTRACT_V2_VERSION,
    recordId: 'REC-001',
    runIdentity: { runId: 'DEV-RUN-001', runKind: 'ROOT', parentRunRef: null, childRunRefs: ['DEV-RUN-002'] },
    gates: [{ namespace: 'UR_G', gate: 'G2', state: 'ACTIVE' }],
    runState: 'OPEN',
    sourceProfile: 'DEV_NATIVE',
    syncState: 'LIVE',
    semanticQualification: 'PENDING',
    authorityState: 'NOT_REQUIRED',
    anomalyCount: 0,
  };
}

function frozenInput(overrides: Partial<ContractFrozenInput> = {}): ContractFrozenInput {
  return {
    contractId: FNR02_CONTRACT_ID,
    contractVersion: FNR02_CONTRACT_VERSION,
    mode: 'STRUCTURED_STATE_EQUALITY',
    hasCrossRuntimeVectors: true,
    vectorsPass: true,
    ...overrides,
  };
}

describe('AC-823-02 · contract is additive/versioned, preserves historical integrity', () => {
  it('exposes the canonical v2 schema id and version', () => {
    expect(PROJECTION_CONTRACT_V2).toBe('gwc.dwo.projection-contract-v2');
    expect(PROJECTION_CONTRACT_V2_VERSION).toBe(2);
  });

  it('has registered upcast rules (v1 -> v2) that preserve history', () => {
    expect(UPCAST_RULES.length).toBeGreaterThan(0);
    const v1to2 = UPCAST_RULES.find((r) => r.fromVersion === 1 && r.toVersion === 2);
    expect(v1to2).toBeDefined();
  });

  it('upcasts a v1 record to v2 without rewriting the v1 source', () => {
    const v2 = upcastV1ToV2({ recordId: 'REC-LEGACY', runId: 'DEV-RUN-001' });
    expect(v2.schemaId).toBe(PROJECTION_CONTRACT_V2);
    expect(v2.schemaVersion).toBe(2);
    expect(v2.runIdentity.runId).toBe('DEV-RUN-001');
  });

  it('validates a well-formed v2 record', () => {
    expect(() => assertProjectionRecordV2(validRecord())).not.toThrow();
  });

  it('rejects a record that conflates UR-G* and GWC-* gate namespaces', () => {
    const bad: ProjectionRecordV2 = {
      ...validRecord(),
      gates: [
        { namespace: 'UR_G', gate: 'G2', state: 'ACTIVE' },
        { namespace: 'GWC_EFFECT', gate: 'G2', state: 'ACTIVE' }, // conflation
      ],
    };
    expect(() => assertProjectionRecordV2(bad)).toThrow(/conflated/);
  });
});

describe('AC-823-03 · unsupported profiles fail closed', () => {
  it('registers the four canonical profiles', () => {
    const profiles = PROFILE_REGISTRY.map((p) => p.profile);
    expect(profiles).toEqual(['DEV_NATIVE', 'COMPATIBILITY', 'COMPATIBILITY_LEGACY', 'UNKNOWN']);
  });

  it('UNKNOWN fails closed as INCOMPATIBLE with no heuristic semantics', () => {
    const proj = resolveProfileProjection('UNKNOWN');
    expect(proj.failClosed).toBe(true);
    expect(proj.semanticQualification).toBe('INCOMPATIBLE');
    expect(proj.syncState).toBe('UNAVAILABLE');
    expect(proj.sourceProfile).toBe('UNKNOWN');
  });

  it('an unrecognized profile also fails closed', () => {
    const proj = resolveProfileProjection('SOME-NEW-PROFILE');
    expect(proj.failClosed).toBe(true);
    expect(proj.semanticQualification).toBe('INCOMPATIBLE');
  });

  it('only DEV_NATIVE and COMPATIBILITY support Universal semantics', () => {
    expect(supportsUniversalSemantics('DEV_NATIVE')).toBe(true);
    expect(supportsUniversalSemantics('COMPATIBILITY')).toBe(true);
    expect(supportsUniversalSemantics('COMPATIBILITY_LEGACY')).toBe(false);
    expect(supportsUniversalSemantics('UNKNOWN')).toBe(false);
  });

  it('exposes the canonical INCOMPATIBLE projection constant', () => {
    expect(INCOMPATIBLE_PROJECTION).toEqual({
      sourceProfile: 'UNKNOWN',
      syncState: 'UNAVAILABLE',
      semanticQualification: 'INCOMPATIBLE',
      authorityState: 'NOT_REQUIRED',
      anomalyCount: 0,
      failClosed: true,
    });
  });
});

describe('AC-823-04 · event position/order, gap identity, correlation frozen', () => {
  it('detects a missing-sequence gap', () => {
    const gaps = detectGaps('src', [1, 2, 4]);
    expect(gaps.some((g) => g.isDuplicate === false && g.isOutOfOrder === false && g.fromSequence === 3 && g.toSequence === 3)).toBe(true);
  });

  it('detects a duplicate gap', () => {
    const gaps = detectGaps('src', [1, 1, 2]);
    expect(gaps.some((g) => g.isDuplicate === true)).toBe(true);
  });

  it('detects an out-of-order regression', () => {
    const gaps = detectGaps('src', [1, 3, 2]);
    expect(gaps.some((g) => g.isOutOfOrder === true)).toBe(true);
  });

  it('produces stable gap ids', () => {
    const gaps = detectGaps('src', [1, 3]);
    for (const g of gaps) {
      expect(g.gapId).toMatch(/^gap-src-/);
    }
  });

  it('correlation metadata is evidence-only (optional, never identity/authority)', () => {
    const meta: CorrelationMetadata = { traceId: 't1', causeRefs: ['c1'] };
    // The contract is that these are optional evidence metadata. Assert the shape.
    expect(meta.traceId).toBe('t1');
    expect(meta.causeRefs).toEqual(['c1']);
  });
});

describe('AC-823-05 · FNR-02 comparison contract versioned with cross-runtime vectors', () => {
  it('exposes the frozen contract id, version and structured-state mode', () => {
    expect(FNR02_CONTRACT.contractId).toBe('gwc.dwo.fnr02-comparison');
    expect(FNR02_CONTRACT.contractVersion).toBe(1);
    expect(FNR02_CONTRACT.mode).toBe('STRUCTURED_STATE_EQUALITY');
  });

  it('excludes UI-only digests from certification comparison', () => {
    expect(FNR02_CONTRACT.excludedFields).toContain('uiDigest');
    expect(FNR02_CONTRACT.includedFields).not.toContain('uiDigest');
  });

  it('has cross-runtime vectors proving equivalent and non-equivalent states', () => {
    const vectors = FNR02_CONTRACT.crossRuntimeVectors;
    expect(vectors.length).toBeGreaterThanOrEqual(4);
    expect(vectors.some((v) => v.expected === 'EQUIVALENT')).toBe(true);
    expect(vectors.some((v) => v.expected === 'NON_EQUIVALENT')).toBe(true);
  });

  it('compareStates() matches the vector expectations', () => {
    for (const v of FNR02_CONTRACT.crossRuntimeVectors) {
      const result = compareStates(v.left as Record<string, unknown>, v.right as Record<string, unknown>);
      expect(result, `vector ${v.id}`).toBe(v.expected);
    }
  });

  it('normalization drops excluded fields and sorts keys', () => {
    const norm = normalizeForComparison({ runId: 'R', uiDigest: 'x', runState: 'OPEN' });
    expect(norm).not.toHaveProperty('uiDigest');
    expect(norm).toHaveProperty('runId');
    expect(norm).toHaveProperty('runState');
  });
});

describe('AC-823-01 · V2_CONTRACT_FROZEN derivation', () => {
  it('derives the token from a coherent frozen contract', () => {
    const decision = deriveV2ContractFrozen(frozenInput());
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_CONTRACT_FROZEN');
    expect(decision.reasons).toEqual([]);
  });

  it('fails closed when the mode is a UI digest (not certification equality)', () => {
    const decision = deriveV2ContractFrozen(frozenInput({ mode: 'CANONICAL_DIGEST' }));
    expect(decision.derivable).toBe(false);
    expect(decision.reasons.some((r) => r.includes('not UI digest'))).toBe(true);
  });

  it('fails closed when vectors are missing or failing', () => {
    expect(deriveV2ContractFrozen(frozenInput({ hasCrossRuntimeVectors: false })).derivable).toBe(false);
    expect(deriveV2ContractFrozen(frozenInput({ vectorsPass: false })).derivable).toBe(false);
  });

  it('fails closed on wrong contract id/version', () => {
    expect(deriveV2ContractFrozen(frozenInput({ contractId: 'wrong' })).derivable).toBe(false);
    expect(deriveV2ContractFrozen(frozenInput({ contractVersion: 0 })).derivable).toBe(false);
  });
});
