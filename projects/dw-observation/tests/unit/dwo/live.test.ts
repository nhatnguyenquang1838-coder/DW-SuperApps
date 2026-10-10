/**
 * CR-828-A/B/C/D verification — realtime reconciled LIVE.
 *
 * AC-828-01 V2_LIVE_PROJECTION_READY derivable
 * AC-828-02 transport connectivity alone cannot establish certified LIVE
 * AC-828-03 reconnect/gap scenarios converge from durable history
 * AC-828-04 DEGRADED and UNAVAILABLE projection states correct
 * AC-828-05 certified Live requires current valid semantic qualification bound to subject
 */
import { describe, expect, it } from 'vitest';
import {
  REALTIME_BOOTSTRAP_CAPABILITIES,
  completeBootstrap,
  completeCatchUp,
  initialBootstrap,
  isCertifiedLive as isBootstrapCertifiedLive,
  maySubscribe,
} from '@/lib/dwo/realtimeBootstrap';
import {
  REALTIME_TRANSPORT_CAPABILITIES,
  handleTransportEvent,
} from '@/lib/dwo/realtimeTransport';
import {
  LIVE_STATE_CAPABILITIES,
  determineLiveState,
  isCertifiedLive,
  type SemanticQualification,
} from '@/lib/dwo/liveState';
import {
  LIVE_CERTIFICATION_CAPABILITIES,
  buildLiveProjectionEvidence,
  deriveV2LiveProjectionReady,
  type LiveProjectionReadyInput,
} from '@/lib/dwo/liveCertification';

function liveInput(overrides: Partial<LiveProjectionReadyInput> = {}): LiveProjectionReadyInput {
  return {
    transportAloneNotCertified: true,
    reconnectConvergesFromDurable: true,
    degradedUnavailableCorrect: true,
    qualificationGateCorrect: true,
    ...overrides,
  };
}

describe('AC-828-02 · transport connectivity alone cannot establish certified LIVE', () => {
  it('a client may subscribe only after durable bootstrap', () => {
    expect(maySubscribe(initialBootstrap())).toBe(false);
    expect(maySubscribe(completeBootstrap(initialBootstrap()))).toBe(true);
  });

  it('transport connectivity alone (no bootstrap) is not certified LIVE', () => {
    const transportOnly = { state: 'LIVE' as const, bootstrapped: false, caughtUp: false };
    expect(isBootstrapCertifiedLive(transportOnly)).toBe(false);
  });

  it('certified LIVE requires bootstrap + catch-up', () => {
    const bootstrapped = completeBootstrap(initialBootstrap());
    expect(isBootstrapCertifiedLive(bootstrapped)).toBe(false); // CATCHING_UP
    const live = completeCatchUp(bootstrapped);
    expect(isBootstrapCertifiedLive(live)).toBe(true);
  });
});

describe('AC-828-03 · reconnect/gap scenarios converge from durable history', () => {
  it('reconnect runs durable catch-up before returning to LIVE', () => {
    const b = completeBootstrap(initialBootstrap());
    expect(b.state).toBe('CATCHING_UP');
    const live = completeCatchUp(b);
    expect(live.state).toBe('LIVE');
    expect(live.caughtUp).toBe(true);
  });
});

describe('AC-828-04 · DEGRADED and UNAVAILABLE projection states correct', () => {
  it('is UNAVAILABLE when transport is down beyond retention', () => {
    const b = completeCatchUp(completeBootstrap(initialBootstrap()));
    expect(determineLiveState(b, false, true)).toBe('UNAVAILABLE');
  });

  it('is DEGRADED when transport available but catch-up incomplete', () => {
    const b = completeBootstrap(initialBootstrap());
    expect(determineLiveState(b, true, false)).toBe('DEGRADED');
  });

  it('is LIVE when transport available and caught up', () => {
    const b = completeCatchUp(completeBootstrap(initialBootstrap()));
    expect(determineLiveState(b, true, false)).toBe('LIVE');
  });
});

describe('AC-828-05 · certified Live requires current valid semantic qualification bound to subject', () => {
  const qualified: SemanticQualification = { subject: 'SUBJ', status: 'QUALIFIED', valid: true };

  it('is certified LIVE only with valid qualification bound to the subject', () => {
    expect(isCertifiedLive('LIVE', qualified, 'SUBJ')).toBe(true);
  });

  it('is NOT certified when qualification is PENDING', () => {
    expect(isCertifiedLive('LIVE', { subject: 'SUBJ', status: 'PENDING', valid: true }, 'SUBJ')).toBe(false);
  });

  it('is NOT certified when qualification is bound to a different subject', () => {
    expect(isCertifiedLive('LIVE', qualified, 'OTHER')).toBe(false);
  });

  it('is NOT certified when qualification is invalid', () => {
    expect(isCertifiedLive('LIVE', { subject: 'SUBJ', status: 'QUALIFIED', valid: false }, 'SUBJ')).toBe(false);
  });

  it('is NOT certified when the state is not LIVE', () => {
    expect(isCertifiedLive('DEGRADED', qualified, 'SUBJ')).toBe(false);
  });
});

describe('transport handling — duplicate/stale/out-of-order', () => {
  it('a duplicate transport event is a no-op', () => {
    const r = handleTransportEvent(new Set(['E1']), new Set([1]), 'E1', 1, 2);
    expect(r.applied).toBe(false);
    expect(r.duplicate).toBe(true);
  });

  it('a stale event (ordinal below expected) is dropped', () => {
    const r = handleTransportEvent(new Set(), new Set([1]), 'E2', 1, 2);
    expect(r.applied).toBe(false);
    expect(r.stale).toBe(true);
  });

  it('an in-order event is applied', () => {
    const r = handleTransportEvent(new Set(), new Set(), 'E1', 1, 1);
    expect(r.applied).toBe(true);
  });

  it('an out-of-order arrival (ordinal above expected) is flagged, not stale', () => {
    // GPT defect: ordinal > expectedNextOrdinal was treated as a stale drop in
    // the realtime layer. It is an out-of-order arrival creating a future gap;
    // stale must be false so it routes to reorder/catch-up, not drop.
    const r = handleTransportEvent(new Set(), new Set(), 'E2', 3, 1);
    expect(r.applied).toBe(false);
    expect(r.outOfOrder).toBe(true);
    expect(r.stale).toBe(false);
  });

  it('a stale event (ordinal below watermark) is neither out-of-order nor applied', () => {
    const r = handleTransportEvent(new Set(), new Set([1]), 'E2', 1, 2);
    expect(r.applied).toBe(false);
    expect(r.stale).toBe(true);
    expect(r.outOfOrder).toBe(false);
  });
});

describe('AC-828-01 · V2_LIVE_PROJECTION_READY derivation', () => {
  it('derives the token from a coherent realtime layer', () => {
    const decision = deriveV2LiveProjectionReady(liveInput());
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_LIVE_PROJECTION_READY');
    expect(decision.reasons).toEqual([]);
  });

  it('derives from the live module evidence', () => {
    const evidence = buildLiveProjectionEvidence();
    const decision = deriveV2LiveProjectionReady(evidence);
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_LIVE_PROJECTION_READY');
  });

  it('fails closed when transport alone establishes certified LIVE', () => {
    expect(deriveV2LiveProjectionReady(liveInput({ transportAloneNotCertified: false })).derivable).toBe(false);
  });

  it('fails closed when reconnect does not converge from durable history', () => {
    expect(deriveV2LiveProjectionReady(liveInput({ reconnectConvergesFromDurable: false })).derivable).toBe(false);
  });
});

describe('capabilities — realtime modules are read-only', () => {
  it('exposes no effect capability anywhere', () => {
    for (const caps of [REALTIME_BOOTSTRAP_CAPABILITIES, REALTIME_TRANSPORT_CAPABILITIES, LIVE_STATE_CAPABILITIES, LIVE_CERTIFICATION_CAPABILITIES]) {
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