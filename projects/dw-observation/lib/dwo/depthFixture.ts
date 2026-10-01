/**
 * R2-C — Recursive depth fixture pack.
 *
 * The DWO-UR-30-V1 catalog tops out at depth 2 (root → child → grandchild),
 * which cannot exercise the recursive invariants the v2 contract states:
 * parent composition at depth, dependency ordering across generations, and
 * the "child PASS never auto-completes the parent" rule across more than one
 * level of nesting.
 *
 * AC-822-02 seals DWO-UR-30-V1 at exactly 30 rows with 29 conforming, so this
 * depth-4 chain is a SEPARATE pack rather than extra catalog rows. It reuses
 * the existing infrastructure — `resolveFixtureProjection` for projections and
 * `buildRunTree` for topology — instead of being a parallel fixture universe.
 *
 * The pack is deliberately not all-green. It carries one positive path that
 * composes and one negative path whose failure modes are each a distinct
 * contract violation, so a depth-4 walk has something to actually detect.
 */

/** One row of the depth pack, shaped like a FIXTURE_CATALOG row. */
export interface DepthFixtureRow {
  readonly id: string;
  readonly domain: string;
  readonly kind: 'ROOT' | 'CHILD' | 'ATOMIC' | 'NEGATIVE';
  readonly parent: string | null;
  readonly gate: string | null;
  readonly gateState: string | null;
  readonly runState: string;
  readonly sourceProfile: string;
  readonly syncState: string;
  readonly semanticQualification: string;
  readonly authorityState: string;
  readonly anomalyCount: number;
  readonly purpose: string;
  readonly children: readonly string[];
  readonly deps: readonly string[];
}

/** The canonical id of the depth-4 pack. */
export const DWO_R2C_DEPTH_4_V1 = 'DWO-R2C-DEPTH-4-V1';

/**
 * The depth-4 pack.
 *
 * DEPTH-A is the positive path: ROOT(d0) → CHILD(d1) → CHILD(d2) → ATOMIC(d3),
 * terminating at an ATOMIC as the contract requires. Its parent sits at
 * G6/PASSED with every child accepted — the exact shape that looks complete by
 * inspection, so the composition contract still has to prove it with evidence.
 *
 * DEPTH-B is the negative path: same depth, but the deepest ATOMIC is a NEGATIVE
 * run (anomaly 1) and its parent is at G4/ACTIVE. A walk must surface both the
 * anomaly and the un-composed parent rather than smoothing them into PASS.
 */
export const DEPTH_FIXTURE_CATALOG: readonly DepthFixtureRow[] = Object.freeze([
  // --- DEPTH-A · positive, composable with full evidence ---
  {
    id: 'R2C-DEPTH-A-ROOT',
    domain: 'CORE',
    kind: 'ROOT',
    parent: null,
    gate: 'G6',
    gateState: 'PASSED',
    runState: 'ACCEPTED',
    sourceProfile: 'DEV_NATIVE',
    syncState: 'LIVE',
    semanticQualification: 'PENDING',
    authorityState: 'NOT_APPLICABLE',
    anomalyCount: 0,
    purpose: 'depth-4 ROOT, children accepted, composition needs its own evidence',
    children: ['R2C-DEPTH-A-L1'],
    deps: [],
  },
  {
    id: 'R2C-DEPTH-A-L1',
    domain: 'CORE',
    kind: 'CHILD',
    parent: 'R2C-DEPTH-A-ROOT',
    gate: 'G6',
    gateState: 'PASSED',
    runState: 'ACCEPTED',
    sourceProfile: 'DEV_NATIVE',
    syncState: 'LIVE',
    semanticQualification: 'PENDING',
    authorityState: 'NOT_APPLICABLE',
    anomalyCount: 0,
    purpose: 'depth-1 CHILD, nests further than the 30-pack reaches',
    children: ['R2C-DEPTH-A-L2'],
    deps: [],
  },
  {
    id: 'R2C-DEPTH-A-L2',
    domain: 'CORE',
    kind: 'CHILD',
    parent: 'R2C-DEPTH-A-L1',
    gate: 'G6',
    gateState: 'PASSED',
    runState: 'ACCEPTED',
    sourceProfile: 'DEV_NATIVE',
    syncState: 'LIVE',
    semanticQualification: 'PENDING',
    authorityState: 'NOT_APPLICABLE',
    anomalyCount: 0,
    purpose: 'depth-2 CHILD, depends on the depth-3 ATOMIC',
    children: ['R2C-DEPTH-A-L3'],
    deps: ['R2C-DEPTH-A-L3'],
  },
  {
    id: 'R2C-DEPTH-A-L3',
    domain: 'CORE',
    kind: 'ATOMIC',
    parent: 'R2C-DEPTH-A-L2',
    gate: 'G6',
    gateState: 'PASSED',
    runState: 'ACCEPTED',
    sourceProfile: 'DEV_NATIVE',
    syncState: 'LIVE',
    semanticQualification: 'PENDING',
    authorityState: 'NOT_APPLICABLE',
    anomalyCount: 0,
    purpose: 'depth-3 ATOMIC, terminates the positive path',
    children: [],
    deps: [],
  },

  // --- DEPTH-B · negative, deep and anomalous ---
  {
    id: 'R2C-DEPTH-B-ROOT',
    domain: 'CORE',
    kind: 'ROOT',
    parent: null,
    gate: 'G4',
    gateState: 'ACTIVE',
    runState: 'OPEN',
    sourceProfile: 'DEV_NATIVE',
    syncState: 'LIVE',
    semanticQualification: 'PENDING',
    authorityState: 'NOT_APPLICABLE',
    anomalyCount: 0,
    purpose: 'depth-4 ROOT not at G6, must not be reported composed',
    children: ['R2C-DEPTH-B-L1'],
    deps: [],
  },
  {
    id: 'R2C-DEPTH-B-L1',
    domain: 'CORE',
    kind: 'CHILD',
    parent: 'R2C-DEPTH-B-ROOT',
    gate: 'G6',
    gateState: 'PASSED',
    runState: 'ACCEPTED',
    sourceProfile: 'DEV_NATIVE',
    syncState: 'LIVE',
    semanticQualification: 'PENDING',
    authorityState: 'NOT_APPLICABLE',
    anomalyCount: 0,
    purpose: 'depth-1 CHILD accepted while its parent is still open',
    children: ['R2C-DEPTH-B-L2'],
    deps: [],
  },
  {
    id: 'R2C-DEPTH-B-L2',
    domain: 'CORE',
    kind: 'CHILD',
    parent: 'R2C-DEPTH-B-L1',
    gate: 'G6',
    gateState: 'PASSED',
    runState: 'ACCEPTED',
    sourceProfile: 'DEV_NATIVE',
    syncState: 'LIVE',
    semanticQualification: 'PENDING',
    authorityState: 'NOT_APPLICABLE',
    anomalyCount: 0,
    purpose: 'depth-2 CHILD, depends on an anomalous ATOMIC',
    children: ['R2C-DEPTH-B-L3'],
    deps: ['R2C-DEPTH-B-L3'],
  },
  {
    id: 'R2C-DEPTH-B-L3',
    domain: 'CORE',
    kind: 'NEGATIVE',
    parent: 'R2C-DEPTH-B-L2',
    gate: 'G3',
    gateState: 'FAILED',
    runState: 'FAILED',
    sourceProfile: 'DEV_NATIVE',
    syncState: 'LIVE',
    semanticQualification: 'PENDING',
    authorityState: 'NOT_APPLICABLE',
    anomalyCount: 1,
    purpose: 'depth-3 NEGATIVE terminal failure, terminates the negative path',
    children: [],
    deps: [],
  },
]);

/**
 * Compute parent-hop depth for every run in a pack.
 * Roots are depth 0. Returns runId → depth.
 */
export function computeDepths(
  catalog: readonly DepthFixtureRow[],
): Readonly<Record<string, number>> {
  const parentOf = new Map(catalog.map((r) => [r.id, r.parent]));
  const depths: Record<string, number> = {};
  for (const row of catalog) {
    let depth = 0;
    let cursor: string | null = row.id;
    const seen = new Set<string>();
    // Count parent hops from this run upwards. A run whose parent is null is
    // a root and therefore depth 0 — the hop is only counted when there IS a
    // parent to hop to.
    while (cursor !== null && parentOf.get(cursor) != null) {
      if (seen.has(cursor)) {
        // A parent cycle would make depth undefined; report it as -1 rather
        // than looping or silently treating it as a root.
        depth = -1;
        break;
      }
      seen.add(cursor);
      const parent = parentOf.get(cursor);
      if (parent === undefined) break;
      cursor = parent;
      depth += 1;
    }
    depths[row.id] = depth;
  }
  return depths;
}

/**
 * Walk the pack from a root and return the ancestry path in hop order.
 * The path terminates when it reaches an ATOMIC or NEGATIVE leaf.
 */
export function walkToLeaf(
  catalog: readonly DepthFixtureRow[],
  rootId: string,
): readonly string[] {
  const byId = new Map(catalog.map((r) => [r.id, r]));
  const path: string[] = [];
  const seen = new Set<string>();
  let cursor: string | null = rootId;

  while (cursor !== null) {
    if (seen.has(cursor)) break; // cycle guard
    seen.add(cursor);
    const row = byId.get(cursor);
    if (!row) break;
    path.push(row.id);
    // A leaf terminates the walk; only governed runs descend further.
    if (row.kind === 'ATOMIC' || row.kind === 'NEGATIVE' || row.children.length === 0) break;
    cursor = row.children[0];
  }
  return path;
}

/** The deepest depth reached by any run in the pack. */
export function maxDepth(catalog: readonly DepthFixtureRow[]): number {
  const depths = Object.values(computeDepths(catalog));
  return depths.length === 0 ? -1 : Math.max(...depths);
}

/** Depth pack is read-only; it grants no effect capability. */
export interface DepthFixtureCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const DEPTH_FIXTURE_CAPABILITIES: DepthFixtureCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
