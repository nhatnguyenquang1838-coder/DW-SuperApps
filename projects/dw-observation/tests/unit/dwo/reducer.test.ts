/**
 * CR-824-A/B/C/D verification — UniversalRun reducer.
 *
 * AC-824-01 V2_REDUCER_CERTIFIED derivable
 * AC-824-02 same event prefix produces same state (deterministic)
 * AC-824-03 missing facts stay UNKNOWN/PARTIAL
 * AC-824-04 parent completion never inferred solely from child-local success
 * AC-824-05 recursive Root/Child/Atomic reduction + dependency blocking path
 */
import { describe, expect, it } from 'vitest';
import {
  REDUCER_CAPABILITIES,
  initialRunState,
  isPartial,
  reduceEvent,
  reduceEventPrefix,
  type ReducerEvent,
} from '@/lib/dwo/reducer';
import {
  TOPOLOGY_CAPABILITIES,
  buildRunTree,
  isParentComplete,
  type RunNode,
} from '@/lib/dwo/recursiveTopology';
import {
  BLOCKING_PATH_CAPABILITIES,
  evaluateBlockingPath,
  reconcileGateState,
} from '@/lib/dwo/blockingPath';
import {
  CERTIFICATION_CAPABILITIES,
  assertDeterministicReduction,
  assertParentCompositionIndependent,
  deriveV2ReducerCertified,
  type ReducerCertificationInput,
} from '@/lib/dwo/reducerCertification';

function certInput(overrides: Partial<ReducerCertificationInput> = {}): ReducerCertificationInput {
  return {
    deterministic: true,
    missingFactsStayUnknown: true,
    parentCompositionIndependent: true,
    recursiveAndBlockingCorrect: true,
    fixtureConformance: true,
    ...overrides,
  };
}

function ev(runId: string, ordinal: number, overrides: Partial<ReducerEvent> = {}): ReducerEvent {
  return {
    eventId: `EVT-${runId}-${ordinal}`,
    runId,
    ordinal,
    gate: 'G2',
    gateState: 'ACTIVE',
    runState: 'OPEN',
    sourceProfile: 'DEV_NATIVE',
    syncState: 'LIVE',
    semanticQualification: 'PENDING',
    authorityState: 'NOT_APPLICABLE',
    anomalyCount: 0,
    ...overrides,
  };
}

describe('AC-824-02 · same event prefix produces same state (deterministic)', () => {
  it('reduceEventPrefix is deterministic for the same ordered prefix', () => {
    const events = [ev('R1', 1), ev('R1', 2, { gateState: 'PASSED', runState: 'ACCEPTED' })];
    const a = reduceEventPrefix('R1', events);
    const b = reduceEventPrefix('R1', events);
    expect(a).toEqual(b);
    expect(assertDeterministicReduction('R1', events)).toBe(true);
  });

  it('applies events in ordinal order regardless of input order', () => {
    const events = [
      ev('R1', 2, { gateState: 'PASSED', runState: 'ACCEPTED' }),
      ev('R1', 1),
    ];
    const state = reduceEventPrefix('R1', events);
    expect(state.gateState).toBe('PASSED');
    expect(state.runState).toBe('ACCEPTED');
  });

  it('ignores events for other runs', () => {
    const events = [ev('R1', 1), ev('R2', 1)];
    const state = reduceEventPrefix('R1', events);
    expect(state.runId).toBe('R1');
  });
});

describe('AC-824-03 · missing facts stay UNKNOWN/PARTIAL', () => {
  it('initial state is all UNKNOWN and PARTIAL', () => {
    const s = initialRunState('R1');
    expect(s.runState).toBe('UNKNOWN');
    expect(s.sourceProfile).toBe('UNKNOWN');
    expect(s.partial).toBe(true);
    expect(isPartial(s)).toBe(true);
  });

  it('a partial event leaves missing facts UNKNOWN', () => {
      const s = reduceEvent(initialRunState('R1'), {
        eventId: 'EVT-R1-1',
        runId: 'R1',
        ordinal: 1,
        runState: 'OPEN',
      });
      // runState known, but sourceProfile/sync/etc still UNKNOWN
      expect(s.runState).toBe('OPEN');
      expect(s.sourceProfile).toBe('UNKNOWN');
      expect(s.partial).toBe(true);
    });

  it('a full event makes the state non-partial', () => {
    const s = reduceEvent(initialRunState('R1'), ev('R1', 1));
    expect(s.partial).toBe(false);
  });
});

describe('AC-824-04 · parent completion never inferred solely from child-local success', () => {
  function node(id: string, kind: 'ROOT' | 'CHILD' | 'ATOMIC', parent: string | null, children: string[], gate: string | null, gateState: string | null): RunNode {
    return {
      runId: id,
      runKind: kind,
      parentRunRef: parent,
      childRunRefs: children,
      state: {
        runId: id,
        gate,
        gateState,
        runState: gate === 'G6' && gateState === 'PASSED' ? 'ACCEPTED' : 'OPEN',
        sourceProfile: 'DEV_NATIVE',
        syncState: 'LIVE',
        semanticQualification: 'PENDING',
        authorityState: 'NOT_APPLICABLE',
        anomalyCount: 0,
        partial: false,
      },
    };
  }

  it('a parent with accepted children but own gate not G6 is NOT complete', () => {
    // DEV-RUN-024: children 025/026 ACCEPTED, parent still G3 ACTIVE
    const tree = buildRunTree([
      node('024', 'ROOT', null, ['025', '026'], 'G3', 'ACTIVE'),
      node('025', 'CHILD', '024', [], 'G6', 'PASSED'),
      node('026', 'CHILD', '024', [], 'G6', 'PASSED'),
    ]);
    expect(isParentComplete(tree, '024')).toBe(false);
    expect(assertParentCompositionIndependent(tree, '024', true)).toBe(true);
  });

  it('a parent with own gate G6/PASSED IS complete', () => {
    const tree = buildRunTree([
      node('006', 'ROOT', null, [], 'G6', 'PASSED'),
    ]);
    expect(isParentComplete(tree, '006')).toBe(true);
  });

  it('buildRunTree rejects an inconsistent topology', () => {
    expect(() =>
      buildRunTree([
        node('A', 'ROOT', null, ['B'], 'G2', 'ACTIVE'),
        node('B', 'CHILD', 'A', [], 'G2', 'ACTIVE'),
        node('C', 'CHILD', 'A', [], 'G2', 'ACTIVE'), // C not in A's child list
      ]),
    ).toThrow(/does not list child/);
  });
});

describe('AC-824-05 · recursive reduction + dependency blocking path', () => {
  it('blocks on an unmet dependency with explicit reason', () => {
    const bp = evaluateBlockingPath('R3', [{ depId: 'R2', state: 'OPEN' }], 'NOT_APPLICABLE');
    expect(bp.status).toBe('BLOCKED');
    expect(bp.reason).toBe('UNMET_DEPENDENCY');
    expect(bp.blockedBy).toEqual(['R2']);
  });

  it('blocks on denied authority', () => {
    const bp = evaluateBlockingPath('R4', [], 'DENIED');
    expect(bp.status).toBe('BLOCKED');
    expect(bp.reason).toBe('AUTHORITY_DENIED');
  });

  it('blocks on upstream dependency revalidation required', () => {
    const bp = evaluateBlockingPath('R29', [{ depId: 'R28', state: 'ACCEPTED', revalidationRequired: true }], 'NOT_APPLICABLE');
    expect(bp.status).toBe('BLOCKED');
    expect(bp.reason).toBe('UPSTREAM_DEPENDENCY_REVALIDATION_REQUIRED');
  });

  it('is ELIGIBLE when all deps accepted and authority not denied', () => {
    const bp = evaluateBlockingPath('R10', [{ depId: 'R9', state: 'ACCEPTED' }], 'NOT_APPLICABLE');
    expect(bp.status).toBe('ELIGIBLE');
  });

  it('fails closed to UNKNOWN when a dependency state is unknown', () => {
      const bp = evaluateBlockingPath('R1', [{ depId: 'R2', state: 'UNKNOWN' }], 'NOT_APPLICABLE');
      expect(bp.status).toBe('UNKNOWN');
      expect(bp.reason).toBe('UNKNOWN');
    });

    it('produces WAITING for an external pending condition (F1)', () => {
      const bp = evaluateBlockingPath('R22', [], 'NOT_APPLICABLE', ['EXTERNAL_GUEST_CONFIRMATIONS_PENDING']);
      expect(bp.status).toBe('WAITING');
      expect(bp.reason).toBe('EXTERNAL_CONDITION_PENDING');
      expect(bp.blockedBy).toEqual(['EXTERNAL_GUEST_CONFIRMATIONS_PENDING']);
    });

    it('reconciles gateState to BLOCKED/WAITING (F2)', () => {
      const blocked = evaluateBlockingPath('R4', [], 'DENIED');
      expect(reconcileGateState('ACTIVE', blocked)).toBe('BLOCKED');
      const waiting = evaluateBlockingPath('R22', [], 'NOT_APPLICABLE', ['EXTERNAL']);
      expect(reconcileGateState('ACTIVE', waiting)).toBe('WAITING');
      const eligible = evaluateBlockingPath('R10', [{ depId: 'R9', state: 'ACCEPTED' }], 'NOT_APPLICABLE');
      expect(reconcileGateState('ACTIVE', eligible)).toBe('ACTIVE');
    });
  });

  describe('F3/F4/F5 — review fixes', () => {
    it('F3: buildRunTree rejects run_kind/parent-child incoherence', () => {
      // ATOMIC with children is invalid.
      expect(() =>
        buildRunTree([
          { runId: 'A', runKind: 'ATOMIC', parentRunRef: null, childRunRefs: ['B'], state: { runId: 'A', gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_APPLICABLE', anomalyCount: 0, partial: false } },
          { runId: 'B', runKind: 'CHILD', parentRunRef: 'A', childRunRefs: [], state: { runId: 'B', gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_APPLICABLE', anomalyCount: 0, partial: false } },
        ]),
      ).toThrow(/ATOMIC/);
    });

    it('F4: reduceEvent rejects an out-of-contract runState', () => {
      expect(() =>
        reduceEvent(initialRunState('R1'), { eventId: 'E', runId: 'R1', ordinal: 1, runState: 'BOGUS' }),
      ).toThrow(/invalid runState/);
    });

    it('F4: reduceEvent rejects an out-of-contract gateState', () => {
      expect(() =>
        reduceEvent(initialRunState('R1'), { eventId: 'E', runId: 'R1', ordinal: 1, gateState: 'BOGUS' }),
      ).toThrow(/invalid gateState/);
    });

    it('F5: parent at G6 but not PASSED is not complete even with accepted children', () => {
      const tree = buildRunTree([
        { runId: 'P', runKind: 'ROOT', parentRunRef: null, childRunRefs: ['C'], state: { runId: 'P', gate: 'G6', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_APPLICABLE', anomalyCount: 0, partial: false } },
        { runId: 'C', runKind: 'CHILD', parentRunRef: 'P', childRunRefs: [], state: { runId: 'C', gate: 'G6', gateState: 'PASSED', runState: 'ACCEPTED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_APPLICABLE', anomalyCount: 0, partial: false } },
      ]);
      expect(isParentComplete(tree, 'P')).toBe(false);
      expect(assertParentCompositionIndependent(tree, 'P', true)).toBe(true);
    });
  });

describe('AC-824-01 · V2_REDUCER_CERTIFIED derivation', () => {
  it('derives the token from a coherent reducer', () => {
    const decision = deriveV2ReducerCertified(certInput());
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_REDUCER_CERTIFIED');
    expect(decision.reasons).toEqual([]);
  });

  it('fails closed on non-determinism', () => {
    expect(deriveV2ReducerCertified(certInput({ deterministic: false })).derivable).toBe(false);
  });

  it('fails closed when parent completion is inferred from child-local success', () => {
    expect(deriveV2ReducerCertified(certInput({ parentCompositionIndependent: false })).derivable).toBe(false);
  });

  it('fails closed when missing facts are fabricated', () => {
    expect(deriveV2ReducerCertified(certInput({ missingFactsStayUnknown: false })).derivable).toBe(false);
  });
});

describe('capabilities — reducer/topology/blocking/certification are read-only', () => {
  it('exposes no effect capability anywhere', () => {
    for (const caps of [REDUCER_CAPABILITIES, TOPOLOGY_CAPABILITIES, BLOCKING_PATH_CAPABILITIES, CERTIFICATION_CAPABILITIES]) {
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
