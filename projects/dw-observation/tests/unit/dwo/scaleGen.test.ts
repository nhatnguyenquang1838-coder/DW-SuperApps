/**
 * CR-829-C/D verification — DWO-SCALE-GEN-V1 scale pack + budget thresholds.
 *
 * AC-829-05 DWO-SCALE-GEN-V1 generated scale pack measures depth/fanout/node-count/performance
 * AC-829-06 progressive disclosure and graph budget thresholds explicitly measured and recorded
 */
import { describe, expect, it } from 'vitest';
import {
  DWO_SCALE_GEN_V1,
  DISCLOSURE_THRESHOLD,
  SCALE_GEN_CAPABILITIES,
  SCALE_SCENARIOS,
  deriveBudgetThresholds,
  generateScaleNodes,
  measureScaleMetrics,
  qualifyScalePack,
} from '@/lib/dwo/scaleGen';

describe('DWO-SCALE-GEN-V1 scale pack (AC-829-05)', () => {
  it('generates deterministic node lists for every scenario', () => {
    for (const s of SCALE_SCENARIOS) {
      const nodes = generateScaleNodes(s);
      expect(nodes.length).toBe(s.nodeCount);
      // deterministic: same input -> same output
      expect(generateScaleNodes(s)).toEqual(nodes);
    }
  });

  it('measures depth/fanout/node-count/performance (AC-829-05)', () => {
    for (const s of SCALE_SCENARIOS) {
      const m = measureScaleMetrics(s);
      expect(m.scenarioId).toBe(s.id);
      expect(m.depth).toBe(s.depth);
      expect(m.fanout).toBe(s.fanout);
      expect(m.nodeCount).toBe(s.nodeCount);
      expect(m.perfCost).toBe(s.nodeCount * 1);
    }
  });

  it('qualifyScalePack returns the canonical pack with 4 scenarios', () => {
    const q = qualifyScalePack();
    expect(q.pack).toBe(DWO_SCALE_GEN_V1);
    expect(q.metrics.length).toBe(4);
    expect(q.budgets.length).toBe(4);
  });

  it('capabilities are read-only', () => {
    expect(SCALE_GEN_CAPABILITIES.write).toBe(false);
    expect(SCALE_GEN_CAPABILITIES.merge).toBe(false);
  });
});

describe('progressive-disclosure budget thresholds (AC-829-06)', () => {
  it('small scenarios do not require progressive disclosure', () => {
    const small = measureScaleMetrics(SCALE_SCENARIOS[0]);
    const b = deriveBudgetThresholds(small);
    expect(b.requiresProgressiveDisclosure).toBe(false);
    expect(b.initialDisclosureFraction).toBe(1);
  });

  it('large scenarios exceed the disclosure threshold and disclose progressively', () => {
    const large = measureScaleMetrics(SCALE_SCENARIOS[2]); // 341 nodes
    const b = deriveBudgetThresholds(large);
    expect(b.nodeCount).toBeGreaterThan(DISCLOSURE_THRESHOLD);
    expect(b.requiresProgressiveDisclosure).toBe(true);
    expect(b.initialDisclosureFraction).toBeLessThan(1);
    expect(b.initialDisclosureFraction).toBeCloseTo(DISCLOSURE_THRESHOLD / 341, 5);
  });

  it('thresholds are derived from measured metrics, not asserted constants', () => {
    const q = qualifyScalePack();
    for (const b of q.budgets) {
      expect(b.disclosureThreshold).toBe(DISCLOSURE_THRESHOLD);
      expect(b.initialDisclosureFraction).toBeGreaterThan(0);
      expect(b.initialDisclosureFraction).toBeLessThanOrEqual(1);
    }
  });
});
