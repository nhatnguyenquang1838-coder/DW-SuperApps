/**
 * R2-D focused tests — authoritative authority-state vocabulary.
 *
 * The two invariants under test are the ones most easily violated by
 * convenience code:
 *   1. absence of a record must NEVER resolve to DENIED;
 *   2. incomplete evidence must NEVER resolve to GRANTED.
 *
 * Every negative case asserts the state is UNKNOWN specifically, not merely
 * "not GRANTED" — collapsing both failures into DENIED is the defect this
 * vocabulary exists to make impossible.
 */

import { describe, expect, it } from 'vitest';
import {
  AUTHORITY_STATES,
  AUTHORITY_VOCABULARY_CAPABILITIES,
  deriveAuthorityState,
  isAuthorityGranted,
  type AuthorityEvidence,
} from '@/lib/dwo/authorityVocabulary';

const NOW = '2026-10-01T12:00:00.000Z';

function evidence(overrides: Partial<AuthorityEvidence> = {}): AuthorityEvidence {
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

describe('R2-D · vocabulary is closed and exact', () => {
  it('exposes exactly the seven authoritative states', () => {
    expect([...AUTHORITY_STATES]).toEqual([
      'PENDING',
      'GRANTED',
      'DENIED',
      'EXPIRED',
      'REVOKED',
      'NOT_REQUIRED',
      'UNKNOWN',
    ]);
  });

  it('an out-of-vocabulary state is UNKNOWN, never coerced to a neighbour', () => {
    const d = deriveAuthorityState(evidence({ assertedState: 'APPROVED' }), NOW);
    expect(d.state).toBe('UNKNOWN');
    expect(d.reason).toBe('UNKNOWN_UNSUPPORTED_STATE');
    expect(d.granted).toBe(false);
  });

  it('a lowercase state is out-of-vocabulary (vocabulary is case-exact)', () => {
    const d = deriveAuthorityState(evidence({ assertedState: 'granted' }), NOW);
    expect(d.state).toBe('UNKNOWN');
    expect(d.reason).toBe('UNKNOWN_UNSUPPORTED_STATE');
  });
});

describe('R2-D · absence never becomes DENIED', () => {
  it('a missing record is UNKNOWN, not DENIED', () => {
    expect(deriveAuthorityState(null, NOW).state).toBe('UNKNOWN');
    expect(deriveAuthorityState(undefined, NOW).state).toBe('UNKNOWN');
    expect(deriveAuthorityState(null, NOW).reason).toBe('UNKNOWN_NO_ASSERTION');
  });

  it('an empty-string state is UNKNOWN, not DENIED', () => {
    const d = deriveAuthorityState(evidence({ assertedState: '' }), NOW);
    expect(d.state).toBe('UNKNOWN');
    expect(d.state).not.toBe('DENIED');
  });

  it('an explicit UNKNOWN assertion stays UNKNOWN', () => {
    const d = deriveAuthorityState(evidence({ assertedState: 'UNKNOWN' }), NOW);
    expect(d.state).toBe('UNKNOWN');
    expect(d.reason).toBe('UNKNOWN_UNRESOLVED');
  });

  it('an unestablished state token is UNKNOWN, not DENIED', () => {
    const d = deriveAuthorityState(evidence({ assertedState: 'UNKNOWN' }), NOW);
    expect(d.state).toBe('UNKNOWN');
  });
});

describe('R2-D · incomplete evidence never becomes GRANTED', () => {
  it('missing source identity → UNKNOWN', () => {
    const d = deriveAuthorityState(evidence({ sourceIdentity: 'UNKNOWN' }), NOW);
    expect(d.state).toBe('UNKNOWN');
    expect(d.reason).toBe('UNKNOWN_INCOMPLETE_EVIDENCE');
    expect(d.granted).toBe(false);
  });

  it('missing scope → UNKNOWN', () => {
    const d = deriveAuthorityState(evidence({ scope: '' }), NOW);
    expect(d.state).toBe('UNKNOWN');
    expect(d.reason).toBe('UNKNOWN_INCOMPLETE_EVIDENCE');
  });

  it('missing source digest → UNKNOWN', () => {
    const d = deriveAuthorityState(evidence({ sourceDigest: 'UNKNOWN' }), NOW);
    expect(d.state).toBe('UNKNOWN');
    expect(d.reason).toBe('UNKNOWN_INCOMPLETE_EVIDENCE');
  });

  it('incomplete evidence is UNKNOWN, never DENIED either', () => {
    // The second failure mode: collapsing "we cannot prove it" into "no".
    for (const override of [{ sourceIdentity: 'UNKNOWN' }, { scope: '' }, { sourceDigest: '' }]) {
      const d = deriveAuthorityState(evidence(override), NOW);
      expect(d.state).toBe('UNKNOWN');
      expect(d.state).not.toBe('DENIED');
    }
  });

  it('an unknown clock on a GRANTED claim → UNKNOWN, not GRANTED', () => {
    const d = deriveAuthorityState(evidence({ assertedState: 'GRANTED' }), 'UNKNOWN');
    expect(d.state).toBe('UNKNOWN');
    expect(d.granted).toBe(false);
  });

  it('unparseable time evidence on a GRANTED claim → UNKNOWN', () => {
    const d = deriveAuthorityState(
      evidence({ assertedState: 'GRANTED', expiresAt: 'not-a-date' }),
      NOW,
    );
    expect(d.state).toBe('UNKNOWN');
    expect(d.reason).toBe('UNKNOWN_INVALID_TIME_EVIDENCE');
  });

  it('an incoherent window (expires before asserted) → UNKNOWN', () => {
    const d = deriveAuthorityState(
      evidence({
        assertedState: 'GRANTED',
        assertedAt: '2026-10-01T14:00:00.000Z',
        expiresAt: '2026-10-01T10:00:00.000Z',
      }),
      NOW,
    );
    expect(d.state).toBe('UNKNOWN');
    expect(d.reason).toBe('UNKNOWN_INVALID_TIME_EVIDENCE');
  });
});

describe('R2-D · GRANTED requires source, scope and time evidence', () => {
  it('full evidence inside the window → GRANTED', () => {
    const d = deriveAuthorityState(evidence({ assertedState: 'GRANTED' }), NOW);
    expect(d.state).toBe('GRANTED');
    expect(d.reason).toBe('AUTHORITY_GRANTED');
    expect(d.granted).toBe(true);
    expect(isAuthorityGranted(d)).toBe(true);
  });

  it('a GRANTED claim asserted at the very edge of the window still holds', () => {
    const d = deriveAuthorityState(
      evidence({
        assertedState: 'GRANTED',
        assertedAt: '2026-10-01T10:00:00.000Z',
        expiresAt: '2026-10-01T12:00:01.000Z',
      }),
      NOW,
    );
    expect(d.state).toBe('GRANTED');
  });

  it('a lapsed window → EXPIRED (a known terminal fact, not UNKNOWN)', () => {
    const d = deriveAuthorityState(
      evidence({
        assertedState: 'GRANTED',
        assertedAt: '2026-10-01T08:00:00.000Z',
        expiresAt: '2026-10-01T11:00:00.000Z',
      }),
      NOW,
    );
    expect(d.state).toBe('EXPIRED');
    expect(d.reason).toBe('AUTHORITY_EXPIRED');
    expect(d.granted).toBe(false);
    expect(isAuthorityGranted(d)).toBe(false);
  });

  it('exactly at expiry is EXPIRED, not GRANTED', () => {
    const d = deriveAuthorityState(
      evidence({
        assertedState: 'GRANTED',
        assertedAt: '2026-10-01T10:00:00.000Z',
        expiresAt: NOW,
      }),
      NOW,
    );
    expect(d.state).toBe('EXPIRED');
  });

  it('an asserted EXPIRED contradicted by a still-open clock → UNKNOWN', () => {
    // Source record and clock disagree. Fail closed rather than pick a side.
    const d = deriveAuthorityState(
      evidence({
        assertedState: 'EXPIRED',
        assertedAt: '2026-10-01T10:00:00.000Z',
        expiresAt: '2026-10-01T20:00:00.000Z',
      }),
      NOW,
    );
    expect(d.state).toBe('UNKNOWN');
    expect(d.reason).toBe('UNKNOWN_UNRESOLVED');
  });
});

describe('R2-D · DENIED and REVOKED are source-backed assertions', () => {
  it('an explicit DENIED with full evidence → DENIED', () => {
    const d = deriveAuthorityState(evidence({ assertedState: 'DENIED' }), NOW);
    expect(d.state).toBe('DENIED');
    expect(d.reason).toBe('AUTHORITY_DENIED');
    expect(d.granted).toBe(false);
  });

  it('DENIED without a source identity → UNKNOWN, not DENIED', () => {
    // A refusal with no attributable source is not a refusal we can act on.
    const d = deriveAuthorityState(
      evidence({ assertedState: 'DENIED', sourceIdentity: 'UNKNOWN' }),
      NOW,
    );
    expect(d.state).toBe('UNKNOWN');
    expect(d.state).not.toBe('DENIED');
  });

  it('an explicit REVOKED with full evidence → REVOKED', () => {
    const d = deriveAuthorityState(evidence({ assertedState: 'REVOKED' }), NOW);
    expect(d.state).toBe('REVOKED');
    expect(d.reason).toBe('AUTHORITY_REVOKED');
  });

  it('REVOKED without a source digest → UNKNOWN', () => {
    const d = deriveAuthorityState(
      evidence({ assertedState: 'REVOKED', sourceDigest: '' }),
      NOW,
    );
    expect(d.state).toBe('UNKNOWN');
  });
});

describe('R2-D · states that describe absence of a decision', () => {
  it('PENDING needs only a scope → PENDING', () => {
    const d = deriveAuthorityState(
      {
        sourceIdentity: 'UNKNOWN',
        sourceDigest: 'UNKNOWN',
        scope: 'merge_to_main',
        assertedAt: 'UNKNOWN',
        expiresAt: 'UNKNOWN',
        assertedState: 'PENDING',
      },
      NOW,
    );
    expect(d.state).toBe('PENDING');
    expect(d.reason).toBe('AUTHORITY_PENDING');
  });

  it('PENDING without a scope → UNKNOWN (an unscoped statement is about nothing)', () => {
    const d = deriveAuthorityState(
      {
        sourceIdentity: 'UNKNOWN',
        sourceDigest: 'UNKNOWN',
        scope: '',
        assertedAt: 'UNKNOWN',
        expiresAt: 'UNKNOWN',
        assertedState: 'PENDING',
      },
      NOW,
    );
    expect(d.state).toBe('UNKNOWN');
    expect(d.reason).toBe('UNKNOWN_INCOMPLETE_EVIDENCE');
  });

  it('NOT_REQUIRED needs only a scope → NOT_REQUIRED', () => {
    const d = deriveAuthorityState(
      {
        sourceIdentity: 'UNKNOWN',
        sourceDigest: 'UNKNOWN',
        scope: 'preview_only_env',
        assertedAt: 'UNKNOWN',
        expiresAt: 'UNKNOWN',
        assertedState: 'NOT_REQUIRED',
      },
      NOW,
    );
    expect(d.state).toBe('NOT_REQUIRED');
    expect(d.reason).toBe('AUTHORITY_NOT_REQUIRED');
    expect(d.granted).toBe(false);
  });

  it('NOT_REQUIRED never grants a gate', () => {
    const d = deriveAuthorityState(
      {
        sourceIdentity: 'UNKNOWN',
        sourceDigest: 'UNKNOWN',
        scope: 'preview_only_env',
        assertedAt: 'UNKNOWN',
        expiresAt: 'UNKNOWN',
        assertedState: 'NOT_REQUIRED',
      },
      NOW,
    );
    expect(isAuthorityGranted(d)).toBe(false);
  });
});

describe('R2-D · gate guard', () => {
  it('isAuthorityGranted is false for every non-GRANTED state', () => {
    const nonGranted = [
      deriveAuthorityState(null, NOW),
      deriveAuthorityState(evidence({ assertedState: 'DENIED' }), NOW),
      deriveAuthorityState(evidence({ assertedState: 'REVOKED' }), NOW),
      deriveAuthorityState(
        evidence({ assertedState: 'GRANTED', expiresAt: '2026-10-01T11:00:00.000Z' }),
        NOW,
      ),
      deriveAuthorityState(evidence({ assertedState: 'PENDING', scope: 's' }), NOW),
    ];
    for (const d of nonGranted) {
      expect(isAuthorityGranted(d)).toBe(false);
    }
  });
});

describe('R2-D · capability marker', () => {
  it('read-only, no effect affordance', () => {
    expect(AUTHORITY_VOCABULARY_CAPABILITIES).toEqual({
      read: true,
      write: false,
      approve: false,
      deny: false,
      merge: false,
      deploy: false,
    });
    expect(Object.isFrozen(AUTHORITY_VOCABULARY_CAPABILITIES)).toBe(true);
  });
});
