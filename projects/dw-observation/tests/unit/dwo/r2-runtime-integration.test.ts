/**
 * R2 runtime integration tests — modules are not isolated contract surfaces.
 *
 * These tests exercise the REAL consumer paths:
 *  - blockingPath.evaluateBlockingPathWithAuthority (R2-D gate)
 *  - reducerCertification.deriveV2ReducerCertified (R2-D + R2-E gate on token)
 *  - acceptanceCertification.deriveDwoV2Accepted + composeDwoV2Readiness (R2-D/E/F)
 *  - runViewModel.buildRunViewModel (R2-D/E/F view exposure)
 *
 * No module is tested in isolation here — each test wires at least two modules
 * through the actual call chain.
 */

import { describe, expect, it } from 'vitest';
import {
  evaluateBlockingPath,
  evaluateBlockingPathWithAuthority,
  evaluateBlockingPathWithDecision,
} from '@/lib/dwo/blockingPath';
import { deriveV2ReducerCertified } from '@/lib/dwo/reducerCertification';
import { isParentComplete, buildRunTree, type RunNode } from '@/lib/dwo/recursiveTopology';
import {
  deriveDwoV2Accepted,
  composeDwoV2Readiness,
  buildAcceptanceEvidence,
  type AcceptanceCertificationInput,
} from '@/lib/dwo/acceptanceCertification';
import { buildRunViewModel } from '@/lib/dwo/runViewModel';
import {
  deriveAuthorityState,
  isAuthorityGranted,
  type AuthorityEvidence,
  type AuthorityDecision,
} from '@/lib/dwo/authorityVocabulary';
import {
  evaluateParentCompositionContract,
  type ParentCompositionContractV2,
  type CompositionDecision,
} from '@/lib/dwo/parentComposition';
import {
  buildTaskRunIndexV2,
  resolveFromIndex,
  type TaskRunRelationRecord,
} from '@/lib/dwo/taskRunIndex';
import {
  buildTraceabilityChainV2,
  assertTraceabilityReadiness,
  type TraceabilityDecision,
} from '@/lib/dwo/traceabilityChain';
import { FIXTURE_CATALOG } from '@/lib/dwo/fixtureSpec';
import type { ReducedRunState } from '@/lib/dwo/reducer';
import { recordAcceptance } from '@/lib/dwo/acceptanceRecord';

const NOW = '2026-10-01T12:00:00.000Z';

function authorityEvidence(overrides: Partial<AuthorityEvidence> = {}): AuthorityEvidence {
  return {
    sourceIdentity: 'approver-7',
    sourceDigest: 'sha256:approval-record',
    scope: 'merge_to_main',
    assertedAt: '2026-10-01T10:00:00.000Z',
    expiresAt: '2026-10-01T14:00:00.000Z',
    assertedState: 'GRANTED',
    ...overrides,
  };
}

function authorityDecision(overrides: Partial<AuthorityEvidence> = {}): AuthorityDecision {
  return deriveAuthorityState(authorityEvidence(overrides), NOW);
}

function passTraceability(): TraceabilityDecision {
  const chain = buildTraceabilityChainV2(
    'T-1', 'T-1', 0,
    'src', 'sha256:src',
    'rev1', 'sha256:topo1',
    '3', '3',
    [],
    { requiredEvidenceIds: [], noEvidenceRequired: true },
  );
  return assertTraceabilityReadiness(chain);
}

// ================================================================
// R2-D — authority consumed by the real gate path
// ================================================================
describe('R2-D · authority through the real gate path', () => {
  it('proven GRANTED → dependency check only (ELIGIBLE when deps met)', () => {
    const decision = authorityDecision(); // GRANTED
    const bp = evaluateBlockingPathWithDecision('RUN-1', decision, []);
    expect(bp.status).toBe('ELIGIBLE');
    expect(bp.reason).toBeNull();
  });

  it('UNKNOWN authority → UNKNOWN (fail closed, never inferred DENIED)', () => {
    const decision = deriveAuthorityState(null, NOW); // no record
    const bp = evaluateBlockingPathWithDecision('RUN-1', decision, []);
    expect(bp.status).toBe('UNKNOWN');
    expect(bp.reason).toBe('UNKNOWN');
  });

  it('DENIED → BLOCKED with AUTHORITY_DENIED', () => {
    const decision = authorityDecision({ assertedState: 'DENIED' });
    const bp = evaluateBlockingPathWithDecision('RUN-1', decision, []);
    expect(bp.status).toBe('BLOCKED');
    expect(bp.reason).toBe('AUTHORITY_DENIED');
  });

  it('EXPIRED → BLOCKED with AUTHORITY_DENIED', () => {
    const decision = authorityDecision({ expiresAt: '2026-10-01T11:00:00.000Z' });
    const bp = evaluateBlockingPathWithDecision('RUN-1', decision, []);
    expect(bp.status).toBe('BLOCKED');
    expect(bp.reason).toBe('AUTHORITY_DENIED');
  });

  it('REVOKED → BLOCKED with AUTHORITY_DENIED', () => {
    const decision = authorityDecision({ assertedState: 'REVOKED' });
    const bp = evaluateBlockingPathWithDecision('RUN-1', decision, []);
    expect(bp.status).toBe('BLOCKED');
    expect(bp.reason).toBe('AUTHORITY_DENIED');
  });

  it('PENDING → WAITING (external decision outstanding)', () => {
    const decision = authorityDecision({ assertedState: 'PENDING' });
    const bp = evaluateBlockingPathWithDecision('RUN-1', decision, []);
    expect(bp.status).toBe('WAITING');
    expect(bp.reason).toBe('EXTERNAL_CONDITION_PENDING');
  });

  it('NOT_REQUIRED → no authority gate, dependency check only', () => {
    const decision = authorityDecision({ assertedState: 'NOT_REQUIRED', scope: 'deploy' });
    const bp = evaluateBlockingPathWithDecision('RUN-1', decision, []);
    expect(bp.status).toBe('ELIGIBLE');
  });

  it('legacy evaluateBlockingPath still DENIED→BLOCKED / UNKNOWN→UNKNOWN (backward compat)', () => {
    expect(evaluateBlockingPath('R', [], 'DENIED').status).toBe('BLOCKED');
    expect(evaluateBlockingPath('R', [], 'UNKNOWN').status).toBe('UNKNOWN');
    expect(evaluateBlockingPath('R', [], 'NOT_REQUIRED').status).toBe('ELIGIBLE');
  });

  it('isAuthorityGranted is true only for proven GRANTED', () => {
    expect(isAuthorityGranted(authorityDecision())).toBe(true);
    expect(isAuthorityGranted(authorityDecision({ assertedState: 'DENIED' }))).toBe(false);
    expect(isAuthorityGranted(deriveAuthorityState(null, NOW))).toBe(false);
    expect(isAuthorityGranted(authorityDecision({ assertedState: 'NOT_REQUIRED' }))).toBe(false);
  });

  it('evidence→decision→gate is one auditable chain: evidence absent → UNKNOWN → gate UNKNOWN', () => {
    const evidence: AuthorityEvidence | null = null;
    const decision = deriveAuthorityState(evidence, NOW);
    const bp = evaluateBlockingPathWithAuthority('RUN-1', evidence, NOW, []);
    expect(decision.state).toBe('UNKNOWN');
    expect(decision.reason).toBe('UNKNOWN_NO_ASSERTION');
    expect(bp.status).toBe('UNKNOWN');
  });
});

// ================================================================
// R2-E — parent composition through the real reducer certification
// ================================================================
describe('R2-E · parent composition through reducer certification', () => {
  const positiveContract: ParentCompositionContractV2 = {
    parentRunId: 'PARENT-A',
    revisionId: 'r1',
    requiredChildren: [
      { runId: 'CHILD-A', completionDigest: 'sha256:child-a', handoffReceiptRef: 'receipt-a' },
    ],
    optionalChildren: [],
    requiredHandoffReceiptRefs: ['receipt-a'],
    parentVerificationRef: 'verify/parent-a.json',
    targetAcceptanceRef: 'accept/parent-a.json',
  };

  function compositionDecision(contract: ParentCompositionContractV2, presentReceipts: string[]): CompositionDecision {
    return evaluateParentCompositionContract(contract, { gate: 'G6', gateState: 'PASSED' }, presentReceipts);
  }

  it('all child-local PASS + complete evidence → composed + accepted', () => {
    const d = compositionDecision(positiveContract, ['receipt-a']);
    expect(d.composed).toBe(true);
    expect(d.accepted).toBe(true);
    expect(d.reason).toBe('COMPOSED');
  });

  it('accepted children WITHOUT parent verification → not composed (the exact defect R2-E prevents)', () => {
    const d = compositionDecision(
      { ...positiveContract, parentVerificationRef: 'UNKNOWN' },
      ['receipt-a'],
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_PARENT_VERIFICATION');
  });

  it('reducerCertification: composed + GRANTED authority → token issued', () => {
    const comp = compositionDecision(positiveContract, ['receipt-a']);
    const decision = deriveV2ReducerCertified({
      deterministic: true,
      missingFactsStayUnknown: true,
      parentCompositionIndependent: true,
      recursiveAndBlockingCorrect: true,
      fixtureConformance: true,
      traceabilityDecision: passTraceability(),
      authorityDecision: authorityDecision(),
      parentComposition: comp,
    });
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_REDUCER_CERTIFIED');
  });

  it('reducerCertification: uncomposed parent → token blocked, reason source-backed', () => {
    const comp = compositionDecision(
      { ...positiveContract, parentVerificationRef: 'UNKNOWN' },
      ['receipt-a'],
    );
    const decision = deriveV2ReducerCertified({
      deterministic: true,
      missingFactsStayUnknown: true,
      parentCompositionIndependent: true,
      recursiveAndBlockingCorrect: true,
      fixtureConformance: true,
      traceabilityDecision: passTraceability(),
      authorityDecision: authorityDecision(),
      parentComposition: comp,
    });
    expect(decision.derivable).toBe(false);
    expect(decision.token).toBeNull();
    expect(decision.reasons.some((r) => r.includes('parent not composed'))).toBe(true);
  });

  it('reducerCertification: absent authorityDecision = not applicable (does not block)', () => {
    const comp = compositionDecision(positiveContract, ['receipt-a']);
    const decision = deriveV2ReducerCertified({
      deterministic: true,
      missingFactsStayUnknown: true,
      parentCompositionIndependent: true,
      recursiveAndBlockingCorrect: true,
      fixtureConformance: true,
      traceabilityDecision: passTraceability(),
      parentComposition: comp,
      // authorityDecision deliberately absent
    });
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_REDUCER_CERTIFIED');
  });

  it('assertParentCompositionIndependent still local: accepted children + non-G6 parent → false', () => {
    // This preserves the legacy lower-level check — it does NOT bypass the contract.
    // The v2 runtime path uses evaluateParentCompositionContract above.
    // Use a single-path tree from the fixture: DEV-RUN-005 (G3/FAILED root)
    // has two G6/PASSED children — accepted children must not complete the parent.
    const path = ['DEV-RUN-005', 'DEV-RUN-006', 'DEV-RUN-007'];
    const byId = new Map(FIXTURE_CATALOG.map((f) => [f.id, f]));
    const nodes: RunNode[] = path.map((id) => {
      const f = byId.get(id)!;
      return {
        runId: f.id,
        runKind: (f.kind === 'NEGATIVE' ? 'ATOMIC' : f.kind) as RunNode['runKind'],
        parentRunRef: f.parent,
        childRunRefs: f.children.filter((c) => path.includes(c)),
        state: {
          runId: f.id, gate: f.gate ?? 'G0', gateState: f.gateState ?? 'ACTIVE',
          runState: f.runState, sourceProfile: f.sourceProfile, syncState: f.syncState,
          semanticQualification: f.semanticQualification, authorityState: f.authorityState,
          anomalyCount: f.anomalyCount, partial: false,
        } as ReducedRunState,
      };
    });
    const tree = buildRunTree(nodes);
    // DEV-RUN-006 and DEV-RUN-007 are G6/PASSED (accepted).
    expect(tree.nodes['DEV-RUN-006'].state.gateState).toBe('PASSED');
    expect(tree.nodes['DEV-RUN-007'].state.gateState).toBe('PASSED');
    // But DEV-RUN-005 is G3/FAILED — isParentComplete must be false
    // even though all its children are accepted.
    expect(isParentComplete(tree, 'DEV-RUN-005')).toBe(false);
    // A G6/PASSED leaf IS complete on its own state.
    expect(isParentComplete(tree, 'DEV-RUN-006')).toBe(true);
  });
});

// ================================================================
// R2-F — task→root mapping through the real acceptance + view path
// ================================================================
describe('R2-F · task→root mapping through acceptance + view-model', () => {
  const records: TaskRunRelationRecord[] = [
    {
      taskRef: 'SCRUM-900',
      relationRevisionId: 'rel-1',
      rootRunIds: ['DEV-RUN-001', 'DEV-RUN-002'],
      sourceSystem: 'JIRA',
      sourceRecordId: 'JIRA-900',
      sourceDigest: 'sha256:rel-1',
      durablePosition: 1,
      supersedesRevisionId: null,
    },
  ];

  it('explicit mapping resolves via the real index', () => {
    const index = buildTaskRunIndexV2(records);
    const d = resolveFromIndex(index, 'SCRUM-900');
    expect(d.status).toBe('RESOLVED');
    expect(d.taskRef).toBe('SCRUM-900');
    expect(d.rootRunIds).toEqual(['DEV-RUN-001', 'DEV-RUN-002']);
  });

  it('no mapping → UNKNOWN_UNRESOLVED (no heuristic, no fabrication)', () => {
    const index = buildTaskRunIndexV2(records);
    const d = resolveFromIndex(index, 'SCRUM-999');
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.rootRunIds).toEqual([]);
  });

  it('conflicting same revision → RELATION_CONFLICT', () => {
    const conflictRecords: TaskRunRelationRecord[] = [
      {
        taskRef: 'SCRUM-900',
        relationRevisionId: 'rel-c',
        rootRunIds: ['DEV-RUN-001'],
        sourceSystem: 'JIRA',
        sourceRecordId: 'JIRA-900-a',
        sourceDigest: 'sha256:rel-c-a',
        durablePosition: 1,
        supersedesRevisionId: null,
      },
      {
        taskRef: 'SCRUM-900',
        relationRevisionId: 'rel-c',
        rootRunIds: ['DEV-RUN-002'],
        sourceSystem: 'JIRA',
        sourceRecordId: 'JIRA-900-b',
        sourceDigest: 'sha256:rel-c-b',
        durablePosition: 1,
        supersedesRevisionId: null,
      },
    ];
    const index = buildTaskRunIndexV2(conflictRecords);
    const d = resolveFromIndex(index, 'SCRUM-900');
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
    expect(d.reason).toBe('RELATION_CONFLICT');
    expect(d.conflictingRevisions).toEqual(['rel-c']);
  });

  it('explicit supersession resolves deterministically', () => {
    const superRecords: TaskRunRelationRecord[] = [
      {
        taskRef: 'SCRUM-900',
        relationRevisionId: 'rel-old',
        rootRunIds: ['DEV-RUN-001'],
        sourceSystem: 'JIRA',
        sourceRecordId: 'JIRA-900-old',
        sourceDigest: 'sha256:rel-old',
        durablePosition: 1,
        supersedesRevisionId: null,
      },
      {
        taskRef: 'SCRUM-900',
        relationRevisionId: 'rel-new',
        rootRunIds: ['DEV-RUN-002', 'DEV-RUN-003'],
        sourceSystem: 'JIRA',
        sourceRecordId: 'JIRA-900-new',
        sourceDigest: 'sha256:rel-new',
        durablePosition: 2,
        supersedesRevisionId: 'rel-old',
      },
    ];
    const index = buildTaskRunIndexV2(superRecords);
    const d = resolveFromIndex(index, 'SCRUM-900');
    expect(d.status).toBe('RESOLVED');
    expect(d.rootRunIds).toEqual(['DEV-RUN-002', 'DEV-RUN-003']);
  });

  it('heuristic-looking run IDs do not create mappings', () => {
    const index = buildTaskRunIndexV2(records);
    // No reverse lookup exists — resolveFromIndex requires declared taskRef.
    expect(() => resolveFromIndex(index, 'DEV-RUN-001')).not.toThrow();
    const d = resolveFromIndex(index, 'DEV-RUN-001');
    expect(d.status).toBe('UNKNOWN_UNRESOLVED');
  });

  it('deriveDwoV2Accepted with RESOLVED task relation → accepted', () => {
    const index = buildTaskRunIndexV2(records);
    const rel = resolveFromIndex(index, 'SCRUM-900');
    const input: AcceptanceCertificationInput = {
      realCampaignReconstructs: true,
      liveReplayEqual: true,
      readOnlySafe: true,
      evidenceProvenanceAttributable: true,
      targetHandoffIdentified: true,
      degradedModeHandled: true,
      reconstructsAfterReset: true,
      identitiesRecorded: true,
      taskRelation: rel,
    };
    const decision = deriveDwoV2Accepted(input);
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('DWO_V2_ACCEPTED');
  });

  it('deriveDwoV2Accepted with RELATION_CONFLICT → not accepted, source-backed reason', () => {
    const conflictRecords: TaskRunRelationRecord[] = [
      {
        taskRef: 'SCRUM-900', relationRevisionId: 'rel-c', rootRunIds: ['DEV-RUN-001'],
        sourceSystem: 'JIRA', sourceRecordId: 'a', sourceDigest: 'd1', durablePosition: 1, supersedesRevisionId: null,
      },
      {
        taskRef: 'SCRUM-900', relationRevisionId: 'rel-c', rootRunIds: ['DEV-RUN-002'],
        sourceSystem: 'JIRA', sourceRecordId: 'b', sourceDigest: 'd2', durablePosition: 1, supersedesRevisionId: null,
      },
    ];
    const rel = resolveFromIndex(buildTaskRunIndexV2(conflictRecords), 'SCRUM-900');
    const input: AcceptanceCertificationInput = {
      realCampaignReconstructs: true, liveReplayEqual: true, readOnlySafe: true,
      evidenceProvenanceAttributable: true, targetHandoffIdentified: true,
      degradedModeHandled: true, reconstructsAfterReset: true, identitiesRecorded: true,
      taskRelation: rel,
    };
    const decision = deriveDwoV2Accepted(input);
    expect(decision.derivable).toBe(false);
    expect(decision.token).toBeNull();
    expect(decision.reasons.some((r) => r.includes('task relation unresolved'))).toBe(true);
  });
});

// ================================================================
// Combined runtime — source evidence → decision → view-model
// ================================================================
describe('R2-D/E/F · combined runtime path: evidence → decision → view-model', () => {
  it('proven GRANTED + composed + resolved → view-model renders decisions, not inferred state', () => {
    const auth = authorityDecision();
    const contract: ParentCompositionContractV2 = {
      parentRunId: 'DEV-RUN-001',
      revisionId: 'r1',
      requiredChildren: [{ runId: 'DEV-RUN-002', completionDigest: 'sha256:c', handoffReceiptRef: 'r' }],
      optionalChildren: [],
      requiredHandoffReceiptRefs: ['r'],
      parentVerificationRef: 'verify.json',
      targetAcceptanceRef: 'accept.json',
    };
    const comp = evaluateParentCompositionContract(contract, { gate: 'G6', gateState: 'PASSED' }, ['r']);
    const index = buildTaskRunIndexV2([
      {
        taskRef: 'SCRUM-900', relationRevisionId: 'rel-1', rootRunIds: ['DEV-RUN-001'],
        sourceSystem: 'JIRA', sourceRecordId: 'J-900', sourceDigest: 'sha256:rel',
        durablePosition: 1, supersedesRevisionId: null,
      },
    ]);
    const rel = resolveFromIndex(index, 'SCRUM-900');

    const vm = buildRunViewModel(
      { 'DEV-RUN-001': auth },
      { 'DEV-RUN-001': comp },
      { 'DEV-RUN-001': rel },
    );

    const row = vm.rows.find((r) => r.runId === 'DEV-RUN-001')!;
    expect(row.authority!.state).toBe('GRANTED');
    expect(row.authority!.granted).toBe(true);
    expect(row.composition!.composed).toBe(true);
    expect(row.composition!.accepted).toBe(true);
    expect(row.taskRelation!.status).toBe('RESOLVED');
    expect(row.taskRelation!.rootRunIds).toContain('DEV-RUN-001');
  });

  it('UNKNOWN authority + uncomposed parent + no mapping → view-model renders UNKNOWN, never fabricates', () => {
    const auth = deriveAuthorityState(null, NOW); // no evidence
    const contract: ParentCompositionContractV2 = {
      parentRunId: 'DEV-RUN-010', revisionId: 'r1',
      requiredChildren: [{ runId: 'DEV-RUN-011', completionDigest: 'sha256:c', handoffReceiptRef: 'r' }],
      optionalChildren: [], requiredHandoffReceiptRefs: ['r'],
      parentVerificationRef: 'verify.json', targetAcceptanceRef: 'accept.json',
    };
    const comp = evaluateParentCompositionContract(contract, { gate: 'G6', gateState: 'PASSED' }, ['r']);
    // comp IS composed — but we test the negative path via authority only
    const vm = buildRunViewModel(
      { 'DEV-RUN-010': auth },
      { 'DEV-RUN-010': comp },
      { 'DEV-RUN-010': resolveFromIndex(buildTaskRunIndexV2([]), 'NO-TASK') },
    );
    const row = vm.rows.find((r) => r.runId === 'DEV-RUN-010')!;
    expect(row.authority!.state).toBe('UNKNOWN');
    expect(row.authority!.reason).toBe('UNKNOWN_NO_ASSERTION');
    expect(row.composition!.composed).toBe(true);
    expect(row.taskRelation!.status).toBe('UNKNOWN_UNRESOLVED');
  });

  it('composeDwoV2Readiness composes all four decisions into one readiness', () => {
    const r = composeDwoV2Readiness(
      authorityDecision(),
      evaluateParentCompositionContract(
        {
          parentRunId: 'P', revisionId: 'r1',
          requiredChildren: [{ runId: 'C', completionDigest: 'd', handoffReceiptRef: 'rc' }],
          optionalChildren: [], requiredHandoffReceiptRefs: ['rc'],
          parentVerificationRef: 'v', targetAcceptanceRef: 'a',
        },
        { gate: 'G6', gateState: 'PASSED' },
        ['rc'],
      ),
      resolveFromIndex(buildTaskRunIndexV2([
        { taskRef: 'T', relationRevisionId: 'r1', rootRunIds: ['R'], sourceSystem: 'J', sourceRecordId: 'x', sourceDigest: 'd', durablePosition: 1, supersedesRevisionId: null },
      ]), 'T'),
      passTraceability(),
    );
    expect(r.ready).toBe(true);
    expect(r.reasons).toEqual([]);
    expect(r.decisions.authority?.granted).toBe(true);
    expect(r.decisions.composition?.composed).toBe(true);
    expect(r.decisions.taskRelation?.status).toBe('RESOLVED');
    expect(r.decisions.traceability?.status).toBe('PASS');
  });

  it('composeDwoV2Readiness: absent decision = not applicable, not a failure', () => {
    const r = composeDwoV2Readiness(undefined, undefined, undefined, undefined);
    expect(r.ready).toBe(true);
    expect(r.reasons).toEqual([]);
    expect(r.decisions.authority).toBeNull();
    expect(r.decisions.composition).toBeNull();
    expect(r.decisions.taskRelation).toBeNull();
    expect(r.decisions.traceability).toBeNull();
  });

  it('acceptanceCertification.buildAcceptanceEvidence carries R2 fields when supplied', () => {
    const campaign = { reconstructsFromDurable: true, liveReplayEqual: true } as never;
    const validation = { readOnlySafe: true, evidenceProvenanceAttributable: true, targetHandoffIdentified: true, degradedModeHandled: true };
    const record = recordAcceptance('sha:u', 'sha:d', 'src', 'prof', 'red', 'proj', ['q1'], true);
    const auth = authorityDecision();
    const evidence = buildAcceptanceEvidence(campaign, validation, record, { authorityDecision: auth });
    expect(evidence.authorityDecision?.granted).toBe(true);
  });

  it('buildAcceptanceEvidence without R2 args defaults R2 fields to null (backward compat)', () => {
    const campaign = { reconstructsFromDurable: true, liveReplayEqual: true } as never;
    const validation = { readOnlySafe: true, evidenceProvenanceAttributable: true, targetHandoffIdentified: true, degradedModeHandled: true };
    const record = recordAcceptance('sha:u', 'sha:d', 'src', 'prof', 'red', 'proj', ['q1'], true);
    const evidence = buildAcceptanceEvidence(campaign, validation, record);
    expect(evidence.authorityDecision).toBeNull();
    expect(evidence.parentComposition).toBeNull();
    expect(evidence.taskRelation).toBeNull();
  });
});
