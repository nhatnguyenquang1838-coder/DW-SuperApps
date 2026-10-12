/**
 * R2-C focused tests — the depth-4 fixture pack.
 *
 * These are INTEGRATION tests, not unit tests of a helper: the pack is fed
 * through the same `buildRunTree`, `resolveFixtureProjection`,
 * `evaluateParentCompositionContract` and `evaluateDependencySatisfactionV2`
 * that production paths use. The point of the pack is to prove the recursive
 * invariants hold at depth, which a unit test of the fixture data itself
 * could not establish.
 *
 * The pack also lives alongside the real fixture infrastructure rather than
 * beside it — AC-822-02 seals DWO-UR-30-V1 at 30 rows, so depth is a separate
 * pack rather than extra catalog rows.
 */

import { describe, expect, it } from 'vitest';
import {
  DWO_R2C_DEPTH_4_V1,
  DEPTH_FIXTURE_CATALOG,
  DEPTH_FIXTURE_CAPABILITIES,
  computeDepths,
  maxDepth,
  walkToLeaf,
} from '@/lib/dwo/depthFixture';
import { buildRunTree, isParentComplete, type RunNode } from '@/lib/dwo/recursiveTopology';
import { resolveFixtureProjection } from '@/lib/dwo/fixtureSpec';
import {
  evaluateParentCompositionContract,
  type ParentCompositionContractV2,
} from '@/lib/dwo/parentComposition';
import {
  evaluateDependencySatisfactionV2,
  type DependencySpec,
} from '@/lib/dwo/dependencySatisfaction';

const REV = 'rev-depth';
const DIGEST = 'sha256:depth-topology';

/** Project the depth pack into the RunNode shape buildRunTree accepts. */
function toRunNodes(): RunNode[] {
  return DEPTH_FIXTURE_CATALOG.map((row) => ({
    runId: row.id,
    runKind: row.kind === 'NEGATIVE' ? 'ATOMIC' : row.kind,
    parentRunRef: row.parent,
    childRunRefs: row.children,
    state: {
      runId: row.id,
      gate: row.gate ?? 'G0',
      gateState: row.gateState ?? 'ACTIVE',
      runState: row.runState,
      sourceProfile: row.sourceProfile,
      syncState: row.syncState,
      semanticQualification: row.semanticQualification,
      authorityState: row.authorityState,
      anomalyCount: row.anomalyCount,
      partial: false,
    },
  } as RunNode));
}

describe('R2-C · the pack reaches depth 4 by parent-child hops', () => {
  it('the pack is identified', () => {
    expect(DWO_R2C_DEPTH_4_V1).toBe('DWO-R2C-DEPTH-4-V1');
    expect(DEPTH_FIXTURE_CATALOG.length).toBe(8);
  });

  it('at least one path reaches depth >= 3 (root = depth 0)', () => {
    // The contract requires depth >= 4 counting the Task hop; within the run
    // topology that is root=0 plus three nested hops. Assert the run-graph
    // depth explicitly rather than trusting the pack's own name.
    expect(maxDepth(DEPTH_FIXTURE_CATALOG)).toBeGreaterThanOrEqual(3);
  });

  it('the positive path is ROOT → CHILD → CHILD → ATOMIC', () => {
    const path = walkToLeaf(DEPTH_FIXTURE_CATALOG, 'R2C-DEPTH-A-ROOT');
    expect(path).toEqual([
      'R2C-DEPTH-A-ROOT',
      'R2C-DEPTH-A-L1',
      'R2C-DEPTH-A-L2',
      'R2C-DEPTH-A-L3',
    ]);
  });

  it('the positive path terminates at an ATOMIC leaf', () => {
    const path = walkToLeaf(DEPTH_FIXTURE_CATALOG, 'R2C-DEPTH-A-ROOT');
    const leaf = DEPTH_FIXTURE_CATALOG.find((r) => r.id === path[path.length - 1])!;
    expect(leaf.kind).toBe('ATOMIC');
    expect(leaf.children).toEqual([]);
  });

  it('every node on the positive path sits at the declared depth', () => {
    const depths = computeDepths(DEPTH_FIXTURE_CATALOG);
    expect(depths['R2C-DEPTH-A-ROOT']).toBe(0);
    expect(depths['R2C-DEPTH-A-L1']).toBe(1);
    expect(depths['R2C-DEPTH-A-L2']).toBe(2);
    expect(depths['R2C-DEPTH-A-L3']).toBe(3);
  });

  it('the negative path is also 4 hops and terminates at a NEGATIVE leaf', () => {
    const path = walkToLeaf(DEPTH_FIXTURE_CATALOG, 'R2C-DEPTH-B-ROOT');
    expect(path).toHaveLength(4);
    const leaf = DEPTH_FIXTURE_CATALOG.find((r) => r.id === path[path.length - 1])!;
    expect(leaf.kind).toBe('NEGATIVE');
    expect(leaf.anomalyCount).toBe(1);
  });

  it('both roots are at depth 0', () => {
    const depths = computeDepths(DEPTH_FIXTURE_CATALOG);
    expect(depths['R2C-DEPTH-A-ROOT']).toBe(0);
    expect(depths['R2C-DEPTH-B-ROOT']).toBe(0);
  });
});

describe('R2-C · the pack feeds the real topology builder', () => {
  it('buildRunTree rejects the pack as-is: two roots is not one tree', () => {
    // This is correct behaviour, and worth pinning: the two paths are separate
    // roots, so the pack is walked per-path rather than as one tree.
    expect(() => buildRunTree(toRunNodes())).toThrow(/exactly one root/);
  });

  it('each path independently builds a valid recursive tree', () => {
    const nodes = toRunNodes();
    const pathA = nodes.filter((n) => n.runId.startsWith('R2C-DEPTH-A-'));
    const tree = buildRunTree(pathA);
    expect(tree.root.runId).toBe('R2C-DEPTH-A-ROOT');
    expect(Object.keys(tree.nodes)).toHaveLength(4);
  });

  it('a parent four levels up is reachable through the tree', () => {
    const nodes = toRunNodes();
    const tree = buildRunTree(nodes.filter((n) => n.runId.startsWith('R2C-DEPTH-A-')));
    // Walk down from the root to prove the nesting is real, not flat.
    let cursor: string | null = 'R2C-DEPTH-A-ROOT';
    let hops = 0;
    while (cursor !== null) {
      const node: RunNode | undefined = tree.nodes[cursor];
      if (!node || node.childRunRefs.length === 0) break;
      cursor = node.childRunRefs[0];
      hops += 1;
    }
    expect(hops).toBe(3);
    expect(cursor).toBe('R2C-DEPTH-A-L3');
  });

  it('the depth pack does not mutate the sealed 30-run catalog', () => {
    // Wiring into existing infrastructure must not extend AC-822-02's pack.
    expect(DEPTH_FIXTURE_CATALOG.some((r) => r.id.startsWith('DEV-RUN-'))).toBe(false);
  });
});

describe('R2-C · projections resolve through the shared accessor', () => {
  it('a conforming depth row projects the standard defaults', () => {
    const row = DEPTH_FIXTURE_CATALOG.find((r) => r.id === 'R2C-DEPTH-A-L3')!;
    const projection = resolveFixtureProjection(row as never);
    expect(projection.sourceProfile).toBe('DEV_NATIVE');
    expect(projection.syncState).toBe('LIVE');
    expect(projection.anomalyCount).toBe(0);
  });

  it('the negative depth row keeps its anomaly rather than being smoothed', () => {
    const row = DEPTH_FIXTURE_CATALOG.find((r) => r.id === 'R2C-DEPTH-B-L3')!;
    const projection = resolveFixtureProjection(row as never);
    expect(projection.anomalyCount).toBe(1);
  });
});

describe('R2-C · dependency relation across generations', () => {
  function depFor(runId: string, deps: readonly string[], position: number): DependencySpec {
    return {
      depId: `${runId}-dep`,
      targetRunRef: deps[0] ?? runId,
      required: true,
      reducerState: 'ACCEPTED',
      durablePosition: position,
      durableWatermark: true,
      topologyRevision: REV,
      topologyDigest: DIGEST,
      eligibility: 'ELIGIBLE',
    };
  }

  it('a depth-2 child depending on its depth-3 ATOMIC child is SATISFIED', () => {
    const nodes = DEPTH_FIXTURE_CATALOG.map((r) => r.id);
    const result = evaluateDependencySatisfactionV2(
      'R2C-DEPTH-A-L2',
      [depFor('R2C-DEPTH-A-L2', ['R2C-DEPTH-A-L3'], 3)],
      REV,
      DIGEST,
      { topologyNodeSet: nodes, reducerWatermark: 3 },
    );
    expect(result.status).toBe('SATISFIED');
    expect(result.blocks).toBe(false);
  });

  it('a dependency on the NEGATIVE leaf still resolves structurally — the anomaly is separate', () => {
    const nodes = DEPTH_FIXTURE_CATALOG.map((r) => r.id);
    const result = evaluateDependencySatisfactionV2(
      'R2C-DEPTH-B-L2',
      [depFor('R2C-DEPTH-B-L2', ['R2C-DEPTH-B-L3'], 7)],
      REV,
      DIGEST,
      { topologyNodeSet: nodes, reducerWatermark: 7 },
    );
    // Dependency satisfaction is about topology/reducer facts, not run health.
    // The anomaly on the leaf is surfaced by the projection, not here.
    expect(result.status).toBe('SATISFIED');
  });

  it('a dependency pointing outside the pack is a missing endpoint', () => {
    const nodes = DEPTH_FIXTURE_CATALOG.map((r) => r.id);
    const result = evaluateDependencySatisfactionV2(
      'R2C-DEPTH-A-L2',
      [depFor('R2C-DEPTH-A-L2', ['SOME-RUN-NOT-IN-PACK'], 3)],
      REV,
      DIGEST,
      { topologyNodeSet: nodes, reducerWatermark: 3 },
    );
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('MISSING_ENDPOINT');
  });

  it('a durable gap at depth is detected against the reducer watermark', () => {
    const nodes = DEPTH_FIXTURE_CATALOG.map((r) => r.id);
    const result = evaluateDependencySatisfactionV2(
      'R2C-DEPTH-A-L2',
      [depFor('R2C-DEPTH-A-L2', ['R2C-DEPTH-A-L3'], 3)],
      REV,
      DIGEST,
      { topologyNodeSet: nodes, reducerWatermark: 99 },
    );
    expect(result.status).toBe('UNKNOWN_UNRESOLVED');
    expect(result.reason).toBe('DURABLE_GAP');
  });
});

describe('R2-C · parent composition evidence across depth', () => {
  const positiveContract: ParentCompositionContractV2 = {
    parentRunId: 'R2C-DEPTH-A-ROOT',
    revisionId: 'r2c-rev-1',
    requiredChildren: [
      { runId: 'R2C-DEPTH-A-L1', completionDigest: 'sha256:a-l1', handoffReceiptRef: 'receipt-a-l1' },
    ],
    optionalChildren: [],
    requiredHandoffReceiptRefs: ['receipt-a-l1'],
    parentVerificationRef: 'verify/a-root.json',
    targetAcceptanceRef: 'accept/a-root.json',
  };

  it('a depth-4 root with every child accepted and full evidence composes', () => {
    const d = evaluateParentCompositionContract(
      positiveContract,
      { gate: 'G6', gateState: 'PASSED' },
      ['receipt-a-l1'],
    );
    expect(d.composed).toBe(true);
    expect(d.accepted).toBe(true);
  });

  it('the same accepted children WITHOUT evidence do not compose', () => {
    // The whole reason this fixture exists: depth-4 with G6/PASSED children
    // looks complete by inspection, and must still require its own proof.
    const d = evaluateParentCompositionContract(
      { ...positiveContract, parentVerificationRef: 'UNKNOWN' },
      { gate: 'G6', gateState: 'PASSED' },
      ['receipt-a-l1'],
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_PARENT_VERIFICATION');
  });

  it('an accepted depth-1 child never auto-completes its still-open root', () => {
    const nodes = toRunNodes();
    const tree = buildRunTree(nodes.filter((n) => n.runId.startsWith('R2C-DEPTH-B-')));
    // The child IS accepted...
    expect(tree.nodes['R2C-DEPTH-B-L1'].state.runState).toBe('ACCEPTED');
    // ...and the root is NOT complete, despite that accepted child.
    expect(isParentComplete(tree, 'R2C-DEPTH-B-ROOT')).toBe(false);
    // The L2 node is also accepted, so acceptance propagates nothing upward:
    // two levels of accepted descendants still leave the root uncompleted.
    expect(tree.nodes['R2C-DEPTH-B-L2'].state.runState).toBe('ACCEPTED');
    expect(isParentComplete(tree, 'R2C-DEPTH-B-ROOT')).toBe(false);
  });

  it('completeness reads the node OWN gate, not its descendants', () => {
    const nodes = toRunNodes();
    const tree = buildRunTree(nodes.filter((n) => n.runId.startsWith('R2C-DEPTH-B-')));
    // L1 sits at G6/PASSED itself, so it IS complete — while its own parent is
    // not. Completeness is a property of a node's own state, which is exactly
    // why it cannot be used to infer a parent's state.
    expect(isParentComplete(tree, 'R2C-DEPTH-B-L1')).toBe(true);
    expect(isParentComplete(tree, 'R2C-DEPTH-B-ROOT')).toBe(false);
    // L2 is at G6/PASSED but is NOT in this tree's required-child position for
    // the root; the root still reads its own G4/ACTIVE.
    expect(tree.nodes['R2C-DEPTH-B-ROOT'].state.gate).toBe('G4');
  });

  it('composition of the negative root stays unresolved even with a G6 parent', () => {
    const d = evaluateParentCompositionContract(
      {
        ...positiveContract,
        parentRunId: 'R2C-DEPTH-B-ROOT',
        requiredChildren: [
          { runId: 'R2C-DEPTH-B-L1', completionDigest: 'sha256:b-l1', handoffReceiptRef: 'receipt-b-l1' },
        ],
        requiredHandoffReceiptRefs: ['receipt-b-l1'],
      },
      { gate: 'G6', gateState: 'PASSED' },
      // The depth-3 NEGATIVE leaf has no handoff receipt to offer.
      [],
    );
    expect(d.composed).toBe(false);
    expect(d.reason).toBe('MISSING_REQUIRED_RECEIPT');
  });
});

describe('R2-C · capability marker', () => {
  it('read-only, no effect affordance', () => {
    expect(DEPTH_FIXTURE_CAPABILITIES).toEqual({
      read: true,
      write: false,
      approve: false,
      deny: false,
      merge: false,
      deploy: false,
    });
    expect(Object.isFrozen(DEPTH_FIXTURE_CAPABILITIES)).toBe(true);
  });
});
