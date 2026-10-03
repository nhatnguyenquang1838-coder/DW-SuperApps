/**
 * CR-828-B — Duplicate/stale/out-of-order transport handling.
 *
 * SCRUM-828 / DWO-V2-07, G2 EXECUTE, PLAN-828-R1, child run CR-828-B.
 *
 * Realtime transport events are handled for duplicates, staleness and
 * out-of-order arrival. This reuses the idempotency/order/gap logic from SCRUM-825.
 *
 * Design decisions:
 *  1. A duplicate transport event is a no-op.
 *  2. A stale event (ordinal below the applied watermark) is dropped.
 *  3. An out-of-order event is flagged; the projection stays consistent via durable
 *     catch-up.
 */

import { applyEvent } from './idempotency';

/** The result of handling a transport event. */
export interface TransportHandlingResult {
  readonly applied: boolean;
  readonly duplicate: boolean;
  readonly stale: boolean;
  readonly outOfOrder: boolean;
}

/**
 * Handle a transport event with duplicate/stale/out-of-order detection.
 *
 * Reuses applyEvent from SCRUM-825 idempotency. A stale event (ordinal below the
 * expected next) is dropped; a duplicate is a no-op.
 */
export function handleTransportEvent(
  seenEventIds: ReadonlySet<string>,
  appliedOrdinals: ReadonlySet<number>,
  eventId: string,
  ordinal: number,
  expectedNextOrdinal: number,
): TransportHandlingResult {
  const result = applyEvent(seenEventIds, appliedOrdinals, eventId, ordinal, expectedNextOrdinal);
  return {
    applied: result.applied,
    duplicate: result.duplicate,
    stale: result.outOfOrder, // ordinal below expected = stale
    outOfOrder: result.outOfOrder,
  };
}

/** Realtime transport is read-only; it grants no effect capability. */
export interface RealtimeTransportCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const REALTIME_TRANSPORT_CAPABILITIES: RealtimeTransportCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);