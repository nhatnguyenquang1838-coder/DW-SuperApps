/** Golden/negative/compatibility coverage for the frozen GWC RunStateRecord v2 mapper. */
import { describe, expect, it } from 'vitest';
import {
  GWC_V2_MAPPER_CAPABILITIES,
  GWC_V2_RUN_STATE_SCHEMA_ID,
  mapGwcV2RunStateRecord,
  type GwcV2RunStateRecord,
} from '@/lib/dwo/gwcV2SourceMapper';
import { PROJECTION_CONTRACT_V2, PROJECTION_CONTRACT_V2_VERSION } from '@/lib/dwo/projectionContract';

function goldenRecord(overrides: Partial<GwcV2RunStateRecord> = {}): GwcV2RunStateRecord {
  return {
    record_id: 'RUN-001-STATE-1',
    schema_id: GWC_V2_RUN_STATE_SCHEMA_ID,
    schema_version: 2,
    run_id: 'run_scrum853_vs1',
    lifecycle_profile: { id: 'gwc.universal-run.v2', version: 2 },
    run_manifest_ref: 'manifest://run_scrum853_vs1/rev1',
    run_manifest_digest: 'a'.repeat(64),
    state_revision: 1,
    predecessor_state_ref: null,
    predecessor_state_digest: null,
    sequence: 0,
    active_gate: 'UR.G2',
    gate_states: {
      'UR.G0': 'PASSED', 'UR.G1': 'PASSED', 'UR.G2': 'ACTIVE',
      'UR.G3': 'NOT_STARTED', 'UR.G4': 'NOT_STARTED', 'UR.G5': 'NOT_STARTED', 'UR.G6': 'NOT_STARTED',
    },
    terminal_state: 'OPEN',
    ...overrides,
  };
}

describe('GWC RunStateRecord v2 golden mapping', () => {
  it('preserves source schema, record/run identity, sequence and all lifecycle states', () => {
    const result = mapGwcV2RunStateRecord(goldenRecord());
    expect(result.source_schema_version).toBe(2);
    expect(result.source_record_id).toBe('RUN-001-STATE-1');
    expect(result.source_sequence).toBe(0);
    expect(result.projection.schemaId).toBe(PROJECTION_CONTRACT_V2);
    expect(result.projection.schemaVersion).toBe(PROJECTION_CONTRACT_V2_VERSION);
    expect(result.projection.recordId).toBe('RUN-001-STATE-1');
    expect(result.projection.runIdentity.runId).toBe('run_scrum853_vs1');
    expect(result.projection.gates).toHaveLength(7);
    expect(result.projection.gates.find((gate) => gate.gate === 'G2')).toEqual({ namespace: 'UR_G', gate: 'G2', state: 'ACTIVE' });
    expect(result.projection.runState).toBe('OPEN');
  });

  it('does not infer absent facts or topology', () => {
    const result = mapGwcV2RunStateRecord(goldenRecord());
    expect(result.projection.runIdentity.runKind).toBe('UNKNOWN');
    expect(result.projection.runIdentity.parentRunRef).toBeNull();
    expect(result.projection.runIdentity.childRunRefs).toEqual([]);
    expect(result.projection.syncState).toBe('UNAVAILABLE');
    expect(result.projection.authorityState).toBe('UNKNOWN');
    expect(result.projection.anomalyCount).toBeNull();
  });

  it('preserves explicit source parent/child references', () => {
    const result = mapGwcV2RunStateRecord(goldenRecord({ parent_run_ref: 'run_parent', child_run_ref: 'run_child' }));
    expect(result.projection.runIdentity.parentRunRef).toBe('run_parent');
    expect(result.projection.runIdentity.childRunRefs).toEqual(['run_child']);
  });
});

describe('GWC v2 source compatibility and negative behavior', () => {
  it('rejects unsupported schema versions', () => {
    expect(() => mapGwcV2RunStateRecord(goldenRecord({ schema_version: 1 as 2 }))).toThrow(/schema\/version/);
  });

  it('rejects missing lifecycle gate state rather than synthesizing it', () => {
    const source = goldenRecord({ gate_states: { ...goldenRecord().gate_states, 'UR.G3': undefined as never } });
    expect(() => mapGwcV2RunStateRecord(source)).toThrow(/UR.G3/);
  });

  it('rejects unknown active gate values', () => {
    expect(() => mapGwcV2RunStateRecord(goldenRecord({ active_gate: 'UR.G9' as never }))).toThrow(/active_gate/);
  });

  it('maps explicit terminal states without substituting accepted/closure semantics', () => {
    const result = mapGwcV2RunStateRecord(goldenRecord({ terminal_state: 'FAILED' }));
    expect(result.projection.runState).toBe('FAILED');
  });
});

describe('read-only boundary', () => {
  it('does not grant effect capabilities', () => {
    expect(GWC_V2_MAPPER_CAPABILITIES).toEqual({ read: true, write: false, approve: false, deny: false, merge: false, deploy: false });
  });
});
