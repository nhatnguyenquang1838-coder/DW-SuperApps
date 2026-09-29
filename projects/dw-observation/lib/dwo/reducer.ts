/**
 * CR-824-A — UniversalRun reducer core.
 *
 * SCRUM-824 / DWO-V2-03, G2 EXECUTE, PLAN-824-R1, child run CR-824-A.
 *
 * The reducer is a PURE function over ordered event prefixes. It deterministically
 * reconstructs Run state from the same event prefix (AC-824-02). Missing facts stay
 * UNKNOWN/PARTIAL (AC-824-03).
 *
 * Design decisions:
 *  1. The reducer is a pure function: same ordered event prefix -> same state.
 *  2. State is reconstructed incrementally; a missing fact stays UNKNOWN/PARTIAL,
 *     never fabricated.
 *  3. The reducer consumes Projection Contract v2 events (from SCRUM-823) and the
 *     fixture stream (from SCRUM-822) for conformance.
 */

import type { GateRef, RunState } from './projectionContract';

/** A projection event consumed by the reducer. */
export interface ReducerEvent {
  readonly eventId: string;
  readonly runId: string;
  readonly ordinal: number;
  readonly gate?: string | null;
  readonly gateState?: string | null;
  readonly runState?: string | null;
  readonly sourceProfile?: string;
  readonly syncState?: string;
  readonly semanticQualification?: string;
  readonly authorityState?: string;
  readonly anomalyCount?: number;
}

/** The reduced state of a single Run. */
export interface ReducedRunState {
  readonly runId: string;
  readonly gate: string | null;
  readonly gateState: string | null;
  readonly runState: RunState | 'UNKNOWN';
  readonly sourceProfile: string | 'UNKNOWN';
  readonly syncState: string | 'UNKNOWN';
  readonly semanticQualification: string | 'UNKNOWN';
  readonly authorityState: string | 'UNKNOWN';
  readonly anomalyCount: number | 'UNKNOWN';
  /** True when the state is PARTIAL (some facts missing). */
  readonly partial: boolean;
}

/** The initial (empty) state for a Run: all facts UNKNOWN. */
export function initialRunState(runId: string): ReducedRunState {
  return {
    runId,
    gate: null,
    gateState: null,
    runState: 'UNKNOWN',
    sourceProfile: 'UNKNOWN',
    syncState: 'UNKNOWN',
    semanticQualification: 'UNKNOWN',
    authorityState: 'UNKNOWN',
    anomalyCount: 'UNKNOWN',
    partial: true,
  };
}

/** The kernel run terminal states (kernel §5.2). */
const VALID_RUN_STATES: readonly string[] = ['OPEN', 'ACCEPTED', 'FAILED', 'CANCELLED', 'SUPERSEDED'];

/** The kernel gate states (kernel §5.1). */
const VALID_GATE_STATES: readonly string[] = ['NOT_STARTED', 'ACTIVE', 'WAITING', 'BLOCKED', 'PASSED', 'FAILED'];

/**
 * Reduce a single event into a Run state.
 *
 * Missing facts stay UNKNOWN; present facts overwrite. The result is PARTIAL until
 * all core facts are known. F4: runState and gateState are validated against the
 * kernel enums; an out-of-contract value is rejected rather than silently accepted.
 */
export function reduceEvent(state: ReducedRunState, event: ReducerEvent): ReducedRunState {
  if (event.runState != null && !VALID_RUN_STATES.includes(event.runState)) {
    throw new Error(`invalid runState "${event.runState}" for ${event.runId}`);
  }
  if (event.gateState != null && !VALID_GATE_STATES.includes(event.gateState)) {
    throw new Error(`invalid gateState "${event.gateState}" for ${event.runId}`);
  }
  const next: ReducedRunState = {
    runId: state.runId,
    gate: event.gate != null ? event.gate : state.gate,
    gateState: event.gateState != null ? event.gateState : state.gateState,
    runState: event.runState != null ? (event.runState as RunState) : state.runState,
    sourceProfile: event.sourceProfile != null ? event.sourceProfile : state.sourceProfile,
    syncState: event.syncState != null ? event.syncState : state.syncState,
    semanticQualification: event.semanticQualification != null ? event.semanticQualification : state.semanticQualification,
    authorityState: event.authorityState != null ? event.authorityState : state.authorityState,
    anomalyCount: event.anomalyCount != null ? event.anomalyCount : state.anomalyCount,
    partial: false,
  };
  return { ...next, partial: isPartial(next) };
}

/** True when any core fact is still UNKNOWN. */
export function isPartial(state: ReducedRunState): boolean {
  return (
    state.runState === 'UNKNOWN' ||
    state.sourceProfile === 'UNKNOWN' ||
    state.syncState === 'UNKNOWN' ||
    state.semanticQualification === 'UNKNOWN' ||
    state.authorityState === 'UNKNOWN' ||
    state.anomalyCount === 'UNKNOWN'
  );
}

/**
 * Reduce an ordered event prefix into a Run state.
 *
 * Deterministic: the same ordered prefix always produces the same state. Events
 * are applied in ordinal order.
 */
export function reduceEventPrefix(
  runId: string,
  events: readonly ReducerEvent[],
): ReducedRunState {
  const ordered = [...events].sort((a, b) => a.ordinal - b.ordinal);
  let state = initialRunState(runId);
  for (const event of ordered) {
    if (event.runId !== runId) continue;
    state = reduceEvent(state, event);
  }
  return state;
}

/** The reducer is read-only; it grants no effect capability. */
export interface ReducerCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const REDUCER_CAPABILITIES: ReducerCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
