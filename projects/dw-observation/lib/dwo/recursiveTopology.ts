/**
 * CR-824-B — Recursive Root/Child/Atomic reduction + parent composition.
 *
 * SCRUM-824 / DWO-V2-03, G2 EXECUTE, PLAN-824-R1, child run CR-824-B.
 *
 * Recursive Run topology: a ROOT has children, a CHILD has a parent, an ATOMIC run
 * has no governed WORK descendants. Parent composition is INDEPENDENT from
 * child-local PASS (AC-824-04): a parent is not complete merely because its
 * children succeeded.
 *
 * Design decisions:
 *  1. Parent completion is never inferred solely from child-local success. The
 *     parent's own gate/state is authoritative.
 *  2. Recursive reduction walks the tree; each Run's state is reduced from its own
 *     events, and the parent's composition is evaluated independently.
 */

import type { ReducedRunState } from './reducer';

/** A node in the recursive Run topology. */
export interface RunNode {
  readonly runId: string;
  readonly runKind: 'ROOT' | 'CHILD' | 'ATOMIC';
  readonly parentRunRef: string | null;
  readonly childRunRefs: readonly string[];
  readonly state: ReducedRunState;
}

/** The recursive topology of a Run tree. */
export interface RunTree {
  readonly root: RunNode;
  readonly nodes: Readonly<Record<string, RunNode>>;
}

/**
 * Build a recursive Run tree from nodes.
 *
 * Asserts the topology is well-formed: every child's parent points back, every
 * parent's child list is consistent, and there is exactly one root.
 */
export function buildRunTree(nodes: readonly RunNode[]): RunTree {
  const byId = new Map(nodes.map((n) => [n.runId, n]));
  const roots = nodes.filter((n) => n.parentRunRef === null);
  if (roots.length !== 1) {
    throw new Error(`expected exactly one root, got ${roots.length}`);
  }
  for (const n of nodes) {
    if (n.parentRunRef !== null) {
      const parent = byId.get(n.parentRunRef);
      if (!parent) throw new Error(`parent ${n.parentRunRef} of ${n.runId} not found`);
      if (!parent.childRunRefs.includes(n.runId)) {
        throw new Error(`parent ${n.parentRunRef} does not list child ${n.runId}`);
      }
    }
    for (const child of n.childRunRefs) {
      const c = byId.get(child);
      if (!c) throw new Error(`child ${child} of ${n.runId} not found`);
      if (c.parentRunRef !== n.runId) {
        throw new Error(`child ${child} parent is ${c.parentRunRef}, expected ${n.runId}`);
      }
    }
  }
  return { root: roots[0], nodes: Object.fromEntries(byId) };
}

/**
 * Evaluate parent composition.
 *
 * A parent is NOT complete merely because its children succeeded. The parent's own
 * gate/state is authoritative. This returns the parent's own state plus the declared
 * child counts (accepted children are resolved by the caller with the full tree).
 */
export function evaluateParentComposition(
  parent: RunNode,
): { parentState: ReducedRunState; parentComplete: boolean; childrenTotal: number } {
  const childrenTotal = parent.childRunRefs.length;
  const parentComplete = parent.state.gate === 'G6' && parent.state.gateState === 'PASSED';
  return {
    parentState: parent.state,
    parentComplete,
    childrenTotal,
  };
}

/**
 * Determine whether a parent is complete, given the full tree.
 *
 * The parent's own gate/state is authoritative. Child-local success alone never
 * marks the parent complete (AC-824-04).
 */
export function isParentComplete(tree: RunTree, parentId: string): boolean {
  const parent = tree.nodes[parentId];
  if (!parent) throw new Error(`parent ${parentId} not in tree`);
  // Parent completion is its own gate/state, NOT derived from children.
  return parent.state.gate === 'G6' && parent.state.gateState === 'PASSED';
}

/** Recursive topology is read-only; it grants no effect capability. */
export interface TopologyCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const TOPOLOGY_CAPABILITIES: TopologyCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
