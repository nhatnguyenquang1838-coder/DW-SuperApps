/**
 * R2-A focused tests — dependency satisfaction + derived BLOCKS fail-closed.
 *
 * Covers: satisfied, unresolved-unsatisfied, cycle, missing endpoint,
 * stale topology, durable gap, out-of-order, missing eligibility,
 * missing reducer state, and proof that malformed inputs never
 * derive BLOCKS. Provenance exactness for dependency/reducer/durable/topology.
 */
import { describe, expect, it } from 'vitest';
import {
  evaluateDependencySatisfactionV2,
  deriveBlocksFromSatisfaction,
  DEPENDENCY_SATISFACTION_CAPABILITIES,
  type DependencySpec,
} from '@/lib/dwo/dependencySatisfaction';

function dep(overrides: Partial<DependencySpec>): DependencySpec {
  return {
    depId: 'D1',
    targetRunRef: 'DEV-RUN-001',
    required: true,
    reducerState: 'ACCEPTED',
    durablePosition: 1,
    topologyRevision: 'rev-1',
    topologyDigest: 'abc123',
    eligibility: 'ELIGIBLE',
    ...overrides,
  };
}

describe('R2-A · satisfied path', () => {
  it('all required deps ACCEPTED with known facts → SATISFIED, no BLOCKS', () => {
    const result = evaluateDependencySatisfactionV2('R1', [dep()], 'rev-1', 'abc123');
    expect(result.status).toBe('SATISFIED');
    expect(result.blocks).toBe(false);
    expect(result.reason).toBeNull();
  });

  it('deriveBlocksFromSatisfaction returns false for SATISFIED', () => {
    const result = evaluateDependencySatisfactionV2('R1', [dep()], 'rev-1', 'abc123');
    expect(deriveBlocksFromSatisfaction(result)).toBe(false);
  });
});

describe('R2-A · unresolved paths never derive BLOCKS', () => {
  it('missing reducer state → UNKNOWN_UNRESOLVED, blocks=false', () => {
    const result = evaluateDependencySatisfactionV2('R1', [dep({ reducerState: 'UNKNOWN' })], 'rev-1', 'abc123');
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.blocks).toBe(false);
    expect(result.reason).toBe('MISSING_REDUCER_STATE');
    expect(deriveBlocksFromSatisfaction(result)).toBe(false);
  });

  it('missing eligibility → UNKNOWN_UNRESOLVED, never BLOCKS', () => {
    const result = evaluateDependencySatisfactionV2('R1', [dep({ eligibility: 'UNKNOWN' })], 'rev-1', 'abc123');
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.blocks).toBe(false);
  });

  it('cycle detected → UNKNOWN_UNRESOLVED, never BLOCKS', () => {
    const result = evaluateDependencySatisfactionV2('R1', [
      dep({ depId: 'R1', targetRunRef: 'R1' }),
    ], 'rev-1', 'abc123');
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.blocks).toBe(false);
    expect(result.reason).toBe('CYCLE_DETECTED');
  });

  it('missing endpoint (empty targetRunRef) → UNKNOWN_UNRESOLVED', () => {
    const result = evaluateDependencySatisfactionV2('R1', [dep({ targetRunRef: '' })], 'rev-1', 'abc123');
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.blocks).toBe(false);
    expect(result.reason).toBe('MISSING_ENDPOINT');
  });

  it('stale topology → UNKNOWN_UNRESOLVED', () => {
    const result = evaluateDependencySatisfactionV2('R1', [dep({ topologyRevision: 'stale-rev' })], 'current-rev', 'abc123');
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.blocks).toBe(false);
    expect(result.reason).toBe('STALE_TOPOLOGY');
  });

  it('durable gap without watermark → SATISFIED (no gap inferred without explicit watermark)', () => {
    const result = evaluateDependencySatisfactionV2('R1', [
      dep({ depId: 'D1', durablePosition: 1 }),
      dep({ depId: 'D2', durablePosition: 5 }),
    ], 'rev-1', 'abc123');
    expect(result.status).toBe('SATISFIED');
    expect(result.blocks).toBe(false);
  });

  it('out-of-order position → UNKNOWN_UNRESOLVED', () => {
    const result = evaluateDependencySatisfactionV2('R1', [
      dep({ depId: 'D1', durablePosition: 3 }),
      dep({ depId: 'D2', durablePosition: 1 }),
    ], 'rev-1', 'abc123');
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.blocks).toBe(false);
    expect(result.reason).toBe('OUT_OF_ORDER');
  });
});

describe('R2-A · resolved unsatisfied → derived BLOCKS', () => {
  it('required dep with known non-ACCEPTED reducer state → UNSATISFIED, BLOCKS', () => {
    const result = evaluateDependencySatisfactionV2('R1', [dep({ reducerState: 'OPEN' })], 'rev-1', 'abc123');
    expect(result.status).toBe('UNSATISFIED');
    expect(result.blocks).toBe(true);
    expect(result.reason).toContain('dependency');
    expect(deriveBlocksFromSatisfaction(result)).toBe(true);
  });

  it('INELIGIBLE with known eligibility → UNSATISFIED, BLOCKS', () => {
    const result = evaluateDependencySatisfactionV2('R1', [dep({ eligibility: 'INELIGIBLE' })], 'rev-1', 'abc123');
    expect(result.status).toBe('UNSATISFIED');
    expect(result.blocks).toBe(true);
  });
});

describe('R2-A · provenance exactness', () => {
  it('provenance binds dependency, reducer state, durable position, topology', () => {
    const result = evaluateDependencySatisfactionV2('R1', [
      dep({ depId: 'D-X', targetRunRef: 'T-X', reducerState: 'OPEN', durablePosition: 42, topologyRevision: 'rev-9', topologyDigest: 'digest9' }),
    ], 'rev-9', 'digest9');
    expect(result.provenance).toHaveLength(1);
    expect(result.provenance[0].depId).toBe('D-X');
    expect(result.provenance[0].targetRunRef).toBe('T-X');
    expect(result.provenance[0].reducerState).toBe('OPEN');
    expect(result.provenance[0].durablePosition).toBe(42);
    expect(result.provenance[0].topologyRevision).toBe('rev-9');
    expect(result.provenance[0].topologyDigest).toBe('digest9');
  });
});

describe('R2-A · capability marker', () => {
  it('read-only, no effect affordance', () => {
    expect(DEPENDENCY_SATISFACTION_CAPABILITIES).toEqual({
      read: true, write: false, approve: false, deny: false, merge: false, deploy: false,
    });
    expect(Object.isFrozen(DEPENDENCY_SATISFACTION_CAPABILITIES)).toBe(true);
  });
});
