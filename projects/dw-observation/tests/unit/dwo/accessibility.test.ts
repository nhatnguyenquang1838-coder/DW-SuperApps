/**
 * CR-829-A/B/D verification — accessibility + 30-run pack unchanged.
 *
 * AC-829-01 V2_ACCESSIBILITY_READY derivable
 * AC-829-02 keyboard-operable graph navigation with visible focus and ARIA labels
 * AC-829-03 graph and structured tree/list selection stay synchronized
 * AC-829-04 status semantics are not color-only
 * AC-829-07 the hand-authored 30-run semantic pack remains unchanged
 */
import { describe, expect, it } from 'vitest';
import { buildRunViewModel } from '@/lib/dwo/runViewModel';
import { selectRun, type SelectionState } from '@/lib/dwo/runList';
import {
  ACCESSIBILITY_CAPABILITIES,
  assertAriaStructure,
  assertGraphTreeSelectionSynchronized,
  assertNonColorOnlyStatus,
  assertVisibleFocus,
  conveyStatus,
  graphNodeAriaLabel,
  keyboardNavOrder,
  selectRunShared,
} from '@/lib/dwo/accessibility';
import {
  ACCESSIBILITY_CERTIFICATION_CAPABILITIES,
  buildAccessibilityEvidence,
  deriveV2AccessibilityReady,
  type AccessibilityCertificationInput,
} from '@/lib/dwo/accessibilityCertification';
import { FIXTURE_CATALOG, assertFixtureCatalogInvariants } from '@/lib/dwo/fixtureSpec';

function certInput(overrides: Partial<AccessibilityCertificationInput> = {}): AccessibilityCertificationInput {
  return {
    keyboardOperable: true,
    visibleFocus: true,
    ariaStructure: true,
    selectionSynchronized: true,
    nonColorOnlyStatus: true,
    scalePackQualified: true,
    budgetThresholdsRecorded: true,
    thirtyRunPackUnchanged: true,
    ...overrides,
  };
}

describe('accessibility model (AC-829-02/03/04)', () => {
  const viewModel = buildRunViewModel();

  it('keyboard nav order covers every run (AC-829-02)', () => {
    const order = keyboardNavOrder(viewModel);
    expect(order.length).toBe(viewModel.rows.length);
    expect(new Set(order).size).toBe(viewModel.rows.length);
  });

  it('visible focus contract holds for a non-empty view model (AC-829-02)', () => {
    expect(assertVisibleFocus(viewModel)).toBe(true);
  });

  it('ARIA structure present for every node (AC-829-02)', () => {
    expect(assertAriaStructure(viewModel)).toBe(true);
    const label = graphNodeAriaLabel(viewModel.rows[0], true);
    expect(label).toContain('selected');
  });

  it('graph/tree selection stays synchronized via shared state (AC-829-03)', () => {
    const first = viewModel.rows[0].runId;
    const state: SelectionState = { selectedRunId: null };
    const next = selectRunShared(state, first);
    expect(assertGraphTreeSelectionSynchronized(viewModel, next)).toBe(true);
    // selectRunShared delegates to runList.selectRun (single shared state)
    expect(selectRun(state, first)).toEqual(next);
  });

  it('status is conveyed by text/icon/aria, not color alone (AC-829-04)', () => {
    for (const row of viewModel.rows) {
      expect(assertNonColorOnlyStatus(row)).toBe(true);
      const c = conveyStatus(row);
      expect(c.text.length).toBeGreaterThan(0);
      expect(c.ariaLabel.length).toBeGreaterThan(0);
    }
  });

  it('capabilities are read-only (no effect authority)', () => {
    expect(ACCESSIBILITY_CAPABILITIES.write).toBe(false);
    expect(ACCESSIBILITY_CAPABILITIES.approve).toBe(false);
    expect(ACCESSIBILITY_CAPABILITIES.merge).toBe(false);
  });
});

describe('V2_ACCESSIBILITY_READY derivation (AC-829-01)', () => {
  it('derives when all invariants hold', () => {
    const d = deriveV2AccessibilityReady(certInput());
    expect(d.derivable).toBe(true);
    expect(d.token).toBe('V2_ACCESSIBILITY_READY');
    expect(d.reasons).toEqual([]);
  });

  it('fails closed when keyboard navigation is missing', () => {
    const d = deriveV2AccessibilityReady(certInput({ keyboardOperable: false }));
    expect(d.derivable).toBe(false);
    expect(d.token).toBeNull();
    expect(d.reasons).toContain('graph navigation not keyboard-operable');
  });

  it('fails closed when status is color-only', () => {
    const d = deriveV2AccessibilityReady(certInput({ nonColorOnlyStatus: false }));
    expect(d.derivable).toBe(false);
    expect(d.reasons).toContain('status conveyed by color alone');
  });

  it('fails closed when the 30-run pack changed', () => {
    const d = deriveV2AccessibilityReady(certInput({ thirtyRunPackUnchanged: false }));
    expect(d.derivable).toBe(false);
    expect(d.reasons).toContain('30-run semantic pack changed');
  });

  it('buildAccessibilityEvidence derives the token from live state', () => {
    const evidence = buildAccessibilityEvidence();
    const d = deriveV2AccessibilityReady(evidence);
    expect(d.derivable).toBe(true);
    expect(d.token).toBe('V2_ACCESSIBILITY_READY');
  });

  it('certification capabilities are read-only', () => {
    expect(ACCESSIBILITY_CERTIFICATION_CAPABILITIES.write).toBe(false);
    expect(ACCESSIBILITY_CERTIFICATION_CAPABILITIES.merge).toBe(false);
  });
});

describe('30-run semantic pack unchanged (AC-829-07)', () => {
  it('catalog invariants hold: exactly 30, 29 conforming + 1 negative', () => {
    expect(() => assertFixtureCatalogInvariants(FIXTURE_CATALOG)).not.toThrow();
    expect(FIXTURE_CATALOG.length).toBe(30);
  });
});
