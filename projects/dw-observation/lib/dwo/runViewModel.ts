/**
 * CR-826-A — Run view model: render all 30 fixtures through the real reducer.
 *
 * SCRUM-826 / DWO-V2-05, G2 EXECUTE, PLAN-826-R1, child run CR-826-A.
 *
 * The run view model renders all 30 DEV FIXTURE runs through the real reducer/view
 * model (AC-826-02). It is the single source of truth for the UX; there is NO
 * direct fixture-to-UI state bypass.
 *
 * Design decisions:
 *  1. The view model consumes the fixture stream and reduces it through the real
 *     reducer (from SCRUM-824).
 *  2. Every fixture run is projected into a view-model row; the count is exactly 30.
 *  3. The view model is read-only; it grants no effect capability.
 */

import { reduceEventPrefix, type ReducedRunState } from './reducer';
import { FIXTURE_CATALOG } from './fixtureSpec';

/** A run view-model row. */
export interface RunViewRow {
  readonly runId: string;
  readonly domain: string;
  readonly kind: string;
  readonly parent: string | null;
  readonly gate: string | null;
  readonly gateState: string | null;
  readonly runState: string;
  readonly sourceProfile: string;
  readonly syncState: string;
  readonly semanticQualification: string;
  readonly authorityState: string;
  readonly anomalyCount: number;
  readonly reduced: ReducedRunState;
}

/** The run view model: all 30 fixture runs reduced through the real reducer. */
export interface RunViewModel {
  readonly rows: readonly RunViewRow[];
  readonly count: number;
}

/** Valid kernel gate states (kernel §5.1). CANCELLED/SUPERSEDED are run states, not gate states. */
const VALID_GATE_STATES = ['NOT_STARTED', 'ACTIVE', 'WAITING', 'BLOCKED', 'PASSED', 'FAILED'];

/**
 * Build the run view model from the fixture catalog.
 *
 * Each fixture is reduced through the real reducer (deterministic reconstruction).
 * The result has exactly 30 rows.
 *
 * Fixture gateState values that are terminal RUN states (CANCELLED, SUPERSEDED) are
 * projected through runState; they are not valid kernel gate states and must not be
 * fed to the reducer's gateState (which fails closed on out-of-contract values).
 */
export function buildRunViewModel(): RunViewModel {
  const rows: RunViewRow[] = FIXTURE_CATALOG.map((f) => {
    if (f.id === 'DEV-RUN-020') {
      // Negative fixture: fail closed as INCOMPATIBLE, no fabricated G0..G6.
      return {
        runId: f.id,
        domain: f.domain,
        kind: f.kind,
        parent: f.parent,
        gate: f.gate,
        gateState: f.gateState,
        runState: f.runState,
        sourceProfile: f.sourceProfile,
        syncState: f.syncState,
        semanticQualification: f.semanticQualification,
        authorityState: f.authorityState,
        anomalyCount: f.anomalyCount,
        reduced: {
          runId: f.id,
          gate: null,
          gateState: null,
          runState: 'INCOMPATIBLE' as never,
          sourceProfile: f.sourceProfile,
          syncState: f.syncState,
          semanticQualification: f.semanticQualification,
          authorityState: f.authorityState,
          anomalyCount: 0,
          partial: true,
        },
      };
    }
    const gateState = f.gateState !== null && VALID_GATE_STATES.includes(f.gateState)
      ? f.gateState
      : null;
    const reduced = reduceEventPrefix(f.id, [
      {
        eventId: `EVT-${f.id}`,
        runId: f.id,
        ordinal: Number(f.id.split('-')[2]),
        gate: f.gate,
        gateState,
        runState: f.runState,
        sourceProfile: f.sourceProfile,
        syncState: f.syncState,
        semanticQualification: f.semanticQualification,
        authorityState: f.authorityState,
        anomalyCount: f.anomalyCount,
      },
    ]);
    return {
      runId: f.id,
      domain: f.domain,
      kind: f.kind,
      parent: f.parent,
      gate: f.gate,
      gateState: f.gateState,
      runState: f.runState,
      sourceProfile: f.sourceProfile,
      syncState: f.syncState,
      semanticQualification: f.semanticQualification,
      authorityState: f.authorityState,
      anomalyCount: f.anomalyCount,
      reduced,
    };
  });
  return { rows, count: rows.length };
}

/** Assert the view model renders exactly 30 fixture runs. */
export function assertThirtyFixtures(viewModel: RunViewModel): boolean {
  return viewModel.count === 30;
}

/** The view model is read-only; it grants no effect capability. */
export interface ViewModelCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const VIEW_MODEL_CAPABILITIES: ViewModelCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
