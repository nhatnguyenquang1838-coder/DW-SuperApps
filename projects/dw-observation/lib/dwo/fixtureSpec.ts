/**
 * CR-822-A — DWO-UR-30-V1 fixture spec accessor.
 *
 * SCRUM-822 / DWO-V2-01, G2 EXECUTE, PLAN-822-R1, child run CR-822-A.
 *
 * This module is the machine-readable view of the materialized fixture pack. It
 * exposes the canonical fixture-set metadata and the 30-run catalog so downstream
 * packages (projection contract v2, reducer, UX) can consume the SAME fixture
 * stream through the real projection path — never a parallel UI source of truth.
 *
 * Design decisions:
 *  1. The fixture pack is materialized as data (fixture-set.yaml + runs/*.yaml +
 *     projection-events.jsonl + golden outputs). This module reads that data; it
 *     does NOT re-author fixtures in code.
 *  2. DEV-RUN-020 is the intentional incompatible-source negative fixture. It must
 *     project INCOMPATIBLE and must NOT receive fabricated G0..G6 state.
 *  3. QUALIFIED is never implicit. A fixture projects QUALIFIED only with a
 *     deterministic synthetic qualification record bound to the exact subject.
 *  4. Universal runtime facts and DWO-derived projection fields are separate
 *     namespaces.
 */

/** DWO projection defaults for fixture-native runs (catalog §0.1). */
export interface DwoProjectionDefaults {
  readonly sourceProfile: 'DEV_NATIVE';
  readonly syncState: 'LIVE';
  readonly semanticQualification: 'PENDING';
  readonly authorityState: 'NOT_REQUIRED';
  readonly anomalyCount: 0;
}

export const DWO_PROJECTION_DEFAULTS: DwoProjectionDefaults = Object.freeze({
  sourceProfile: 'DEV_NATIVE',
  syncState: 'LIVE',
  semanticQualification: 'PENDING',
  authorityState: 'NOT_REQUIRED',
  anomalyCount: 0,
} as const);

/** A single fixture run's DWO-expected projection. */
export interface FixtureProjection {
  readonly sourceProfile: string;
  readonly syncState: string;
  readonly semanticQualification: string;
  readonly authorityState: string;
  readonly anomalyCount: number;
}

/** A fixture run's canonical runtime facts (Universal namespace). */
export interface FixtureRuntimeFacts {
  readonly runId: string;
  readonly runKind: string;
  readonly lifecycleProfile: { readonly id: string; readonly version: number };
  readonly domainProfileRef: string;
  readonly targetContractRef: string;
  readonly activeRuntimePlanRef: string;
  readonly activeRuntimePlanRevision: number;
  readonly activeRuntimePlanDigest: string;
  readonly atomic: boolean;
  readonly childRunRefs: readonly string[];
  readonly dependencyRefs: readonly string[];
  readonly parentRunRef: string | null;
  readonly lifecycle: Readonly<Record<string, string>>;
  readonly runState: string;
  readonly waitingReason?: string;
  readonly blockReason?: string;
}

/** A fixture bundle: runtime facts + DWO expected projection, namespaces separate. */
export interface FixtureBundle {
  readonly runtimeFacts: FixtureRuntimeFacts;
  readonly dwoExpectedProjection: FixtureProjection;
}

export interface FixtureSet {
  readonly fixtureSet: string;
  readonly status: string;
  readonly semanticReview: string;
  readonly materialization: string;
  readonly runCount: number;
  readonly conformingRuns: number;
  readonly negativeFixture: string;
  readonly runs: readonly string[];
}

/** The canonical fixture-set id. */
export const DWO_UR_30_V1 = 'DWO-UR-30-V1';

/** The intentional incompatible-source negative fixture. */
export const DEV_RUN_020 = 'DEV-RUN-020';

/** The fixture whose authority is NOT_REQUIRED (no manufactured UNKNOWN/DENIED). */
export const DEV_RUN_030 = 'DEV-RUN-030';

/**
 * The 30-run catalog, mirroring the materialized fixture-set.yaml. This is the
 * canonical table the generator emits from; keeping it here lets tests assert the
 * materialized pack matches the spec without re-parsing YAML in the test.
 */
export const FIXTURE_CATALOG: readonly {
  readonly id: string;
  readonly domain: string;
  readonly kind: string;
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
}[] = [
  { id: 'DEV-RUN-001', domain: 'CORE', kind: 'ROOT', parent: null, gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'recursive Root/ALL_REQUIRED', children: ['DEV-RUN-002', 'DEV-RUN-003', 'DEV-RUN-004'], deps: [] },
  { id: 'DEV-RUN-002', domain: 'CORE', kind: 'ATOMIC', parent: 'DEV-RUN-001', gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'RETRY_STEP', children: [], deps: [] },
  { id: 'DEV-RUN-003', domain: 'CORE', kind: 'ATOMIC', parent: 'DEV-RUN-001', gate: 'G2', gateState: 'BLOCKED', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'dependency unmet', children: [], deps: ['DEV-RUN-002'] },
  { id: 'DEV-RUN-004', domain: 'CORE', kind: 'ATOMIC', parent: 'DEV-RUN-001', gate: 'G2', gateState: 'BLOCKED', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'DENIED', anomalyCount: 0, purpose: 'authority DENIED', children: [], deps: [] },
  { id: 'DEV-RUN-005', domain: 'CORE', kind: 'ROOT', parent: null, gate: 'G3', gateState: 'FAILED', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'parent composition FAIL', children: ['DEV-RUN-006', 'DEV-RUN-007'], deps: [] },
  { id: 'DEV-RUN-006', domain: 'CORE', kind: 'ATOMIC', parent: 'DEV-RUN-005', gate: 'G6', gateState: 'PASSED', runState: 'ACCEPTED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'G4 IN_PLACE', children: [], deps: [] },
  { id: 'DEV-RUN-007', domain: 'CORE', kind: 'ATOMIC', parent: 'DEV-RUN-005', gate: 'G6', gateState: 'PASSED', runState: 'ACCEPTED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'RESET_DERIVED_STATE', children: [], deps: [] },
  { id: 'DEV-RUN-008', domain: 'CORE', kind: 'ROOT', parent: null, gate: 'G4', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'QUORUM 2/3', children: ['DEV-RUN-009', 'DEV-RUN-010', 'DEV-RUN-011'], deps: [] },
  { id: 'DEV-RUN-009', domain: 'CORE', kind: 'ATOMIC', parent: 'DEV-RUN-008', gate: 'G6', gateState: 'PASSED', runState: 'ACCEPTED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'RERUN_STEP', children: [], deps: [] },
  { id: 'DEV-RUN-010', domain: 'CORE', kind: 'ATOMIC', parent: 'DEV-RUN-008', gate: 'G6', gateState: 'PASSED', runState: 'ACCEPTED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'normal success', children: [], deps: [] },
  { id: 'DEV-RUN-011', domain: 'CORE', kind: 'ATOMIC', parent: 'DEV-RUN-008', gate: 'G3', gateState: 'FAILED', runState: 'FAILED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'terminal failure', children: [], deps: [] },
  { id: 'DEV-RUN-012', domain: 'CORE', kind: 'ROOT', parent: null, gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'REPLAN_RUN', children: [], deps: [] },
  { id: 'DEV-RUN-013', domain: 'CORE', kind: 'CHILD', parent: 'DEV-RUN-014', gate: 'G6', gateState: 'CANCELLED', runState: 'CANCELLED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'child gen1 cancelled', children: [], deps: [] },
  { id: 'DEV-RUN-014', domain: 'CORE', kind: 'ROOT', parent: null, gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'RERUN_SUBTREE', children: ['DEV-RUN-013'], deps: [] },
  { id: 'DEV-RUN-015', domain: 'CORE', kind: 'ROOT', parent: null, gate: 'G6', gateState: 'SUPERSEDED', runState: 'SUPERSEDED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'superseded', children: [], deps: [] },
  { id: 'DEV-RUN-016', domain: 'CORE', kind: 'ROOT', parent: null, gate: 'G0', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'RESTART_AS_NEW_RUN', children: [], deps: [] },
  { id: 'DEV-RUN-017', domain: 'EVENT', kind: 'ROOT', parent: null, gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Home Party Root', children: ['DEV-RUN-018'], deps: [] },
  { id: 'DEV-RUN-018', domain: 'EVENT', kind: 'CHILD', parent: 'DEV-RUN-017', gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Food Run', children: ['DEV-RUN-019'], deps: [] },
  { id: 'DEV-RUN-019', domain: 'EVENT', kind: 'ATOMIC', parent: 'DEV-RUN-018', gate: 'G6', gateState: 'PASSED', runState: 'ACCEPTED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Buy Cake', children: [], deps: [] },
  { id: 'DEV-RUN-020', domain: 'CORE', kind: 'NEGATIVE', parent: null, gate: null, gateState: null, runState: 'INCOMPATIBLE', sourceProfile: 'UNKNOWN', syncState: 'UNAVAILABLE', semanticQualification: 'INCOMPATIBLE', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'incompatible-source negative', children: [], deps: [] },
  { id: 'DEV-RUN-021', domain: 'EVENT/PARTY_HOLDING', kind: 'ROOT', parent: null, gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Party Holding Root', children: ['DEV-RUN-022', 'DEV-RUN-023'], deps: [] },
  { id: 'DEV-RUN-022', domain: 'EVENT/PARTY_HOLDING', kind: 'CHILD', parent: 'DEV-RUN-021', gate: 'G5', gateState: 'WAITING', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Guest Coordination', children: [], deps: [] },
  { id: 'DEV-RUN-023', domain: 'EVENT/PARTY_HOLDING', kind: 'CHILD', parent: 'DEV-RUN-021', gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Rain Contingency', children: [], deps: [] },
  { id: 'DEV-RUN-024', domain: 'RESEARCH', kind: 'ROOT', parent: null, gate: 'G3', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Research Root', children: ['DEV-RUN-025', 'DEV-RUN-026'], deps: [] },
  { id: 'DEV-RUN-025', domain: 'RESEARCH', kind: 'CHILD', parent: 'DEV-RUN-024', gate: 'G6', gateState: 'PASSED', runState: 'ACCEPTED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Source Collection', children: [], deps: [] },
  { id: 'DEV-RUN-026', domain: 'RESEARCH', kind: 'CHILD', parent: 'DEV-RUN-024', gate: 'G6', gateState: 'PASSED', runState: 'ACCEPTED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Research Synthesis', children: [], deps: ['DEV-RUN-025'] },
  { id: 'DEV-RUN-027', domain: 'EVENT/WEDDING', kind: 'ROOT', parent: null, gate: 'G2', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Wedding Root', children: ['DEV-RUN-028', 'DEV-RUN-029', 'DEV-RUN-030'], deps: [] },
  { id: 'DEV-RUN-028', domain: 'EVENT/WEDDING', kind: 'CHILD', parent: 'DEV-RUN-027', gate: 'G6', gateState: 'PASSED', runState: 'ACCEPTED', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Venue Booking', children: [], deps: [] },
  { id: 'DEV-RUN-029', domain: 'EVENT/WEDDING', kind: 'CHILD', parent: 'DEV-RUN-027', gate: 'G2', gateState: 'BLOCKED', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Catering Selection', children: [], deps: ['DEV-RUN-028'] },
  { id: 'DEV-RUN-030', domain: 'EVENT/WEDDING', kind: 'CHILD', parent: 'DEV-RUN-027', gate: 'G5', gateState: 'ACTIVE', runState: 'OPEN', sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, purpose: 'Ceremony Day', children: [], deps: [] },
];

/** Assert the catalog has exactly 30 runs, 29 conforming + 1 negative. */
export function assertFixtureCatalogInvariants(catalog: typeof FIXTURE_CATALOG): void {
  if (catalog.length !== 30) {
    throw new Error(`expected 30 fixtures, got ${catalog.length}`);
  }
  const ids = new Set(catalog.map((f) => f.id));
  if (ids.size !== 30) {
    throw new Error('duplicate fixture ids');
  }
  const negative = catalog.filter((f) => f.kind === 'NEGATIVE');
  if (negative.length !== 1 || negative[0].id !== DEV_RUN_020) {
    throw new Error('expected exactly one negative fixture DEV-RUN-020');
  }
  const conforming = catalog.filter((f) => f.kind !== 'NEGATIVE');
  if (conforming.length !== 29) {
    throw new Error(`expected 29 conforming runs, got ${conforming.length}`);
  }
}

/**
 * Resolve a fixture's DWO projection, applying the catalog defaults.
 *
 * DEV-RUN-020 fails closed as INCOMPATIBLE (no fabricated G0..G6). Every other
 * fixture inherits the defaults unless it explicitly overrides.
 */
export function resolveFixtureProjection(
  fixture: (typeof FIXTURE_CATALOG)[number],
): FixtureProjection {
  if (fixture.id === DEV_RUN_020) {
    return {
      sourceProfile: 'UNKNOWN',
      syncState: 'UNAVAILABLE',
      semanticQualification: 'INCOMPATIBLE',
      authorityState: 'NOT_REQUIRED',
      anomalyCount: 0,
    };
  }
  return {
    sourceProfile: fixture.sourceProfile,
    syncState: fixture.syncState,
    semanticQualification: fixture.semanticQualification,
    authorityState: fixture.authorityState,
    anomalyCount: fixture.anomalyCount,
  };
}

/** True when a fixture projects QUALIFIED — only valid with a qualification record. */
export function isQualified(fixture: (typeof FIXTURE_CATALOG)[number]): boolean {
  return fixture.semanticQualification === 'QUALIFIED';
}

/** The fixture pack exposes read-only data; it grants no effect capability. */
export interface FixtureCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const FIXTURE_CAPABILITIES: FixtureCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
