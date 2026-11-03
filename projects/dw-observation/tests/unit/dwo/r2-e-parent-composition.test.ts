/**
 * R2-E focused tests — ParentCompositionContractV2.
 *
 * The invariant under test throughout: a parent's gate position and its
 * children's success are NEVER sufficient. Composition requires its own
 * evidence, and target acceptance is a further, separate obligation.
 *
 * The negative cases are the point of the module. Each one sets up a parent
 * that looks complete by the old shortcut and asserts it stays unresolved.
 */

import { describe, expect, it } from 'vitest';
import {
  PARENT_COMPOSITION_CAPABILITIES,
  evaluateParentCompositionContract,
  isParentComposedUnderContract,
  type ParentCompositionContractV2,
} from '@/lib/dwo/parentComposition';

const G6_PASSED = { gate: 'G6', gateState: 'PASSED' } as const;

function contract(overrides: Partial<ParentCompositionContractV2> = {}): ParentCompositionContractV2 {
  return {
    parentRunId: 'PARENT-1',
    revisionId: 'rev-1',
    requiredChildren: [
      { runId: 'CHILD-A', completionDigest: 'sha256:child-a-done', handoffReceiptRef: 'receipt-a' },
      { runId: 'CHILD-B', completionDigest: 'sha256:child-b-done', handoffReceiptRef: 'receipt-b' },
    ],
    optionalChildren: [],
    requiredHandoffReceiptRefs: ['receipt-a', 'receipt-b'],
    parentVerificationRef: 'verify/parent-1.json',
    targetAcceptanceRef: 'accept/target-1.json',
    ...overrides,
  };
}

const PRESENT = ['receipt-a', 'receipt-b'];

describe('R2-E · fully proven contract → composed and accepted', () => {
  it('all obligations proven → composed + accepted', () => {
    const d = evaluateParentCompositionContract(contract(), G6_PASSED, PRESENT);
    expect(d.composed).toBe(true);
    expect(d.accepted).toBe(true);
    expect(d.reason).toBe('COMPOSED');
    expect(d.missingRefs).toEqual([]);
    expect(d.childCompletion).toEqual({ 'CHILD-A': true, 'CHILD-B': true });
  });

  it('no required children at all is still composable when the other proofs exist', () => {
    // A parent with no children is a legitimate shape; it still needs its own
    // verification and acceptance.
    const d = evaluateParentCompositionContract(
      contract({ requiredChildren: [], requiredHandoffReceiptRefs: [] }),
      G6_PASSED,
      [],
    );
    expect(d.composed).toBe(true);
    expect(d.accepted).toBe(true);
  });

  it('optional children never block composition', () => {
    const d = evaluateParentCompositionContract(
      contract({
        optionalChildren: [
          { runId: 'OPT-C', completionDigest: 'UNKNOWN', handoffReceiptRef: 'UNKNOWN' },
        ],
      }),
      G6_PASSED,
      PRESENT,
    );
    expect(d.composed).toBe(true);
    expect(d.accepted).toBe(true);
  });
});

describe('R2-E · child state never auto-completes the parent', () => {
  it('a parent at G6/PASSED with unproven children stays unresolved', () => {
    // The old shortcut: parent terminal ⇒ composed. Contract forbids it.
    const d = evaluateParentCompositionContract(
      contract({
        requiredChildren: [
          { runId: 'CHILD-A', completionDigest: 'sha256:child-a-done', handoffReceiptRef: 'UNKNOWN' },
          { runId: 'CHILD-B', completionDigest: 'sha256:child-b-done', handoffReceiptRef: 'receipt-b' },
        ],
      }),
      G6_PASSED,
      PRESENT,
    );
    expect(d.composed).toBe(false);
    expect(d.accepted).toBe(false);
    expect(d.reason).toBe('MISSING_CHILD_HANDOFF_RECEIPT');
    expect(d.missingRefs).toContain('child-handoff:CHILD-A');
    expect(isParentComposedUnderContract(d)).toBe(false);
  });

  it('a required child with no completion digest stays unresolved', () => {
    const d = evaluateParentCompositionContract(
      contract({
        requiredChildren: [
          { runId: 'CHILD-A', completionDigest: 'UNKNOWN', handoffReceiptRef: 'receipt-a' },
          { runId: 'CHILD-B', completionDigest: 'sha256:child-b-done', handoffReceiptRef: 'receipt-b' },
        ],
      }),
      G6_PASSED,
      PRESENT,
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_CHILD_COMPLETION_DIGEST');
    expect(d.childCompletion['CHILD-A']).toBe(false);
  });

  it('a required child whose digest disagrees with the authoritative record fails', () => {
    const d = evaluateParentCompositionContract(
      contract(),
      G6_PASSED,
      PRESENT,
      { 'CHILD-A': 'sha256:something-else' },
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('CHILD_DIGEST_MISMATCH');
    expect(d.missingRefs).toContain('child-digest-mismatch:CHILD-A');
  });

  it('a matching authoritative child digest still composes', () => {
    const d = evaluateParentCompositionContract(
      contract(),
      G6_PASSED,
      PRESENT,
      { 'CHILD-A': 'sha256:child-a-done', 'CHILD-B': 'sha256:child-b-done' },
    );
    expect(d.composed).toBe(true);
  });
});

describe('R2-E · handoff receipts are explicit obligations', () => {
  it('a required receipt that does not exist blocks composition', () => {
    const d = evaluateParentCompositionContract(contract(), G6_PASSED, ['receipt-a']);
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_REQUIRED_RECEIPT');
    expect(d.missingRefs).toContain('required-receipt:receipt-b');
  });

  it('per-child receipts do not substitute for the contract receipt set', () => {
    // Both children name receipt-a; the contract also requires receipt-b.
    const d = evaluateParentCompositionContract(
      contract({
        requiredChildren: [
          { runId: 'CHILD-A', completionDigest: 'sha256:a', handoffReceiptRef: 'receipt-a' },
          { runId: 'CHILD-B', completionDigest: 'sha256:b', handoffReceiptRef: 'receipt-a' },
        ],
      }),
      G6_PASSED,
      ['receipt-a'],
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_REQUIRED_RECEIPT');
  });

  it('a blank receipt ref in the contract is unresolved, not waived', () => {
    const d = evaluateParentCompositionContract(
      contract({ requiredHandoffReceiptRefs: ['receipt-a', ''] }),
      G6_PASSED,
      PRESENT,
    );
    expect(d.composed).toBe(false);
    expect(d.missingRefs).toContain('required-receipt:<empty>');
  });

  it('a blank child id in the required set is unresolved', () => {
    const d = evaluateParentCompositionContract(
      contract({
        requiredChildren: [
          { runId: '', completionDigest: 'sha256:a', handoffReceiptRef: 'receipt-a' },
        ],
      }),
      G6_PASSED,
      PRESENT,
    );
    expect(d.composed).toBe(false);
    expect(d.missingRefs).toContain('required-child:<empty>');
  });
});

describe('R2-E · parent verification and target acceptance are separate', () => {
  it('all children proven but no parent verification → unresolved', () => {
    const d = evaluateParentCompositionContract(
      contract({ parentVerificationRef: 'UNKNOWN' }),
      G6_PASSED,
      PRESENT,
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_PARENT_VERIFICATION');
  });

  it('parent verification proven but target acceptance absent → composed, not accepted', () => {
    // The distinction the contract exists to preserve: the composed artifact
    // exists, but the target has not taken it.
    const d = evaluateParentCompositionContract(
      contract({ targetAcceptanceRef: 'UNKNOWN' }),
      G6_PASSED,
      PRESENT,
    );
    expect(d.composed).toBe(true);
    expect(d.accepted).toBe(false);
    expect(d.reason).toBe('COMPOSITION_COMPLETE_NOT_ACCEPTED');
    expect(d.missingRefs).toContain('targetAcceptanceRef');
    expect(isParentComposedUnderContract(d)).toBe(true);
  });

  it('child success never supplies parent verification', () => {
    const d = evaluateParentCompositionContract(
      contract({ parentVerificationRef: '' }),
      G6_PASSED,
      PRESENT,
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_PARENT_VERIFICATION');
  });
});

describe('R2-E · the parent gate position is not an input to composition', () => {
  it('a parent at G2/ACTIVE with full evidence still composes', () => {
    // Gate position is context; the contract evidence is what composes.
    const d = evaluateParentCompositionContract(
      contract(),
      { gate: 'G2', gateState: 'ACTIVE' },
      PRESENT,
    );
    expect(d.composed).toBe(true);
  });

  it('a parent at G6/PASSED with no contract evidence does NOT compose', () => {
    const d = evaluateParentCompositionContract(
      contract({
        parentVerificationRef: 'UNKNOWN',
        targetAcceptanceRef: 'UNKNOWN',
        requiredChildren: [],
        requiredHandoffReceiptRefs: [],
      }),
      G6_PASSED,
      [],
    );
    expect(d.composed).toBe(false);
    expect(d.accepted).toBe(false);
  });

  it('an unknown parent gate position is reported as unresolved state', () => {
    const d = evaluateParentCompositionContract(
      contract(),
      { gate: 'UNKNOWN', gateState: 'UNKNOWN' },
      PRESENT,
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_PARENT_STATE');
  });
});

describe('R2-E · the contract must identify itself', () => {
  it('a missing revision id is unresolved', () => {
    const d = evaluateParentCompositionContract(
      contract({ revisionId: 'UNKNOWN' }),
      G6_PASSED,
      PRESENT,
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_REVISION_ID');
  });

  it('a missing parent run id is unresolved', () => {
    const d = evaluateParentCompositionContract(
      contract({ parentRunId: '' }),
      G6_PASSED,
      PRESENT,
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_REVISION_ID');
  });
});

describe('R2-E · capability marker', () => {
  it('read-only, no effect affordance', () => {
    expect(PARENT_COMPOSITION_CAPABILITIES).toEqual({
      read: true,
      write: false,
      approve: false,
      deny: false,
      merge: false,
      deploy: false,
    });
    expect(Object.isFrozen(PARENT_COMPOSITION_CAPABILITIES)).toBe(true);
  });
});
