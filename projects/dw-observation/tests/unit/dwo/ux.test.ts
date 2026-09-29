/**
 * CR-826-A/B/C/D verification — run-centric UX.
 *
 * AC-826-01 V2_PRODUCT_ALPHA derivable
 * AC-826-02 run exploration UX usable against all 30 fixtures
 * AC-826-03 graph and tree/list selection stay synchronized
 * AC-826-04 no action affordance grants or consumes runtime authority
 * AC-826-05 UR-G* vs GWC-* namespace separation visible
 */
import { describe, expect, it } from 'vitest';
import {
  VIEW_MODEL_CAPABILITIES,
  assertThirtyFixtures,
  buildRunViewModel,
} from '@/lib/dwo/runViewModel';
import {
  RUN_LIST_CAPABILITIES,
  assertSelectionSynchronized,
  clearSelection,
  runDetail,
  runList,
  selectRun,
} from '@/lib/dwo/runList';
import {
  LIFECYCLE_STRIP_CAPABILITIES,
  assertNamespaceSeparation,
  assertNoAuthorityAffordance,
  buildAuthorityRail,
  buildLifecycleStrip,
} from '@/lib/dwo/lifecycleStrip';
import {
  UX_CERTIFICATION_CAPABILITIES,
  buildProductAlphaEvidence,
  deriveV2ProductAlpha,
  type ProductAlphaInput,
} from '@/lib/dwo/uxCertification';

function alphaInput(overrides: Partial<ProductAlphaInput> = {}): ProductAlphaInput {
  return {
    rendersThirtyFixtures: true,
    selectionSynchronized: true,
    noAuthorityAffordance: true,
    namespaceSeparationVisible: true,
    ...overrides,
  };
}

describe('AC-826-02 · run exploration UX usable against all 30 fixtures', () => {
  it('the view model renders exactly 30 fixture runs through the real reducer', () => {
    const vm = buildRunViewModel();
    expect(vm.count).toBe(30);
    expect(assertThirtyFixtures(vm)).toBe(true);
  });

  it('every row carries reduced state through the real reducer path', () => {
    const vm = buildRunViewModel();
    for (const row of vm.rows) {
      expect(row.reduced.runId).toBe(row.runId);
      // No direct fixture-to-UI bypass: reduced state is the view source.
      expect(row.reduced).toBeDefined();
    }
  });

  it('run list and run detail serve the view model', () => {
    const vm = buildRunViewModel();
    expect(runList(vm).length).toBe(30);
    expect(runList(vm, 'DEV-RUN-021').length).toBe(2); // 022, 023
    const detail = runDetail(vm, 'DEV-RUN-024');
    expect(detail).toBeDefined();
    expect(detail!.runId).toBe('DEV-RUN-024');
  });
});

describe('AC-826-03 · graph and tree/list selection stay synchronized', () => {
  it('a single shared selection state drives both views', () => {
    const vm = buildRunViewModel();
    const selected = selectRun(clearSelection(), 'DEV-RUN-001');
    expect(selected.selectedRunId).toBe('DEV-RUN-001');
    expect(assertSelectionSynchronized(vm, selected)).toBe(true);
  });

  it('clearing the selection is valid', () => {
    const vm = buildRunViewModel();
    expect(assertSelectionSynchronized(vm, clearSelection())).toBe(true);
  });

  it('an unknown selection is not synchronized', () => {
    const vm = buildRunViewModel();
    expect(assertSelectionSynchronized(vm, { selectedRunId: 'NOPE' })).toBe(false);
  });
});

describe('AC-826-04 · no action affordance grants or consumes runtime authority', () => {
  it('the authority rail is evidence-only with no actions', () => {
    const vm = buildRunViewModel();
    for (const row of vm.rows) {
      const rail = buildAuthorityRail(row);
      expect(assertNoAuthorityAffordance(rail)).toBe(true);
      expect(rail.actions.length).toBe(0);
    }
  });
});

describe('AC-826-05 · UR-G* vs GWC-* namespace separation visible', () => {
  it('the lifecycle strip renders UR-G* gates distinct from GWC-* effect gates', () => {
    const vm = buildRunViewModel();
    for (const row of vm.rows) {
      const strip = buildLifecycleStrip(row);
      expect(strip.urGates.length).toBe(7); // G0..G6
      expect(strip.gwcGates.length).toBe(4); // G3_PR..G6_PRODUCTION_DATA
      expect(assertNamespaceSeparation(strip)).toBe(true);
      // The run's own gate is reflected in the UR-G* strip state.
      if (row.gate) {
        const cell = strip.urGates.find((c) => c.gate === row.gate);
        expect(cell!.state).toBe(row.gateState);
      }
    }
  });
});

describe('AC-826-01 · V2_PRODUCT_ALPHA derivation', () => {
  it('derives the token from a coherent UX', () => {
    const decision = deriveV2ProductAlpha(alphaInput());
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_PRODUCT_ALPHA');
    expect(decision.reasons).toEqual([]);
  });

  it('derives from the live view model evidence', () => {
    const evidence = buildProductAlphaEvidence();
    const decision = deriveV2ProductAlpha(evidence);
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('V2_PRODUCT_ALPHA');
  });

  it('fails closed when the UX does not render 30 fixtures', () => {
    expect(deriveV2ProductAlpha(alphaInput({ rendersThirtyFixtures: false })).derivable).toBe(false);
  });

  it('fails closed when an action grants authority', () => {
    expect(deriveV2ProductAlpha(alphaInput({ noAuthorityAffordance: false })).derivable).toBe(false);
  });
});

describe('capabilities — UX modules are read-only', () => {
  it('exposes no effect capability anywhere', () => {
    for (const caps of [VIEW_MODEL_CAPABILITIES, RUN_LIST_CAPABILITIES, LIFECYCLE_STRIP_CAPABILITIES, UX_CERTIFICATION_CAPABILITIES]) {
      expect(caps).toEqual({
        read: true,
        write: false,
        approve: false,
        deny: false,
        merge: false,
        deploy: false,
      });
      expect(Object.isFrozen(caps)).toBe(true);
    }
  });
});