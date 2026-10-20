/**
 * CR-825-C — Duplicate idempotency + out-of-order handling + gap fail-closed.
 *
 * SCRUM-825 / DWO-V2-04, G2 EXECUTE, PLAN-825-R1, child run CR-825-C.
 *
 * Duplicate idempotency, out-of-order handling and gap fail-closed behavior
 * (AC-825-04). A duplicate event is applied once; an out-of-order event is
 * reordered deterministically; a gap fails closed (never fabricated).
 *
 * Design decisions:
 *  1. Duplicate idempotency: the same event_id applied twice yields the same state
 *     (the second application is a no-op).
 *  2. Out-of-order handling: events are applied in ordinal order regardless of
 *     arrival order.
 *  3. Gap fail-closed: a missing ordinal makes the watermark non-contiguous and the
 *     reconstruction is marked PARTIAL/UNKNOWN rather than fabricated.
 */

/** The result of applying an event with idempotency/order/gap handling. */
export interface ApplyResult {
  readonly applied: boolean;
  readonly duplicate: boolean;
  readonly outOfOrder: boolean;
  readonly stale: boolean;
  readonly gapDetected: boolean;
  readonly position: number;
}

/**
 * Apply an event to a durable log with idempotency + order + gap handling.
 *
 * Returns whether the event was applied, and flags for duplicate/out-of-order/gap.
 */
export function applyEvent(
  seenEventIds: ReadonlySet<string>,
  appliedOrdinals: ReadonlySet<number>,
  eventId: string,
  ordinal: number,
  expectedNextOrdinal: number,
): ApplyResult {
  if (seenEventIds.has(eventId)) {
    return { applied: false, duplicate: true, outOfOrder: false, stale: false, gapDetected: false, position: expectedNextOrdinal - 1 };
  }
  if (ordinal < expectedNextOrdinal) {
    // Stale: ordinal is below the applied watermark — already-applied region.
    return { applied: false, duplicate: false, outOfOrder: false, stale: true, gapDetected: false, position: expectedNextOrdinal - 1 };
  }
  if (appliedOrdinals.has(ordinal)) {
    return { applied: false, duplicate: true, outOfOrder: false, stale: false, gapDetected: false, position: expectedNextOrdinal - 1 };
  }
  if (ordinal > expectedNextOrdinal) {
    // Out-of-order arrival: ordinal is ahead of the expected next, creating a
    // future gap. The event is flagged for deterministic reordering, NOT stale.
    return { applied: false, duplicate: false, outOfOrder: true, stale: false, gapDetected: true, position: expectedNextOrdinal - 1 };
  }
  return { applied: true, duplicate: false, outOfOrder: false, stale: false, gapDetected: false, position: ordinal };
}

/** Idempotency/order/gap handling is read-only; it grants no effect capability. */
export interface IdempotencyCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const IDEMPOTENCY_CAPABILITIES: IdempotencyCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
