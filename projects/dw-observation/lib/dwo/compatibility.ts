/**
 * CR-825-B — v1/v2 compatibility + backfill fixtures.
 *
 * SCRUM-825 / DWO-V2-04, G2 EXECUTE, PLAN-825-R1, child run CR-825-B.
 *
 * v1/v2 compatibility and backfill. Legacy v1 projection events are upcast to v2
 * (via the Projection Contract v2 upcast rules) and backfilled into the durable
 * log so historical semantic integrity is preserved.
 *
 * Design decisions:
 *  1. A v1 event is upcast to v2 using the registered upcast rules; the v1 source
 *     is preserved (immutable history).
 *  2. Backfill appends upcast v2 events to the durable log in deterministic order.
 *  3. Compatibility is additive/versioned; historical v1 records are never rewritten.
 */

import { upcastV1ToV2 } from './projectionContract';

/** A legacy v1 projection event. */
export interface V1Event {
  readonly recordId: string;
  readonly runId: string;
  readonly ordinal: number;
}

/** A backfill result. */
export interface BackfillResult {
  readonly backfilled: number;
  readonly upcast: number;
  readonly preservedV1: number;
}

/**
 * Upcast a v1 event to a v2 projection record.
 *
 * The v1 source is preserved (immutable history); the returned v2 record is a new
 * additive view.
 */
export function upcastV1Event(v1: V1Event): ReturnType<typeof upcastV1ToV2> {
  return upcastV1ToV2({ recordId: v1.recordId, runId: v1.runId });
}

/**
 * Backfill a set of v1 events into a durable log.
 *
 * Returns counts. The v1 sources are preserved; upcast v2 records are appended in
 * ordinal order.
 */
export function backfillV1(
  v1Events: readonly V1Event[],
  append: (event: { eventId: string; runId: string; ordinal: number; payload: unknown }) => number,
): BackfillResult {
  const ordered = [...v1Events].sort((a, b) => a.ordinal - b.ordinal);
  let upcast = 0;
  for (const v1 of ordered) {
    const v2 = upcastV1Event(v1);
    append({ eventId: v1.recordId, runId: v1.runId, ordinal: v1.ordinal, payload: v2 });
    upcast += 1;
  }
  return { backfilled: ordered.length, upcast, preservedV1: v1Events.length };
}

/** Compatibility is read-only data; it grants no effect capability. */
export interface CompatibilityCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const COMPATIBILITY_CAPABILITIES: CompatibilityCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
