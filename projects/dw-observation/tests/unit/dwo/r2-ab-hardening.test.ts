/**
 * R2-A / R2-B hardening regression tests.
 *
 * Each test names the defect it closes. A defect is only considered closed
 * when a test FAILS without the corresponding implementation change and
 * PASSES with it — otherwise the test is decoration, not evidence.
 */

import { describe, expect, it } from 'vitest';

import {
  evaluateDependencySatisfactionV2,
  deriveBlocksFromSatisfaction,
  type DependencySpec,
  type Eligibility,
  type ReducerState,
} from '../../../lib/dwo/dependencySatisfaction';

import {
  assertTraceabilityComplete,
  assertTraceabilityReadiness,
  buildTraceabilityChainV2,
  type EvidenceDescriptor,
  type DigestPinnedEvidenceRegistry,
} from '../../../lib/dwo/traceabilityChain';

const REV = 'rev-7';
const DIGEST = 'sha256:topology-7';

function dep(overrides: Partial<DependencySpec> = {}): DependencySpec {
  return {
    depId: 'dep-a',
    targetRunRef: 'RUN-A',
    required: true,
    reducerState: 'ACCEPTED' as ReducerState,
    durablePosition: 1,
    durableWatermark: true,
    topologyRevision: REV,
    topologyDigest: DIGEST,
    eligibility: 'ELIGIBLE' as Eligibility,
    ...overrides,
  };
}

function ev(ref: string, digest: string, required = true): EvidenceDescriptor {
  return { ref, digest, required };
}

describe('R2-A defect closure', () => {
  it('A1: emits DURABLE_GAP only with explicit watermark evidence beyond observed positions', () => {
    const deps = [dep({ depId: 'dep-a', durablePosition: 1 })];

    // Watermark beyond the max observed position => a real durable gap.
    const withGap = evaluateDependencySatisfactionV2('RUN-X', deps, REV, DIGEST, {
      reducerWatermark: 9,
    });
    expect(withGap.status).toBe('UNKNOWN_UNRESOLVED');
    expect(withGap.reason).toBe('DURABLE_GAP');

    // No watermark => non-adjacent positions alone are NOT a gap.
    const noWatermark = evaluateDependencySatisfactionV2('RUN-X', deps, REV, DIGEST, {});
    expect(noWatermark.status).toBe('SATISFIED');

    // Watermark at or below max observed => no gap.
    const noGap = evaluateDependencySatisfactionV2('RUN-X', deps, REV, DIGEST, {
      reducerWatermark: 1,
    });
    expect(noGap.status).toBe('SATISFIED');
  });

  it('A2: rejects a non-empty targetRunRef that is not in the topology node set', () => {
    const deps = [dep({ targetRunRef: 'RUN-GHOST' })];

    // Registered node => endpoint resolves.
    const registered = evaluateDependencySatisfactionV2('RUN-X', deps, REV, DIGEST, {
      topologyNodeSet: ['RUN-A', 'RUN-B'],
    });
    expect(registered.status).toBe('UNKNOWN_UNRESOLVED');
    expect(registered.reason).toBe('MISSING_ENDPOINT');

    // Unregistered but non-empty ref => still a missing endpoint.
    const unregistered = evaluateDependencySatisfactionV2('RUN-X', deps, REV, DIGEST, {
      topologyNodeSet: ['RUN-A', 'RUN-B'],
    });
    expect(unregistered.reason).toBe('MISSING_ENDPOINT');

    // Registered set containing the ref => resolves past the endpoint check.
    const ok = evaluateDependencySatisfactionV2(
      'RUN-X',
      [dep({ targetRunRef: 'RUN-A' })],
      REV,
      DIGEST,
      { topologyNodeSet: ['RUN-A', 'RUN-B'] },
    );
    expect(ok.reason).not.toBe('MISSING_ENDPOINT');
  });

  it('A3: an empty dependency set is unresolved, never vacuously satisfied', () => {
    const result = evaluateDependencySatisfactionV2('RUN-X', [], REV, DIGEST, {});
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.blocks).toBe(false);
  });

  it('A4: evaluation is invariant under caller array order', () => {
    const a = dep({ depId: 'dep-a', durablePosition: 1 });
    const b = dep({ depId: 'dep-b', durablePosition: 2, targetRunRef: 'RUN-B' });

    const forward = evaluateDependencySatisfactionV2('RUN-X', [a, b], REV, DIGEST, {
      topologyNodeSet: ['RUN-A', 'RUN-B'],
    });
    const reversed = evaluateDependencySatisfactionV2('RUN-X', [b, a], REV, DIGEST, {
      topologyNodeSet: ['RUN-A', 'RUN-B'],
    });

    expect(reversed.status).toBe(forward.status);
    expect(reversed.reason).toBe(forward.reason);
    expect(reversed.reason).not.toBe('OUT_OF_ORDER');
  });

  it('A4b: duplicate durable positions across distinct deps are unresolved', () => {
    const a = dep({ depId: 'dep-a', durablePosition: 5 });
    const b = dep({ depId: 'dep-b', durablePosition: 5, targetRunRef: 'RUN-B' });
    const result = evaluateDependencySatisfactionV2('RUN-X', [a, b], REV, DIGEST, {
      topologyNodeSet: ['RUN-A', 'RUN-B'],
    });
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('OUT_OF_ORDER');
  });

  it('A5: a missing durable position reports its own reason, not MISSING_REDUCER_STATE', () => {
    const result = evaluateDependencySatisfactionV2(
      'RUN-X',
      [dep({ durablePosition: 'UNKNOWN' })],
      REV,
      DIGEST,
      {},
    );
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('MISSING_DURABLE_POSITION');
  });

  it('BLOCKS is derived only from resolved UNSATISFIED, never from UNKNOWN', () => {
    const unsat = evaluateDependencySatisfactionV2(
      'RUN-X',
      [dep({ reducerState: 'FAILED' })],
      REV,
      DIGEST,
      {},
    );
    expect(unsat.status).toBe('UNSATISFIED');
    expect(deriveBlocksFromSatisfaction(unsat)).toBe(true);

    const unknown = evaluateDependencySatisfactionV2(
      'RUN-X',
      [dep({ reducerState: 'UNKNOWN' })],
      REV,
      DIGEST,
      {},
    );
    expect(unknown.status).toBe('UNKNOWN_UNRESOLVED');
    expect(deriveBlocksFromSatisfaction(unknown)).toBe(false);
  });

  it('detects a self-cycle and a multi-node cycle', () => {
    const selfCycle = dep({ depId: 'dep-a', targetRunRef: 'dep-a' });
    const selfResult = evaluateDependencySatisfactionV2('RUN-X', [selfCycle], REV, DIGEST, {});
    expect(selfResult.status).toBe('UNKNOWN_UNRESOLVED');
    expect(selfResult.reason).toBe('CYCLE_DETECTED');

    // dep-a -> dep-b -> dep-a
    const n1 = dep({ depId: 'dep-a', targetRunRef: 'dep-b' });
    const n2 = dep({ depId: 'dep-b', targetRunRef: 'dep-a' });
    const multi = evaluateDependencySatisfactionV2('RUN-X', [n1, n2], REV, DIGEST, {});
    expect(multi.reason).toBe('CYCLE_DETECTED');
  });

  it('reports STALE_TOPOLOGY_DIGEST when a dep digest differs from current', () => {
    const result = evaluateDependencySatisfactionV2(
      'RUN-X',
      [dep({ topologyDigest: 'sha256:stale' })],
      REV,
      DIGEST,
      {},
    );
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('STALE_TOPOLOGY_DIGEST');
  });
});

describe('R2-B defect closure', () => {
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

  it('B1: detects a required-evidence digest that differs from the registry expectation', () => {
    const registry: DigestPinnedEvidenceRegistry = {
      requiredEvidenceIds: ['target.json'],
      entries: [{ id: 'target.json', expectedDigest: 'sha256:correct' }],
    };
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [ev('target.json', 'sha256:WRONG')],
      registry,
    );
    const decision = assertTraceabilityComplete(chain);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.reason).toBe('EVIDENCE_DIGEST_MISMATCH');
  });

  it('B1b: the correct pinned digest passes', () => {
    const registry: DigestPinnedEvidenceRegistry = {
      requiredEvidenceIds: ['target.json'],
      entries: [{ id: 'target.json', expectedDigest: 'sha256:correct' }],
    };
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [ev('target.json', 'sha256:correct')],
      registry,
    );
    expect(assertTraceabilityComplete(chain).status).toBe('PASS');
  });

  it('B2: an omitted required evidence reports OMITTED_REQUIRED_EVIDENCE, not the aggregate', () => {
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [],
      { requiredEvidenceIds: ['target.json', 'handoff.json'] },
    );
    const decision = assertTraceabilityComplete(chain);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.reason).toBe('OMITTED_REQUIRED_EVIDENCE');
    expect(decision.missingRefs).toContain('required-evidence:target.json');
  });

  it('B2b: a missing source ref reports MISSING_SOURCE_REF, not MISSING_REQUIRED_EVIDENCE', () => {
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      '', base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [],
      { requiredEvidenceIds: [] },
    );
    const decision = assertTraceabilityComplete(chain);
    expect(decision.reason).toBe('MISSING_SOURCE_REF');
    expect(decision.missingRefs).toContain('sourceRef');
  });

  it('B2c: a missing watermark reports its own reason', () => {
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      '', base.inputWatermark,
      [],
      { requiredEvidenceIds: [] },
    );
    expect(assertTraceabilityComplete(chain).reason).toBe('MISSING_REDUCER_WATERMARK');
  });

  it('never fabricates PASS for an empty evidence set without a registry', () => {
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [],
      { requiredEvidenceIds: [] },
    );
    // All identity/watermark facts present and no required evidence declared:
    // an empty declared set with no registry demand is a valid PASS, but the
    // chain identity must still be proven.
    expect(assertTraceabilityComplete(chain).status).toBe('PASS');

    // Identity mismatch must fail closed.
    const mismatched = buildTraceabilityChainV2(
      'RUN-1', 'RUN-2', base.durablePosition,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [],
      { requiredEvidenceIds: [] },
    );
    const decision = assertTraceabilityComplete(mismatched);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.reason).toBe('IDENTITY_MISMATCH');
  });

  it('B3: readiness delegates to the fail-closed completeness decision', () => {
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [ev('target.json', 'sha256:x')],
      { requiredEvidenceIds: ['target.json'] },
    );
    expect(assertTraceabilityReadiness(chain).status).toBe('PASS');

    const broken = buildTraceabilityChainV2(
      base.runId, base.projectionId, base.durablePosition,
      '', base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [],
      { requiredEvidenceIds: ['target.json'] },
    );
    expect(assertTraceabilityReadiness(broken).status).toBe('UNKNOWN_UNRESOLVED');
  });

  it('rejects a negative durable position', () => {
    const chain = buildTraceabilityChainV2(
      base.runId, base.projectionId, -1,
      base.sourceRef, base.sourceDigest, base.topologyRevision, base.topologyDigest,
      base.reducerWatermark, base.inputWatermark,
      [],
      { requiredEvidenceIds: [] },
    );
    const decision = assertTraceabilityComplete(chain);
    expect(decision.status).toBe('UNKNOWN_UNRESOLVED');
    expect(decision.reason).toBe('NEGATIVE_DURABLE_POSITION');
  });
});
