/**
 * CR-826-C — UR lifecycle strip + UR-G* vs GWC-* namespace separation + authority rail.
 *
 * SCRUM-826 / DWO-V2-05, G2 EXECUTE, PLAN-826-R1, child run CR-826-C.
 *
 * The UR lifecycle strip shows the G0..G6 lifecycle with explicit UR-G* vs GWC-*
 * namespace separation (AC-826-05). The authority/effect rail is EVIDENCE-ONLY UX:
 * no action affordance grants or consumes runtime authority (AC-826-04).
 *
 * Design decisions:
 *  1. The lifecycle strip renders UR-G* gates (G0..G6) in the Universal namespace,
 *     distinct from GWC-* effect gates (G3_PR/G4_MERGE/G5_DEPLOY/G6_PRODUCTION_DATA).
 *  2. The authority rail is evidence-only: it displays authority state but exposes
 *     no action that grants/consumes authority.
 *  3. No action affordance in the UX grants or consumes runtime authority.
 */

import type { RunViewRow } from './runViewModel';

/** A lifecycle strip gate cell. */
export interface LifecycleGateCell {
  readonly namespace: 'UR_G' | 'GWC_EFFECT';
  readonly gate: string;
  readonly state: string | null;
}

/** The UR lifecycle strip for a run. */
export interface LifecycleStrip {
  readonly runId: string;
  readonly urGates: readonly LifecycleGateCell[];
  readonly gwcGates: readonly LifecycleGateCell[];
}

/** The UR-G* lifecycle gates in order. */
const UR_GATES = ['G0', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6'] as const;

/** The GWC-* effect gates. */
const GWC_GATES = ['G3_PR', 'G4_MERGE', 'G5_DEPLOY', 'G6_PRODUCTION_DATA'] as const;

/**
 * Build the lifecycle strip for a run.
 *
 * UR-G* gates are rendered in the Universal namespace; GWC-* effect gates in the
 * effect namespace. The two are never conflated.
 */
export function buildLifecycleStrip(row: RunViewRow): LifecycleStrip {
  const urGates: LifecycleGateCell[] = UR_GATES.map((g) => ({
    namespace: 'UR_G',
    gate: g,
    state: row.gate === g ? row.gateState : null,
  }));
  const gwcGates: LifecycleGateCell[] = GWC_GATES.map((g) => ({
    namespace: 'GWC_EFFECT',
    gate: g,
    state: null, // GWC-* effect gates are not part of the UR lifecycle strip
  }));
  return { runId: row.runId, urGates, gwcGates };
}

/**
 * Assert UR-G* vs GWC-* namespace separation.
 *
 * Returns true when no UR-G* gate is conflated with a GWC-* gate (the namespaces
 * are disjoint).
 */
export function assertNamespaceSeparation(strip: LifecycleStrip): boolean {
  const urGates = new Set(strip.urGates.map((g) => g.gate));
  const gwcGates = new Set(strip.gwcGates.map((g) => g.gate));
  for (const g of gwcGates) {
    if (urGates.has(g)) return false;
  }
  return true;
}

/** The authority/effect rail — evidence-only UX. */
export interface AuthorityRail {
  readonly runId: string;
  readonly authorityState: string;
  /** No action affordance grants or consumes runtime authority. */
  readonly actions: readonly never[];
}

/**
 * Build the authority rail for a run.
 *
 * The rail is EVIDENCE-ONLY: it displays the authority state but exposes NO action
 * that grants or consumes runtime authority (AC-826-04).
 */
export function buildAuthorityRail(row: RunViewRow): AuthorityRail {
  return {
    runId: row.runId,
    authorityState: row.authorityState,
    actions: [],
  };
}

/** Assert no action affordance grants/consumes runtime authority. */
export function assertNoAuthorityAffordance(rail: AuthorityRail): boolean {
  return rail.actions.length === 0;
}

/** Lifecycle strip is read-only; it grants no effect capability. */
export interface LifecycleStripCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const LIFECYCLE_STRIP_CAPABILITIES: LifecycleStripCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
