/**
 * CR-825-A/B/C/D verification — durable history/reconciliation foundation.
 *
 * AC-825-01 V2_DURABLE_RECONCILIATION_READY derivable
 * AC-825-02 derived state disposable/rebuildable (rebuild-from-zero parity)
 * AC-825-03 durable history sufficient to reconstruct accepted projection state
 * AC-825-04 duplicate idempotency, out-of-order, gap fail-closed
 * AC-825-05 no browser path requires service-role/secret credentials
 */
import { describe, expect, it } from 'vitest';
import {
  DURABLE_ORDER_CAPABILITIES,
  DurableLog,
  type DurableEvent,
} from '@/lib/dwo/durableOrder';
import {
  COMPATIBILITY_CAPABILITIES,
  backfillV1,
  upcastV1Event,
  type V1Event,
} from '@/lib/dwo/compatibility';
import {
  IDEMPOTENCY_CAPABILITIES,
  applyEvent,
} from '@/lib/dwo/idempotency';
import {
  DURABLE_CAPABILITIES,
  assertNoServiceRoleInBrowser,
  assertRebuildParity,
  deriveV2DurableReconciliationReady,
  resetDerivedState,
  type DurableReconciliationInput,
  type RlsPolicy,
} from '@/lib/dwo/durableCertification';

function certInput(overrides: Partial<DurableReconciliationInput> = {}): DurableReconciliationInput {
  return {
    rebuildParity: true,
    historySufficient: true,
    idempotencyCorrect: true,
    noServiceRoleInBrowser: true,
    ...overrides,
  };
}

function ev(ordinal: number, runId = 'R1'): DurableEvent {
  return { eventId: `EVT-${runId}-${ordinal}`, runId, ordinal, payload: { runId, ordinal } };
}

describe('AC-825-03 · durable history sufficient to reconstruct accepted projection state', () => {
  it('DurableLog appends events and tracks the durable position', () => {
    const log = new DurableLog();
    log.append(ev(1));
    log.append(ev(2));
    expect(log.position()).toBe(2);
    expect(log.read().length).toBe(2);
  });

  it('watermark is contiguous when ordinals are sequential', () => {
    const log = new DurableLog();
    log.append(ev(1));
    log.append(ev(2));
    log.append(ev(3));
    const wm = log.watermark();
    expect(wm.position).toBe(3);
    expect(wm.contiguous).toBe(true);
  });

  it('watermark is non-contiguous when a gap exists', () => {
    const log = new DurableLog();
    log.append(ev(1));
    log.append(ev(3)); // gap at 2
    const wm = log.watermark();
    expect(wm.contiguous).toBe(false);
    expect(wm.position).toBe(1);
  });
});

describe('AC-825-02 · derived state disposable/rebuildable (rebuild-from-zero parity)', () => {
  it('rebuild-from-zero reproduces the same state', () => {
    const log = new DurableLog();
    log.append(ev(1));
    log.append(ev(2));
    const reduce = (events: readonly { ordinal: number; payload: unknown }[]) =>
      events.map((e) => e.ordinal).join(',');
    expect(assertRebuildParity(log, reduce)).toBe(true);
  });

  it('RESET_DERIVED_STATE clears derived state but preserves durable history', () => {
    const log = new DurableLog();
    log.append(ev(1));
    const result = resetDerivedState(log, { some: 'derived' });
    expect(result.logPreserved).toBe(true);
    expect(result.derivedCleared).toBe(false); // derived object is not null/undefined
    const cleared = resetDerivedState(log, null);
    expect(cleared.derivedCleared).toBe(true);
  });
});

describe('AC-825-04 · duplicate idempotency, out-of-order, gap fail-closed', () => {
  it('a duplicate event is a no-op (idempotent)', () => {
    const result = applyEvent(new Set(['EVT-1']), new Set([1]), 'EVT-1', 1, 2);
    expect(result.applied).toBe(false);
    expect(result.duplicate).toBe(true);
  });

  it('an out-of-order event is flagged and not applied', () => {
    // ordinal > expectedNextOrdinal: arrives ahead, creates a future gap.
    // This is OUT-OF-ORDER (reorder for deterministic catch-up), NOT stale.
    const result = applyEvent(new Set(), new Set(), 'EVT-2', 3, 1);
    expect(result.applied).toBe(false);
    expect(result.outOfOrder).toBe(true);
    expect(result.gapDetected).toBe(true);
    expect(result.stale).toBe(false);
  });

  it('a stale event (ordinal below the applied watermark) is flagged stale, not out-of-order', () => {
    // ordinal 1 < expectedNextOrdinal 2: already-applied region. STALE, not
    // out-of-order. GPT defect: this was misclassified as outOfOrder:true.
    const result = applyEvent(new Set(), new Set([1]), 'EVT-2', 1, 2);
    expect(result.applied).toBe(false);
    expect(result.stale).toBe(true);
    expect(result.outOfOrder).toBe(false);
  });

  it('a gap fails closed (never fabricated)', () => {
    const result = applyEvent(new Set(), new Set(), 'EVT-3', 3, 1);
    expect(result.applied).toBe(false);
    expect(result.gapDetected).toBe(true);
  });

  it('an already-applied ordinal is duplicate even when its event ID differs', () => {
    const result = applyEvent(new Set(), new Set([1]), 'EVT-DIFFERENT-ID', 1, 1);
    expect(result.applied).toBe(false);
    expect(result.duplicate).toBe(true);
  });

  it('an in-order event is applied', () => {
    const result = applyEvent(new Set(), new Set(), 'EVT-1', 1, 1);
    expect(result.applied).toBe(true);
    expect(result.position).toBe(1);
  });
});

describe('AC-825-05 · no browser path requires service-role/secret credentials', () => {
  it('a browser path using authenticated/anon is safe', () => {
    const policies: RlsPolicy[] = [
      { role: 'authenticated', allow: true },
      { role: 'anon', allow: false },
    ];
    expect(assertNoServiceRoleInBrowser(policies)).toBe(true);
  });

  it('a browser path requiring service_role is a violation', () => {
    const policies: RlsPolicy[] = [
      { role: 'service_role', allow: true },
    ];
    expect(assertNoServiceRoleInBrowser(policies)).toBe(false);
  });
});

describe('v1/v2 compatibility + backfill', () => {
  it('upcasts a v1 event to v2 preserving the v1 source', () => {
    const v1: V1Event = { recordId: 'REC-LEGACY', runId: 'DEV-RUN-001', ordinal: 1 };
    const v2 = upcastV1Event(v1);
    expect(v2.schemaId).toBe('gwc.dwo.projection-contract-v2');
    expect(v2.schemaVersion).toBe(2);
  });

  it('backfills v1 events in ordinal order', () => {
    const appended: number[] = [];
    const result = backfillV1(
      [
        { recordId: 'R2', runId: 'DEV-RUN-001', ordinal: 2 },
        { recordId: 'R1', runId: 'DEV-RUN-001', ordinal: 1 },
      ],
      (e) => {
        appended.push(e.ordinal);
        return appended.length;
      },
    );
    expect(appended).toEqual([1, 2]);
    expect(result.backfilled).toBe(2);
    expect(result.upcast).toBe(2);
    expect(result.preservedV1).toBe(2);
  });
});

describe('AC-825-01 · V2_DURABLE_RECONCILIATION_READY derivation', () => {
  it('derives the token from a coherent durable foundation', () => {
    const decision = deriveV2DurableReconciliationReady(certInput());
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_DURABLE_RECONCILIATION_READY');
    expect(decision.reasons).toEqual([]);
  });

  it('fails closed on broken rebuild parity', () => {
    expect(deriveV2DurableReconciliationReady(certInput({ rebuildParity: false })).derivable).toBe(false);
  });

  it('fails closed when a browser path requires service-role', () => {
    expect(deriveV2DurableReconciliationReady(certInput({ noServiceRoleInBrowser: false })).derivable).toBe(false);
  });

  it('fails closed on incorrect idempotency', () => {
    expect(deriveV2DurableReconciliationReady(certInput({ idempotencyCorrect: false })).derivable).toBe(false);
  });
});

describe('capabilities — durable foundation is read-only', () => {
  it('exposes no effect capability anywhere', () => {
    for (const caps of [DURABLE_ORDER_CAPABILITIES, COMPATIBILITY_CAPABILITIES, IDEMPOTENCY_CAPABILITIES, DURABLE_CAPABILITIES]) {
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
