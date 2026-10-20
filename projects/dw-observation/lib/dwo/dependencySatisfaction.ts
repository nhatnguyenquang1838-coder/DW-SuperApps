/**
 * R2-A — Dependency satisfaction predicate + derived BLOCKS fail-closed.
 *
 * BLOCKS is derived, never reducer-authoritative. It is produced only when at
 * least one required dependency is resolved UNSATISFIED. All other
 * unsatisfactory conditions (cycle, missing endpoint, stale topology, gap,
 * out-of-order position, missing eligibility) yield UNKNOWN_UNRESOLVED —
 * never fabricated BLOCKED.
 *
 * Provenance ties each result back to the dependency ID, reducer state,
 * durable position, and topology revision/digest so the projection/replay
 * chain is traceable.
 *
 * The legacy evaluateBlockingPath API is preserved unchanged for existing
 * callers; the V2 predicate is additive.
 */

/** Three-way dependency satisfaction result. */
export type DependencySatisfaction = 'SATISFIED' | 'UNSATISFIED' | 'UNKNOWN_UNRESOLVED';

/** Eligibility of a dependency run. */
export type Eligibility = 'INELIGIBLE' | 'ELIGIBLE' | 'UNKNOWN';

/** Valid reducer states per the DWO v2 reducer vocabulary. */
export type ReducerState = 'ACCEPTED' | 'OPEN' | 'FAILED' | 'CANCELLED' | 'SUPERSEDED' | 'UNKNOWN';

/** A single dependency with full identity for provenance. */
export interface DependencySpec {
  readonly depId: string;
  readonly targetRunRef: string;
  readonly required: boolean;
  readonly reducerState: ReducerState | 'UNKNOWN';
  readonly durablePosition: number | 'UNKNOWN';
  readonly durableWatermark: boolean;
  readonly topologyRevision: string | 'UNKNOWN';
  readonly topologyDigest: string | 'UNKNOWN';
  readonly eligibility: Eligibility;
}

/**
 * Bounded external evidence supplied by the caller.
 *
 * These are NOT optional refinements: without them the corresponding
 * invariants cannot be proven, so the evaluation stays fail-closed
 * (UNKNOWN_UNRESOLVED) rather than assuming a default that would let a
 * fabricated PASS through.
 */
export interface DependencyEvaluationOptions {
  /**
   * The authoritative set of run refs that exist in the current topology.
   * A dependency whose targetRunRef is absent from this set is a missing
   * endpoint. When the set is omitted the membership check is unprovable
   * and endpoint validation degrades to non-empty-ref only.
   */
  readonly topologyNodeSet?: readonly string[];
  /**
   * The reducer's durable high-water mark. Together with the observed
   * dependency positions this is the ONLY evidence that may establish a
   * durable gap; non-adjacent positions alone are not a gap.
   */
  readonly reducerWatermark?: number | 'UNKNOWN';
}

/** Provenance record for one dependency — binds the evidence identity. */
export interface DependencyProvenance {
  readonly depId: string;
  readonly targetRunRef: string;
  readonly reducerState: string | 'UNKNOWN';
  readonly durablePosition: number | 'UNKNOWN';
  readonly topologyRevision: string | 'UNKNOWN';
  readonly topologyDigest: string | 'UNKNOWN';
  readonly eligibility: Eligibility;
}

/** Result of the V2 dependency satisfaction evaluation. */
export interface DependencySatisfactionResult {
  readonly status: DependencySatisfaction;
  readonly blocks: boolean;
  readonly reason: string | null;
  readonly provenance: readonly DependencyProvenance[];
}

/** Reason codes for UNKNOWN_UNRESOLVED. */
export type UnresolvedReason =
  | 'CYCLE_DETECTED'
  | 'MISSING_ENDPOINT'
  | 'STALE_TOPOLOGY'
  | 'STALE_TOPOLOGY_DIGEST'
  | 'DURABLE_GAP'
  | 'OUT_OF_ORDER'
  | 'MISSING_DURABLE_POSITION'
  | 'MISSING_ELIGIBILITY'
  | 'MISSING_REDUCER_STATE'
  | 'MISSING_TOPOLOGY_REVISION'
  | 'MISSING_TOPOLOGY_DIGEST'
  | 'UNKNOWN_UNRESOLVED';

/**
 * Evaluate dependency satisfaction with explicit provenance.
 *
 * - SATISFIED: every required dependency has reducerState == 'ACCEPTED',
 *   eligibility != 'INELIGIBLE', and all identity facts known.
 * - UNSATISFIED: every required dependency has all facts known but at
 *   least one required dep has reducerState != 'ACCEPTED' or is INELIGIBLE.
 * - UNKNOWN_UNRESOLVED: any required dependency has UNKNOWN facts,
 *   a cycle in the dep graph, a missing endpoint, a stale topology,
 *   a durable gap, an out-of-order position, or a missing eligibility.
 *
 * BLOCKS is derived: true only when status == UNSATISFIED and at least
 * one required dependency is UNSATISFIED. UNKNOWN_UNRESOLVED never
 * produces BLOCKS.
 *
 * Anomaly precedence: if ANY dependency has a cycle, missing endpoint,
 * stale topology, gap, out-of-order, or missing eligibility, the
 * entire result is UNKNOWN_UNRESOLVED — never deriving BLOCKS from
 * another dependency's resolved unsatisfaction.
 */
export function evaluateDependencySatisfactionV2(
  runId: string,
  deps: readonly DependencySpec[],
  currentTopologyRevision: string | 'UNKNOWN',
  currentTopologyDigest: string | 'UNKNOWN',
  options: DependencyEvaluationOptions = {},
): DependencySatisfactionResult {
  const provenance: DependencyProvenance[] = [];

  // An empty dependency set cannot be SATISFIED: absence of declared
  // dependencies is unresolved, never proof that nothing is required.
  const requiredDeps = deps.filter((d) => d.required);
  if (deps.length === 0) {
    return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'MISSING_REDUCER_STATE', provenance: [] };
  }

  // Cycle detection via DFS on dependency graph (actual directed edges)
  const adj = new Map<string, string[]>();
  for (const d of deps) {
    if (!adj.has(d.depId)) adj.set(d.depId, []);
    adj.get(d.depId)!.push(d.targetRunRef);
  }
  const visited = new Set<string>();
  const stack = new Set<string>();
  function hasCycle(node: string): boolean {
    if (stack.has(node)) return true;
    if (visited.has(node)) return false;
    visited.add(node);
    stack.add(node);
    for (const next of adj.get(node) ?? []) {
      if (hasCycle(next)) return true;
    }
    stack.delete(node);
    return false;
  }
  for (const d of deps) {
    if (hasCycle(d.depId)) {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'CYCLE_DETECTED', provenance: [] };
    }
  }

  for (const dep of deps) {
    provenance.push({
      depId: dep.depId,
      targetRunRef: dep.targetRunRef,
      reducerState: dep.reducerState,
      durablePosition: dep.durablePosition,
      topologyRevision: dep.topologyRevision,
      topologyDigest: dep.topologyDigest,
      eligibility: dep.eligibility,
    });
  }

  // Missing endpoint: the dependency must name a run that exists in the
  // authoritative topology node set. A non-empty ref that is not a
  // registered node is still a missing endpoint — that is the case the
  // non-empty check alone cannot catch.
  const nodeSet = options.topologyNodeSet;
  for (const dep of deps) {
    if (!dep.targetRunRef) {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'MISSING_ENDPOINT', provenance };
    }
    // C1: if topologyNodeSet is omitted/empty, membership cannot be proven → fail closed
    if (!nodeSet || nodeSet.length === 0) {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'MISSING_ENDPOINT', provenance };
    }
    if (!nodeSet.includes(dep.targetRunRef)) {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'MISSING_ENDPOINT', provenance };
    }
  }

  // Stale topology: any dep's known topology revision differs from current known revision
  if (currentTopologyRevision !== 'UNKNOWN') {
    for (const d of deps) {
      if (
        d.topologyRevision !== 'UNKNOWN' &&
        d.topologyRevision !== currentTopologyRevision
      ) {
        return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'STALE_TOPOLOGY', provenance };
      }
    }
  }

  // Stale topology digest: any dep's known digest differs from current known digest
  if (currentTopologyDigest !== 'UNKNOWN') {
    for (const d of deps) {
      if (
        d.topologyDigest !== 'UNKNOWN' &&
        d.topologyDigest !== currentTopologyDigest
      ) {
        return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'STALE_TOPOLOGY_DIGEST', provenance };
      }
    }
  }

  // Check each required dep for UNKNOWN facts — anomaly-specific reasons.
  // Each condition reports its OWN reason code: a missing durable position
  // is not a missing reducer state, and collapsing them hides which
  // invariant actually failed.
  for (const dep of deps) {
    if (!dep.required) continue;
    if (dep.reducerState === 'UNKNOWN') {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'MISSING_REDUCER_STATE', provenance };
    }
    if (dep.durablePosition === 'UNKNOWN') {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'MISSING_DURABLE_POSITION', provenance };
    }
    if (dep.topologyRevision === 'UNKNOWN') {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'MISSING_TOPOLOGY_REVISION', provenance };
    }
    if (dep.topologyDigest === 'UNKNOWN') {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'MISSING_TOPOLOGY_DIGEST', provenance };
    }
    if (dep.eligibility === 'UNKNOWN') {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'MISSING_ELIGIBILITY', provenance };
    }
  }

  // Ordering and durable-gap checks operate on the SET of durable positions,
  // not on the order the caller happened to supply the array in. Sorting a
  // copy first makes the result invariant under input permutation; using
  // the raw array order would report OUT_OF_ORDER for a merely reordered
  // but semantically identical input.
  const knownPositions = deps
    .filter((d) => d.durablePosition !== 'UNKNOWN')
    .map((d) => ({ depId: d.depId, position: d.durablePosition as number }))
    .sort((a, b) => a.position - b.position);

  // Duplicate durable positions across distinct dependencies are an
  // unprovable ordering fact, not a gap.
  for (let i = 1; i < knownPositions.length; i++) {
    if (knownPositions[i].position === knownPositions[i - 1].position
      && knownPositions[i].depId !== knownPositions[i - 1].depId) {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'OUT_OF_ORDER', provenance };
    }
  }

  // Durable gap: requires EXPLICIT watermark evidence. Non-adjacent
  // positions alone are not a gap — a gap means the reducer's declared
  // high-water mark is beyond the observed durable positions, i.e. events
  // that should exist were never durably observed. Without a known
  // watermark no gap may be inferred.
  const watermark = options.reducerWatermark;
  if (watermark !== undefined && watermark !== 'UNKNOWN' && knownPositions.length > 0) {
    const maxObserved = knownPositions[knownPositions.length - 1].position;
    if (watermark > maxObserved) {
      return { status: 'UNKNOWN_UNRESOLVED', blocks: false, reason: 'DURABLE_GAP', provenance };
    }
  }

  // All required deps known — determine SATISFIED vs UNSATISFIED
  if (requiredDeps.length === 0) {
    return { status: 'SATISFIED', blocks: false, reason: null, provenance };
  }

  const allAccepted = requiredDeps.every(
    (d) => d.reducerState === 'ACCEPTED' && d.eligibility !== 'INELIGIBLE',
  );
  if (allAccepted) {
    return { status: 'SATISFIED', blocks: false, reason: null, provenance };
  }

  // At least one required dep is not ACCEPTED or is INELIGIBLE → UNSATISFIED → derived BLOCKS
  const unsatisfiedDep = requiredDeps.find(
    (d) => d.reducerState !== 'ACCEPTED' || d.eligibility === 'INELIGIBLE',
  );
  const unsatReason = unsatisfiedDep
    ? `dependency ${unsatisfiedDep.depId} reducerState=${unsatisfiedDep.reducerState}${unsatisfiedDep.eligibility === 'INELIGIBLE' ? ' eligibility=INELIGIBLE' : ''}`
    : 'required dependency not accepted';
  return {
    status: 'UNSATISFIED',
    blocks: true,
    reason: unsatReason,
    provenance,
  };
}

/**
 * Derive BLOCKS from a dependency satisfaction result.
 * BLOCKS is purely derived — never fabricated from UNKNOWN inputs.
 */
export function deriveBlocksFromSatisfaction(result: DependencySatisfactionResult): boolean {
  return result.status === 'UNSATISFIED' && result.blocks;
}

/** V2 capability marker — read-only, no effect affordance. */
export interface DependencySatisfactionCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const DEPENDENCY_SATISFACTION_CAPABILITIES: DependencySatisfactionCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
