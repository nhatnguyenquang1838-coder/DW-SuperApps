/**
 * CR-821-D verification suite — R0 rebind evidence record + DEV_BINDING_ACTIVE.
 *
 * AC-821-05  recurring R0 rebind evidence record schema defined and immutable per
 *            revision
 * AC-821-08  exit token DEV_BINDING_ACTIVE derivable from machine-readable state
 */
import { describe, expect, it } from 'vitest';
import {
  REBIND_RECORD_SCHEMA_ID,
  REBIND_RECORD_SCHEMA_VERSION,
  createRebindRecord,
  deriveDevBindingActive,
  type RebindEvidenceInput,
} from '@/lib/dwo/rebindRecord';
import { resolveNativeBinding, type NativeSourceResolution } from '@/lib/dwo/releaseBinding';

const UR_DEV = '5c4e4a53fe6ceaceac05f233409c3dd20f17f4f3';
const UR_DEV_NEXT = '7f270f367b36b748c6b0e7afa4c51c4c998123ee';
const DIGEST = '5ae7f38a4efe374966b497004dbe18ea30c24e3b';

function rebindInput(overrides: Partial<RebindEvidenceInput> = {}): RebindEvidenceInput {
  return {
    previousSha: UR_DEV,
    newSha: UR_DEV_NEXT,
    lifecycleProfileId: 'gwc.universal-run',
    lifecycleProfileVersion: 1,
    contractDigest: DIGEST,
    driftClassification: 'ADAPTER_CHANGE',
    affectedSurfaces: ['ADAPTER', 'PROJECTION_CONTRACT_V2'],
    provenanceRef: 'plan:PLAN-821-R2',
    ...overrides,
  };
}

function nativeBinding() {
  const resolution: NativeSourceResolution = {
    universalRepository: 'nhatnguyenquang1838-coder/gwc',
    logicalReleaseDevelopmentRef: 'fix/SCRUM-781-m1-runtime-contract-convergence',
    exactConsumedSha: UR_DEV,
    contractDigest: DIGEST,
    boundAt: '2026-09-30T03:31:00Z',
    affectedSurfaces: ['PROJECTION_CONTRACT_V2', 'UNIVERSAL_RUN_REDUCER'],
  };
  const result = resolveNativeBinding(resolution);
  if (!result.ok) throw new Error('test fixture failed to build native binding');
  return result.binding;
}

describe('AC-821-05 · R0 rebind evidence record schema', () => {
  it('records the full schema identity and immutable fields', () => {
    const result = createRebindRecord('SCRUM-821', 1, '2026-09-30T03:46:00Z', rebindInput());
    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error('unreachable');
    expect(result.record.schemaId).toBe(REBIND_RECORD_SCHEMA_ID);
    expect(result.record.schemaVersion).toBe(REBIND_RECORD_SCHEMA_VERSION);
    expect(result.record.revision).toBe(1);
    expect(result.record.previousSha).toBe(UR_DEV);
    expect(result.record.newSha).toBe(UR_DEV_NEXT);
    expect(result.record.contractDigest).toBe(DIGEST);
    expect(result.record.driftClassification).toBe('ADAPTER_CHANGE');
    expect(result.record.affectedSurfaces).toEqual(['ADAPTER', 'PROJECTION_CONTRACT_V2']);
    expect(result.record.provenanceRef).toBe('plan:PLAN-821-R2');
  });

  it('rejects malformed SHAs and digests', () => {
    for (const bad of ['main', 'abc', '5c4e4a53', '']) {
      const result = createRebindRecord('SCRUM-821', 1, '2026-09-30T03:46:00Z', rebindInput({ newSha: bad }));
      expect(result.ok, `newSha ${JSON.stringify(bad)}`).toBe(false);
    }
    const badPrev = createRebindRecord('SCRUM-821', 1, '2026-09-30T03:46:00Z', rebindInput({ previousSha: 'short' }));
    expect(badPrev.ok).toBe(false);
    const badDigest = createRebindRecord('SCRUM-821', 1, '2026-09-30T03:46:00Z', rebindInput({ contractDigest: 'nope' }));
    expect(badDigest.ok).toBe(false);
  });

  it('rejects an unknown drift classification — the taxonomy is a closed enum', () => {
    const result = createRebindRecord('SCRUM-821', 1, '2026-09-30T03:46:00Z', rebindInput({ driftClassification: 'BIG_MOVE' as never }));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/unknown drift classification/);
  });

  it('rejects an unsupported lifecycle profile identity', () => {
    const result = createRebindRecord('SCRUM-821', 1, '2026-09-30T03:46:00Z', rebindInput({ lifecycleProfileVersion: 2 }));
    expect(result.ok).toBe(false);
  });

  it('rejects a non-positive or non-integer revision', () => {
    expect(createRebindRecord('SCRUM-821', 0, '2026-09-30T03:46:00Z', rebindInput()).ok).toBe(false);
    expect(createRebindRecord('SCRUM-821', 1.5, '2026-09-30T03:46:00Z', rebindInput()).ok).toBe(false);
  });
});

describe('AC-821-08 · DEV_BINDING_ACTIVE derivation', () => {
  it('derives DEV_BINDING_ACTIVE from a coherent native binding + non-blocking drift', () => {
    const decision = deriveDevBindingActive({
      nativeBinding: nativeBinding(),
      drift: 'ADAPTER_CHANGE',
    });
    expect(decision.derivable).toBe(true);
    expect(decision.token).toBe('DEV_BINDING_ACTIVE');
    expect(decision.reasons).toEqual([]);
  });

  it('fails closed when no native binding exists', () => {
    const decision = deriveDevBindingActive({ nativeBinding: null, drift: 'COMPATIBLE' });
    expect(decision.derivable).toBe(false);
    expect(decision.token).toBeNull();
    expect(decision.reasons).toContain('no active native Universal binding established');
  });

  it('fails closed when drift is BLOCKING_CONTRACT_DRIFT', () => {
    const decision = deriveDevBindingActive({
      nativeBinding: nativeBinding(),
      drift: 'BLOCKING_CONTRACT_DRIFT',
    });
    expect(decision.derivable).toBe(false);
    expect(decision.token).toBeNull();
    expect(decision.reasons).toContain('drift classification is BLOCKING_CONTRACT_DRIFT — replan required');
  });

  it('fails closed on an unknown drift value', () => {
    const decision = deriveDevBindingActive({ nativeBinding: nativeBinding(), drift: 'MAYBE' as never });
    expect(decision.derivable).toBe(false);
  });

  it('holds for every non-blocking drift classification', () => {
    for (const drift of ['COMPATIBLE', 'ADAPTER_CHANGE', 'REDUCER_CHANGE', 'UI_CHANGE', 'QUALIFICATION_CHANGE'] as const) {
      const decision = deriveDevBindingActive({ nativeBinding: nativeBinding(), drift });
      expect(decision.derivable, drift).toBe(true);
      expect(decision.token).toBe('DEV_BINDING_ACTIVE');
    }
  });
});