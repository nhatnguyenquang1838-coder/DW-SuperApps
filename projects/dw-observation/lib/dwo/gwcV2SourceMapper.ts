/**
 * Frozen GWC Universal Run v2 source mapper (SCRUM-853 / VS1).
 *
 * Source binding: gwc/main@c93b722b2a611d805ada803920b92e205ec8cabc,
 * schemas/node-architect/universal-run/run-state-record.schema.json.
 *
 * Maps the exact version-2 RunStateRecord lifecycle facts into DWO's typed
 * projection contract. It preserves record/run identity and every gate state;
 * it does not infer missing parent/child topology, authority, sync health,
 * qualification, acceptance, or timestamps.
 */
import {
  PROJECTION_CONTRACT_V2,
  PROJECTION_CONTRACT_V2_VERSION,
  assertProjectionRecordV2,
  type GateRef,
  type GateState,
  type ProjectionRecordV2,
  type RunIdentity,
  type RunState,
} from './projectionContract';

export const GWC_V2_RUN_STATE_SCHEMA_ID = 'gwc.universal-run.run-state-record.v2' as const;
export const GWC_V2_RUN_STATE_SCHEMA_VERSION = 2 as const;

export type GwcV2Gate = 'UR.G0' | 'UR.G1' | 'UR.G2' | 'UR.G3' | 'UR.G4' | 'UR.G5' | 'UR.G6';
export type GwcV2GateState = 'NOT_STARTED' | 'ACTIVE' | 'WAITING' | 'BLOCKED' | 'PASSED' | 'FAILED';
export type GwcV2TerminalState = 'OPEN' | 'FAILED' | 'CANCELLED' | 'SUPERSEDED';

/** Fields required by frozen RunStateRecord v2; optional lineage refs are source-authored. */
export interface GwcV2RunStateRecord {
  readonly record_id: string;
  readonly schema_id: typeof GWC_V2_RUN_STATE_SCHEMA_ID;
  readonly schema_version: typeof GWC_V2_RUN_STATE_SCHEMA_VERSION;
  readonly run_id: string;
  readonly lifecycle_profile: { readonly id: 'gwc.universal-run.v2'; readonly version: 2 };
  readonly run_manifest_ref: string;
  readonly run_manifest_digest: string;
  readonly state_revision: number;
  readonly predecessor_state_ref: string | null;
  readonly predecessor_state_digest: string | null;
  readonly sequence: number;
  readonly active_gate: GwcV2Gate;
  readonly gate_states: Readonly<Record<GwcV2Gate, GwcV2GateState>>;
  readonly terminal_state: GwcV2TerminalState;
  readonly parent_run_ref?: string;
  readonly child_run_ref?: string;
}

export interface GwcV2RunMapping {
  readonly source_schema_id: typeof GWC_V2_RUN_STATE_SCHEMA_ID;
  readonly source_schema_version: typeof GWC_V2_RUN_STATE_SCHEMA_VERSION;
  readonly source_record_id: string;
  readonly source_sequence: number;
  readonly projection: ProjectionRecordV2;
}

const GATES: readonly GwcV2Gate[] = ['UR.G0', 'UR.G1', 'UR.G2', 'UR.G3', 'UR.G4', 'UR.G5', 'UR.G6'];
const GATE_STATES: readonly GwcV2GateState[] = ['NOT_STARTED', 'ACTIVE', 'WAITING', 'BLOCKED', 'PASSED', 'FAILED'];
const TERMINAL_STATES: readonly GwcV2TerminalState[] = ['OPEN', 'FAILED', 'CANCELLED', 'SUPERSEDED'];

/** Map one exact frozen GWC v2 RunStateRecord. Invalid/missing source facts fail closed by throwing. */
export function mapGwcV2RunStateRecord(source: GwcV2RunStateRecord): GwcV2RunMapping {
  if (source.schema_id !== GWC_V2_RUN_STATE_SCHEMA_ID || source.schema_version !== GWC_V2_RUN_STATE_SCHEMA_VERSION) {
    throw new Error('unsupported GWC RunStateRecord schema/version');
  }
  if (source.lifecycle_profile?.id !== 'gwc.universal-run.v2' || source.lifecycle_profile.version !== 2) {
    throw new Error('unsupported GWC lifecycle profile/version');
  }
  if (!source.record_id || !source.run_id || !Number.isInteger(source.sequence) || source.sequence < 0) {
    throw new Error('RunStateRecord identity and non-negative sequence are required');
  }
  if (!source.active_gate || !GATES.includes(source.active_gate)) throw new Error('unsupported active_gate');
  if (!TERMINAL_STATES.includes(source.terminal_state)) throw new Error('unsupported terminal_state');

  const gates: GateRef[] = GATES.map((sourceGate) => {
    const state = source.gate_states?.[sourceGate];
    if (!state || !GATE_STATES.includes(state)) throw new Error(`missing or unsupported state for ${sourceGate}`);
    return { namespace: 'UR_G', gate: sourceGate.replace('UR.', '') as GateRef['gate'], state: state as GateState };
  });

  const runIdentity: RunIdentity = {
    runId: source.run_id,
    // RunStateRecord v2 does not declare a run-kind field; do not infer it.
    runKind: 'UNKNOWN',
    parentRunRef: source.parent_run_ref ?? null,
    childRunRefs: source.child_run_ref ? [source.child_run_ref] : [],
  };
  const runState = source.terminal_state as RunState;
  const projection: ProjectionRecordV2 = {
    schemaId: PROJECTION_CONTRACT_V2,
    schemaVersion: PROJECTION_CONTRACT_V2_VERSION,
    recordId: source.record_id,
    runIdentity,
    gates,
    runState,
    // The source state record has no sync, qualification, authority, or anomaly fields.
    sourceProfile: 'DEV_NATIVE',
    syncState: 'UNAVAILABLE',
    semanticQualification: 'PENDING',
    authorityState: 'UNKNOWN',
    anomalyCount: null,
  };
  assertProjectionRecordV2(projection);
  return {
    source_schema_id: GWC_V2_RUN_STATE_SCHEMA_ID,
    source_schema_version: GWC_V2_RUN_STATE_SCHEMA_VERSION,
    source_record_id: source.record_id,
    source_sequence: source.sequence,
    projection,
  };
}

/** The mapper is read-only; it grants no effect capability. */
export const GWC_V2_MAPPER_CAPABILITIES = Object.freeze({
  read: true, write: false, approve: false, deny: false, merge: false, deploy: false,
} as const);
