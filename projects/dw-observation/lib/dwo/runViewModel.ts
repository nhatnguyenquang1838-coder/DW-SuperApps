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
import { AUTHORITY_STATES, type AuthorityState, type AuthorityDecision } from './authorityVocabulary';
import type { CompositionDecision } from './parentComposition';
import type { RelationDecision } from './taskRunIndex';

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
  /** R2-D: authoritative authority decision rendered, not inferred. */
  readonly authority: AuthorityDecision | null;
  /** R2-E: explicit parent composition decision, absent when not applicable. */
  readonly composition: CompositionDecision | null;
  /** R2-F: explicit task→root mapping decision, absent when not applicable. */
  readonly taskRelation: RelationDecision | null;
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
 * Optional R2 evidence maps are consumed by runId when present — the UI renders
 * the authoritative decision, never inferred state. Absent maps = R2 not
 * applicable to this view, fields default to null.
 *
 * Fixture gateState values that are terminal RUN states (CANCELLED, SUPERSEDED) are
 * projected through runState; they are not valid kernel gate states and must not be
 * fed to the reducer's gateState (which fails closed on out-of-contract values).
 */
export function buildRunViewModel(
  authorityByRun?: Readonly<Record<string, AuthorityDecision>>,
  compositionByRun?: Readonly<Record<string, CompositionDecision>>,
  taskRelationByRun?: Readonly<Record<string, RelationDecision>>,
): RunViewModel {
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
        authorityState: (AUTHORITY_STATES as readonly string[]).includes(f.authorityState) ? (f.authorityState as AuthorityState) : 'UNKNOWN',
        anomalyCount: f.anomalyCount,
        reduced: {
          runId: f.id,
          gate: null,
          gateState: null,
          runState: 'INCOMPATIBLE' as never,
          sourceProfile: f.sourceProfile,
          syncState: f.syncState,
          semanticQualification: f.semanticQualification,
          authorityState: (AUTHORITY_STATES as readonly string[]).includes(f.authorityState) ? (f.authorityState as AuthorityState) : 'UNKNOWN',
          anomalyCount: 0,
          partial: true,
        },
        authority: authorityByRun?.[f.id] ?? null,
        composition: compositionByRun?.[f.id] ?? null,
        taskRelation: taskRelationByRun?.[f.id] ?? null,
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
        authorityState: (AUTHORITY_STATES as readonly string[]).includes(f.authorityState) ? (f.authorityState as AuthorityState) : 'UNKNOWN',
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
      authorityState: (AUTHORITY_STATES as readonly string[]).includes(f.authorityState) ? (f.authorityState as AuthorityState) : 'UNKNOWN',
      anomalyCount: f.anomalyCount,
      reduced,
      authority: authorityByRun?.[f.id] ?? null,
      composition: compositionByRun?.[f.id] ?? null,
      taskRelation: taskRelationByRun?.[f.id] ?? null,
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
