/**
 * CR-823-A — DWO Projection Contract v2 schema + versioning/upcast.
 *
 * SCRUM-823 / DWO-V2-02, G2 EXECUTE, PLAN-823-R1, child run CR-823-A.
 *
 * The versioned DWO Projection Contract v2. It is ADDITIVE and VERSIONED: each
 * revision preserves historical semantic integrity, and upcast rules move older
 * revisions forward without rewriting them.
 *
 * Design decisions:
 *  1. The contract is versioned (schema_version). A revision is immutable once
 *     frozen; later revisions are additive and carry explicit upcast rules.
 *  2. UR-G* lifecycle namespace is SEPARATE from GWC-* effect/governance namespace.
 *     A UR-G* gate is never reinterpreted as a GWC-* effect gate and vice versa.
 *  3. Recursive Run identity: run_id is immutable; Parent/Child relationships are
 *     explicit; ChildRuns own their own lifecycle.
 *  4. Correlation/causation/trace metadata is EVIDENCE METADATA ONLY — it never
 *     becomes Run identity or authority.
 */

/** The canonical Projection Contract v2 schema id. */
export const PROJECTION_CONTRACT_V2 = 'gwc.dwo.projection-contract-v2';
export const PROJECTION_CONTRACT_V2_VERSION = 2;

/** Lifecycle namespace. UR-G* is Universal lifecycle; GWC-* is effect/governance. */
export type LifecycleNamespace = 'UR_G' | 'GWC_EFFECT';

/** A gate position in the UR-G* lifecycle namespace. */
export type UrGate = 'G0' | 'G1' | 'G2' | 'G3' | 'G4' | 'G5' | 'G6';

/** A gate position in the GWC-* effect/governance namespace. */
export type GwcGate = 'G3_PR' | 'G4_MERGE' | 'G5_DEPLOY' | 'G6_PRODUCTION_DATA';

/** Gate state projection (kernel §5.1). */
export type GateState = 'NOT_STARTED' | 'ACTIVE' | 'WAITING' | 'BLOCKED' | 'PASSED' | 'FAILED';

/** Run terminal state (kernel §5.2). UNKNOWN = not recorded by the source. */
export type RunState = 'OPEN' | 'ACCEPTED' | 'FAILED' | 'CANCELLED' | 'SUPERSEDED' | 'UNKNOWN';

/** Run kind (kernel §2.1). UNKNOWN = not recorded by the source. */
export type RunKind = 'ROOT' | 'CHILD' | 'ATOMIC' | 'UNKNOWN';

/**
 * A gate reference is namespace-qualified so UR-G* and GWC-* can never be
 * conflated. This is the structural enforcement of the namespace separation.
 */
export interface GateRef {
  readonly namespace: LifecycleNamespace;
  readonly gate: UrGate | GwcGate;
  readonly state: GateState;
}

/** Recursive Run identity. run_id is immutable; lineage is explicit. */
export interface RunIdentity {
  readonly runId: string;
  readonly runKind: RunKind;
  readonly parentRunRef: string | null;
  readonly childRunRefs: readonly string[];
  readonly supersededBy?: string;
  readonly rerunOf?: string;
}

/** Correlation/causation/trace metadata — evidence metadata ONLY, never identity/authority. */
export interface CorrelationMetadata {
  readonly traceId?: string;
  readonly spanId?: string;
  readonly causeRefs?: readonly string[];
  readonly correlationRefs?: readonly string[];
}

/** A single Projection Contract v2 record. */
export interface ProjectionRecordV2 {
  readonly schemaId: typeof PROJECTION_CONTRACT_V2;
  readonly schemaVersion: typeof PROJECTION_CONTRACT_V2_VERSION;
  readonly recordId: string;
  readonly runIdentity: RunIdentity;
  readonly gates: readonly GateRef[];
  readonly runState: RunState;
  readonly correlation?: CorrelationMetadata;
  readonly sourceProfile: string;
  readonly syncState: string;
  readonly semanticQualification: string;
  readonly authorityState: string;
  readonly anomalyCount: number | null;
}

/** Upcast rule: moves a v1 record forward to v2 without rewriting history. */
export interface UpcastRule {
  readonly fromVersion: number;
  readonly toVersion: number;
  readonly description: string;
}

/** The registered upcast rules. Additive: v1 -> v2. */
export const UPCAST_RULES: readonly UpcastRule[] = [
  {
    fromVersion: 1,
    toVersion: 2,
    description: 'v1 legacy projection records are upcast to v2 by adding the namespace-qualified gate refs and correlation metadata; historical v1 records are preserved, not rewritten.',
  },
];

/**
 * Assert a record is a valid Projection Contract v2 record.
 * Fails closed on any structural violation.
 */
export function assertProjectionRecordV2(record: ProjectionRecordV2): void {
  if (record.schemaId !== PROJECTION_CONTRACT_V2) {
    throw new Error(`schemaId ${record.schemaId}, expected ${PROJECTION_CONTRACT_V2}`);
  }
  if (record.schemaVersion !== PROJECTION_CONTRACT_V2_VERSION) {
    throw new Error(`schemaVersion ${record.schemaVersion}, expected ${PROJECTION_CONTRACT_V2_VERSION}`);
  }
  if (!record.recordId) throw new Error('recordId is required');
  if (!record.runIdentity.runId) throw new Error('runId is required');
  // UR-G* and GWC-* gates are distinct values but share numeric positions.
  // Compare those positions; comparing the gate strings themselves can never
  // detect cross-namespace conflation because the two vocabularies are disjoint.
  const urPositions = new Set(
    record.gates
      .filter((g) => g.namespace === 'UR_G')
      .map((g) => Number(g.gate.slice(1, 2))),
  );
  const gwcGates = record.gates
    .filter((g) => g.namespace === 'GWC_EFFECT')
    .map((g) => g.gate);
  for (const gate of gwcGates) {
    if (urPositions.has(Number(gate.slice(1, 2)))) {
      throw new Error(`gate ${gate} conflated across UR-G* and GWC-* namespaces`);
    }
  }
}

/**
 * Upcast a v1 record to v2. The v1 record is preserved (immutable history); the
 * returned v2 record is a new additive view.
 *
 * FAIL-CLOSED (GPT review): a v1 input carries only { recordId, runId }. Facts
 * the v1 source did NOT record must map to UNKNOWN / legacy-unqualified — never
 * to optimistic inference (LIVE / NOT_REQUIRED / 0 / OPEN / ATOMIC). Fabricating
 * "healthy" values would certify state the evidence does not support.
 */
export function upcastV1ToV2(v1: { recordId: string; runId: string }): ProjectionRecordV2 {
  return {
    schemaId: PROJECTION_CONTRACT_V2,
    schemaVersion: PROJECTION_CONTRACT_V2_VERSION,
    recordId: v1.recordId,
    runIdentity: { runId: v1.runId, runKind: 'UNKNOWN', parentRunRef: null, childRunRefs: [] },
    gates: [],
    runState: 'UNKNOWN',
    sourceProfile: 'COMPATIBILITY_LEGACY',
    syncState: 'UNAVAILABLE',
    semanticQualification: 'INCOMPATIBLE',
    authorityState: 'UNKNOWN',
    anomalyCount: null,
  };
}

/** The contract is read-only data; it grants no effect capability. */
export interface ContractCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const CONTRACT_CAPABILITIES: ContractCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
