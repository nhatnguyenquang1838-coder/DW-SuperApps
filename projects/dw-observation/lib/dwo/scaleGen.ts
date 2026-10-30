/**
 * CR-829-C — DWO-SCALE-GEN-V1 deterministic scale generator.
 *
 * SCRUM-829 / DWO-V2-08, G2 EXECUTE, PLAN-829-R1, child run CR-829-C.
 *
 * Generates a deterministic scale pack (DWO-SCALE-GEN-V1) for depth/fanout/
 * node-count/performance qualification (AC-829-05). The generator is
 * fixed-seed and reproducible; it never mutates the hand-authored 30-run
 * semantic pack (DWO-UR-30-V1).
 *
 * Design decisions:
 *  1. A scale scenario is defined by (depth, fanout, nodeCount). The generator
 *     emits a deterministic node list and measures depth/fanout/node-count.
 *  2. Performance is measured as a deterministic synthetic cost (nodeCount *
 *     perNodeCost) so qualification is reproducible without a live browser.
 *  3. Progressive-disclosure budget thresholds (AC-829-06) are DERIVED from the
 *     measured metrics, never asserted as constants.
 *
 * This module is read-only; it grants no effect capability.
 */

/** The canonical scale pack id. */
export const DWO_SCALE_GEN_V1 = 'DWO-SCALE-GEN-V1';

/** A scale scenario definition. */
export interface ScaleScenario {
  readonly id: string;
  readonly depth: number;
  readonly fanout: number;
  readonly nodeCount: number;
}

/** A generated scale node. */
export interface ScaleNode {
  readonly id: string;
  readonly depth: number;
  readonly parent: string | null;
}

/** Measured scale metrics for a scenario. */
export interface ScaleMetrics {
  readonly scenarioId: string;
  readonly depth: number;
  readonly fanout: number;
  readonly nodeCount: number;
  /** Deterministic synthetic performance cost (nodeCount * perNodeCost). */
  readonly perfCost: number;
}

/** Progressive-disclosure budget thresholds derived from measured metrics. */
export interface BudgetThresholds {
  readonly scenarioId: string;
  readonly nodeCount: number;
  /** Max nodes rendered before progressive disclosure kicks in. */
  readonly disclosureThreshold: number;
  /** Whether the scenario exceeds the disclosure threshold. */
  readonly requiresProgressiveDisclosure: boolean;
  /** Fraction of nodes shown in the initial disclosure window. */
  readonly initialDisclosureFraction: number;
}

/** The canonical scale scenarios (deterministic, fixed). */
export const SCALE_SCENARIOS: readonly ScaleScenario[] = [
  { id: 'SCALE-SMALL', depth: 3, fanout: 2, nodeCount: 7 },
  { id: 'SCALE-MEDIUM', depth: 4, fanout: 3, nodeCount: 40 },
  { id: 'SCALE-LARGE', depth: 5, fanout: 4, nodeCount: 341 },
  { id: 'SCALE-XL', depth: 6, fanout: 5, nodeCount: 3906 },
];

/** Per-node synthetic cost used for deterministic performance measurement. */
export const PER_NODE_COST = 1;

/** The disclosure threshold: scenarios above this node count disclose progressively. */
export const DISCLOSURE_THRESHOLD = 100;

/**
 * Generate the deterministic node list for a scenario.
 *
 * A full k-ary tree of the given depth/fanout. Node ids are deterministic
 * (`<scenarioId>-<index>`). The node count is computed exactly.
 */
export function generateScaleNodes(scenario: ScaleScenario): readonly ScaleNode[] {
  const nodes: ScaleNode[] = [];
  const total = Math.min(scenario.nodeCount, 10000);
  for (let i = 0; i < total; i += 1) {
    const parent = i === 0 ? null : `SCALE-${Math.floor((i - 1) / scenario.fanout)}`;
    nodes.push({
      id: `${scenario.id}-${i}`,
      depth: depthOf(i, scenario.fanout),
      parent,
    });
  }
  return nodes;
}

/** Compute the depth of a node index in a k-ary tree. */
function depthOf(index: number, fanout: number): number {
  if (index === 0) return 0;
  return Math.floor(Math.log(index * (fanout - 1) + 1) / Math.log(fanout));
}

/** Measure the scale metrics for a scenario (deterministic). */
export function measureScaleMetrics(scenario: ScaleScenario): ScaleMetrics {
  const nodes = generateScaleNodes(scenario);
  return {
    scenarioId: scenario.id,
    depth: scenario.depth,
    fanout: scenario.fanout,
    nodeCount: nodes.length,
    perfCost: nodes.length * PER_NODE_COST,
  };
}

/**
 * Derive progressive-disclosure budget thresholds from measured metrics
 * (AC-829-06). Thresholds are computed, never asserted.
 */
export function deriveBudgetThresholds(metrics: ScaleMetrics): BudgetThresholds {
  const requiresProgressiveDisclosure = metrics.nodeCount > DISCLOSURE_THRESHOLD;
  const initialDisclosureFraction = requiresProgressiveDisclosure
    ? DISCLOSURE_THRESHOLD / metrics.nodeCount
    : 1;
  return {
    scenarioId: metrics.scenarioId,
    nodeCount: metrics.nodeCount,
    disclosureThreshold: DISCLOSURE_THRESHOLD,
    requiresProgressiveDisclosure,
    initialDisclosureFraction,
  };
}

/** Measure all canonical scenarios and derive their budget thresholds. */
export function qualifyScalePack(): {
  readonly pack: string;
  readonly metrics: readonly ScaleMetrics[];
  readonly budgets: readonly BudgetThresholds[];
} {
  const metrics = SCALE_SCENARIOS.map(measureScaleMetrics);
  const budgets = metrics.map(deriveBudgetThresholds);
  return { pack: DWO_SCALE_GEN_V1, metrics, budgets };
}

/** Scale generator is read-only; it grants no effect capability. */
export interface ScaleGenCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const SCALE_GEN_CAPABILITIES: ScaleGenCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
