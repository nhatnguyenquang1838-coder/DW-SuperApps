/**
 * CR-828-A — Subscribe-after-bootstrap + reconnect durable catch-up.
 *
 * SCRUM-828 / DWO-V2-07, G2 EXECUTE, PLAN-828-R1, child run CR-828-A.
 *
 * Realtime subscribes ONLY after durable bootstrap, and reconnects with durable
 * catch-up before returning to LIVE (AC-828-03). Transport connectivity alone
 * never establishes certified LIVE (AC-828-02).
 *
 * Design decisions:
 *  1. A client subscribes only after the durable bootstrap completes.
 *  2. On reconnect, durable catch-up runs before the projection returns to LIVE.
 *  3. The projection state is BOOTSTRAPPING / CATCHING_UP / LIVE / DEGRADED /
 *     UNAVAILABLE.
 */

/** Realtime projection lifecycle states. */
export type RealtimeState =
  | 'BOOTSTRAPPING'
  | 'CATCHING_UP'
  | 'LIVE'
  | 'DEGRADED'
  | 'UNAVAILABLE';

/** The realtime bootstrap/catch-up controller. */
export interface RealtimeBootstrap {
  readonly state: RealtimeState;
  readonly bootstrapped: boolean;
  readonly caughtUp: boolean;
}

/** Initial state: not bootstrapped, not caught up. */
export function initialBootstrap(): RealtimeBootstrap {
  return { state: 'BOOTSTRAPPING', bootstrapped: false, caughtUp: false };
}

/**
 * Complete the durable bootstrap.
 *
 * Only after this may a client subscribe. Returns a bootstrapped controller still
 * in CATCHING_UP (not yet LIVE).
 */
export function completeBootstrap(b: RealtimeBootstrap): RealtimeBootstrap {
  return { state: 'CATCHING_UP', bootstrapped: true, caughtUp: false };
}

/**
 * Complete the reconnect durable catch-up.
 *
 * Only after this does the projection return to LIVE. Returns a LIVE controller.
 */
export function completeCatchUp(b: RealtimeBootstrap): RealtimeBootstrap {
  return { state: 'LIVE', bootstrapped: true, caughtUp: true };
}

/** Assert a client may subscribe (only after durable bootstrap). */
export function maySubscribe(b: RealtimeBootstrap): boolean {
  return b.bootstrapped === true;
}

/** Assert certified LIVE requires durable bootstrap + catch-up (not transport alone). */
export function isCertifiedLive(b: RealtimeBootstrap): boolean {
  return b.state === 'LIVE' && b.bootstrapped === true && b.caughtUp === true;
}

/** Realtime bootstrap is read-only; it grants no effect capability. */
export interface RealtimeBootstrapCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const REALTIME_BOOTSTRAP_CAPABILITIES: RealtimeBootstrapCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);