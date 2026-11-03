/**
 * CR-828-C — DEGRADED/UNAVAILABLE projection states + certified-LIVE qualification gate.
 *
 * SCRUM-828 / DWO-V2-07, G2 EXECUTE, PLAN-828-R1, child run CR-828-C.
 *
 * DEGRADED and UNAVAILABLE projection states (AC-828-04), and certified LIVE
 * requiring current valid semantic qualification bound to the current projection
 * subject (AC-828-05). Transport connectivity alone never establishes certified
 * LIVE (AC-828-02).
 *
 * Design decisions:
 *  1. A projection is DEGRADED when transport is partially available but durable
 *     catch-up is incomplete; UNAVAILABLE when transport is down beyond retention.
 *  2. Certified LIVE requires: durable bootstrap + catch-up complete AND current
 *     valid semantic qualification bound to the current projection subject.
 */

import type { RealtimeBootstrap } from './realtimeBootstrap';

/** The live projection state. */
export type LiveProjectionState = 'LIVE' | 'DEGRADED' | 'UNAVAILABLE';

/** A semantic qualification binding. */
export interface SemanticQualification {
  readonly subject: string;
  readonly status: 'QUALIFIED' | 'PENDING' | 'INCOMPATIBLE';
  readonly valid: boolean;
}

/**
 * Determine the live projection state.
 *
 * - UNAVAILABLE when transport is down beyond retention.
 * - DEGRADED when transport is partially available but durable catch-up incomplete.
 * - Otherwise the state is LIVE (but certified LIVE additionally requires valid
 *   qualification).
 */
export function determineLiveState(
  bootstrap: RealtimeBootstrap,
  transportAvailable: boolean,
  beyondRetention: boolean,
): LiveProjectionState {
  if (!transportAvailable || beyondRetention) return 'UNAVAILABLE';
  if (!bootstrap.caughtUp) return 'DEGRADED';
  return 'LIVE';
}

/**
 * Determine whether a projection is CERTIFIED LIVE.
 *
 * Certified LIVE requires: the projection state is LIVE AND the current valid
 * semantic qualification is bound to the current projection subject. Transport
 * connectivity alone never establishes certified LIVE (AC-828-02).
 */
export function isCertifiedLive(
  state: LiveProjectionState,
  qualification: SemanticQualification,
  projectionSubject: string,
): boolean {
  if (state !== 'LIVE') return false;
  if (qualification.status !== 'QUALIFIED') return false;
  if (!qualification.valid) return false;
  if (qualification.subject !== projectionSubject) return false;
  return true;
}

/** Live state is read-only; it grants no effect capability. */
export interface LiveStateCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const LIVE_STATE_CAPABILITIES: LiveStateCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);