/**
 * CR-826-D — V2_PRODUCT_ALPHA derivation.
 *
 * SCRUM-826 / DWO-V2-05, G2 EXECUTE, PLAN-826-R1, child run CR-826-D.
 *
 * The WS5 exit token V2_PRODUCT_ALPHA is DERIVED from machine-readable state, never
 * asserted. It holds exactly when:
 *   1. the run exploration UX renders all 30 fixtures through the real reducer;
 *   2. graph and tree/list selection stay synchronized;
 *   3. no action affordance grants or consumes runtime authority;
 *   4. UR-G* vs GWC-* namespace separation is visible in the lifecycle strip.
 */
import { assertThirtyFixtures, buildRunViewModel } from './runViewModel';
import type { AuthorityDecision } from './authorityVocabulary';
import type { CompositionDecision } from './parentComposition';
import type { RelationDecision } from './taskRunIndex';
import { assertSelectionSynchronized, type SelectionState } from './runList';
import { assertNamespaceSeparation, assertNoAuthorityAffordance, buildAuthorityRail, buildLifecycleStrip } from './lifecycleStrip';

export interface ProductAlphaInput {
  readonly rendersThirtyFixtures: boolean;
  readonly selectionSynchronized: boolean;
  readonly noAuthorityAffordance: boolean;
  readonly namespaceSeparationVisible: boolean;
}

export interface ProductAlphaDecision {
  readonly derivable: boolean;
  readonly token: string | null;
  readonly reasons: readonly string[];
}

/**
 * Derive V2_PRODUCT_ALPHA. Fails closed on any incoherent input.
 */
export function deriveV2ProductAlpha(input: ProductAlphaInput): ProductAlphaDecision {
  const reasons: string[] = [];
  if (!input.rendersThirtyFixtures) reasons.push('UX does not render all 30 fixtures');
  if (!input.selectionSynchronized) reasons.push('graph/tree selection not synchronized');
  if (!input.noAuthorityAffordance) reasons.push('an action affordance grants/consumes authority');
  if (!input.namespaceSeparationVisible) reasons.push('UR-G* vs GWC-* namespace separation not visible');
  if (reasons.length === 0) {
    return { derivable: true, token: 'V2_PRODUCT_ALPHA', reasons: [] };
  }
  return { derivable: false, token: null, reasons };
}

/**
 * Build the certification evidence from the live view model.
 * R2-D/E/F: evidence maps are consumed by runId — the UI renders the
 * authoritative decision, never inferred state. Absent maps = null.
 */
export function buildProductAlphaEvidence(
  authorityByRun?: Readonly<Record<string, AuthorityDecision>>,
  compositionByRun?: Readonly<Record<string, CompositionDecision>>,
  taskRelationByRun?: Readonly<Record<string, RelationDecision>>,
): ProductAlphaInput {
  const viewModel = buildRunViewModel(authorityByRun, compositionByRun, taskRelationByRun);
  const selection: SelectionState = { selectedRunId: viewModel.rows[0]?.runId ?? null };
  const strips = viewModel.rows.map(buildLifecycleStrip);
  const rails = viewModel.rows.map(buildAuthorityRail);
  return {
    rendersThirtyFixtures: assertThirtyFixtures(viewModel),
    selectionSynchronized: assertSelectionSynchronized(viewModel, selection),
    noAuthorityAffordance: rails.every(assertNoAuthorityAffordance),
    namespaceSeparationVisible: strips.every(assertNamespaceSeparation),
  };
}

/** UX certification is read-only; it grants no effect capability. */
export interface UxCertificationCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const UX_CERTIFICATION_CAPABILITIES: UxCertificationCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);

/** Exit-token registry. */
export const EXIT_TOKENS = Object.freeze({
  v2ProductAlpha: 'V2_PRODUCT_ALPHA',
} as const);
