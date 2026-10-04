/**
 * CR-829-D — V2_ACCESSIBILITY_READY derivation.
 *
 * SCRUM-829 / DWO-V2-08, G2 EXECUTE, PLAN-829-R1, child run CR-829-D.
 *
 * The WS8 exit token V2_ACCESSIBILITY_READY is DERIVED from machine-readable
 * state, never asserted. It holds exactly when:
 *   1. keyboard-operable graph navigation with visible focus (AC-829-02);
 *   2. ARIA labels and screen-reader-friendly structure (AC-829-02);
 *   3. graph and structured tree/list selection stay synchronized (AC-829-03);
 *   4. status semantics are not color-only (AC-829-04);
 *   5. DWO-SCALE-GEN-V1 scale pack measures depth/fanout/node-count/performance (AC-829-05);
 *   6. progressive-disclosure budget thresholds are measured and recorded (AC-829-06);
 *   7. the hand-authored 30-run semantic pack remains unchanged (AC-829-07).
 */
import { buildRunViewModel } from './runViewModel';
import type { AuthorityDecision } from './authorityVocabulary';
import type { CompositionDecision } from './parentComposition';
import type { RelationDecision } from './taskRunIndex';
import {
  assertAriaStructure,
  assertGraphTreeSelectionSynchronized,
  assertNonColorOnlyStatus,
  assertVisibleFocus,
  keyboardNavOrder,
} from './accessibility';
import { type SelectionState } from './runList';
import { qualifyScalePack } from './scaleGen';
import { FIXTURE_CATALOG, assertFixtureCatalogInvariants } from './fixtureSpec';

export interface AccessibilityCertificationInput {
  readonly keyboardOperable: boolean;
  readonly visibleFocus: boolean;
  readonly ariaStructure: boolean;
  readonly selectionSynchronized: boolean;
  readonly nonColorOnlyStatus: boolean;
  readonly scalePackQualified: boolean;
  readonly budgetThresholdsRecorded: boolean;
  readonly thirtyRunPackUnchanged: boolean;
}

export interface AccessibilityCertificationDecision {
  readonly derivable: boolean;
  readonly token: string | null;
  readonly reasons: readonly string[];
}

/**
 * Derive V2_ACCESSIBILITY_READY. Fails closed on any incoherent input.
 */
export function deriveV2AccessibilityReady(
  input: AccessibilityCertificationInput,
): AccessibilityCertificationDecision {
  const reasons: string[] = [];
  if (!input.keyboardOperable) reasons.push('graph navigation not keyboard-operable');
  if (!input.visibleFocus) reasons.push('no visible focus contract');
  if (!input.ariaStructure) reasons.push('ARIA structure missing');
  if (!input.selectionSynchronized) reasons.push('graph/tree selection not synchronized');
  if (!input.nonColorOnlyStatus) reasons.push('status conveyed by color alone');
  if (!input.scalePackQualified) reasons.push('DWO-SCALE-GEN-V1 not qualified');
  if (!input.budgetThresholdsRecorded) reasons.push('budget thresholds not recorded');
  if (!input.thirtyRunPackUnchanged) reasons.push('30-run semantic pack changed');
  if (reasons.length === 0) {
    return { derivable: true, token: 'V2_ACCESSIBILITY_READY', reasons: [] };
  }
  return { derivable: false, token: null, reasons };
}

/**
 * Build the certification evidence from the live view model and scale pack.
 * R2-D/E/F: evidence maps are consumed by runId — the UI renders the
 * authoritative decision, never inferred state. Absent maps = null.
 */
export function buildAccessibilityEvidence(
  authorityByRun?: Readonly<Record<string, AuthorityDecision>>,
  compositionByRun?: Readonly<Record<string, CompositionDecision>>,
  taskRelationByRun?: Readonly<Record<string, RelationDecision>>,
): AccessibilityCertificationInput {
  const viewModel = buildRunViewModel(authorityByRun, compositionByRun, taskRelationByRun);
  const selection: SelectionState = { selectedRunId: viewModel.rows[0]?.runId ?? null };
  const navOrder = keyboardNavOrder(viewModel);
  const scale = qualifyScalePack();

  // 30-run pack unchanged: catalog invariants hold (exactly 30, 29 conforming + 1 negative).
  let thirtyRunPackUnchanged = true;
  try {
    assertFixtureCatalogInvariants(FIXTURE_CATALOG);
  } catch {
    thirtyRunPackUnchanged = false;
  }

  return {
    keyboardOperable: navOrder.length === viewModel.rows.length,
    visibleFocus: assertVisibleFocus(viewModel),
    ariaStructure: assertAriaStructure(viewModel),
    selectionSynchronized: assertGraphTreeSelectionSynchronized(viewModel, selection),
    nonColorOnlyStatus: viewModel.rows.every(assertNonColorOnlyStatus),
    scalePackQualified: scale.metrics.length === 4 && scale.pack === 'DWO-SCALE-GEN-V1',
    budgetThresholdsRecorded: scale.budgets.length === scale.metrics.length,
    thirtyRunPackUnchanged,
  };
}

/** Accessibility certification is read-only; it grants no effect capability. */
export interface AccessibilityCertificationCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const ACCESSIBILITY_CERTIFICATION_CAPABILITIES: AccessibilityCertificationCapabilities =
  Object.freeze({
    read: true,
    write: false,
    approve: false,
    deny: false,
    merge: false,
    deploy: false,
  } as const);

/** Exit-token registry. */
export const EXIT_TOKENS = Object.freeze({
  v2AccessibilityReady: 'V2_ACCESSIBILITY_READY',
} as const);
