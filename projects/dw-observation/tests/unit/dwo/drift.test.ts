/**
 * CR-821-B verification suite — drift classification (FNR-03).
 *
 * The interesting cases are the ones the handoff calls out by name:
 *   - head movement that does NOT restart the Epic
 *   - REPLAN_REQUIRED only for genuinely blocking drift
 *   - fail-closed when drift cannot be scoped
 */
import { describe, expect, it } from 'vitest';
import {
  DRIFT_CAPABILITIES,
  DRIFT_CLASSIFICATIONS,
  classifyDrift,
  requiresReplan,
  type ContractSurface,
  type DriftEvidence,
} from '@/lib/dwo/drift';

const UR_DEV = '5c4e4a53fe6ceaceac05f233409c3dd20f17f4f3';
const UR_DEV_NEXT = '7f270f367b36b748c6b0e7afa4c51c4c998123ee';
const GWC_MAIN = '414002f92d48083e7133236346b26e3a2a047e33';
const DIGEST_A = '5ae7f38a4efe374966b497004dbe18ea30c24e3b';
const DIGEST_B = '9f2c1b7d4e6a8c0f2b4d6e8a0c2f4b6d8e0a2c4f';

function evidence(overrides: Partial<DriftEvidence> = {}): DriftEvidence {
  return {
    previousSha: UR_DEV,
    currentSha: UR_DEV_NEXT,
    previousContractDigest: DIGEST_A,
    currentContractDigest: DIGEST_A,
    changedSurfaces: [],
    lifecycleProfileChanged: false,
    ...overrides,
  };
}

describe('AC-821-06 · drift classification uses the canonical FNR-03 taxonomy', () => {
  it('exposes exactly the six canonical values, in canonical order', () => {
    expect(DRIFT_CLASSIFICATIONS).toEqual([
      'COMPATIBLE',
      'ADAPTER_CHANGE',
      'REDUCER_CHANGE',
      'UI_CHANGE',
      'QUALIFICATION_CHANGE',
      'BLOCKING_CONTRACT_DRIFT',
    ]);
  });

  it('has no numeric magnitude path — classification is enum-only', () => {
    // Two unrelated SHAs with an identical contract are COMPATIBLE. FNR-03 forbids
    // scoring drift by how far the head moved.
    const far = classifyDrift(
      evidence({ previousSha: UR_DEV, currentSha: GWC_MAIN }),
    );
    expect(far.classification).toBe('COMPATIBLE');
    expect(far.directive).not.toBe('REPLAN_REQUIRED');
  });

  it('classifies each contract surface to its taxonomy value', () => {
    const cases: Array<[ContractSurface, string]> = [
      ['ADAPTER', 'ADAPTER_CHANGE'],
      ['REDUCER', 'REDUCER_CHANGE'],
      ['UI', 'UI_CHANGE'],
      ['QUALIFICATION', 'QUALIFICATION_CHANGE'],
    ];
    for (const [surface, expected] of cases) {
      const d = classifyDrift(evidence({ changedSurfaces: [surface] }));
      expect(d.classification, `surface ${surface}`).toBe(expected);
      expect(d.directive).toBe('AFFECTED_REVALIDATION');
      expect(d.surfacesToRevalidate).toEqual([surface]);
    }
  });
});

describe('head movement alone does not restart the Epic', () => {
  it('treats a moved head with a byte-identical contract as COMPATIBLE', () => {
    const d = classifyDrift(evidence());
    expect(d.classification).toBe('COMPATIBLE');
    expect(d.headMovedContractUnchanged).toBe(true);
    expect(d.surfacesToRevalidate).toEqual([]);
  });

  it('reports NO_ACTION when the exact SHA did not move at all', () => {
    const d = classifyDrift(evidence({ currentSha: UR_DEV }));
    expect(d.classification).toBe('COMPATIBLE');
    expect(d.directive).toBe('NO_ACTION');
    expect(d.headMovedContractUnchanged).toBe(false);
  });
});

describe('REPLAN_REQUIRED is reserved for genuinely blocking drift', () => {
  it('does NOT replan for any non-blocking classification', () => {
    for (const c of ['COMPATIBLE', 'ADAPTER_CHANGE', 'REDUCER_CHANGE', 'UI_CHANGE', 'QUALIFICATION_CHANGE'] as const) {
      expect(requiresReplan(c), `${c} must not replan`).toBe(false);
    }
    expect(requiresReplan('BLOCKING_CONTRACT_DRIFT')).toBe(true);
  });

  it('replans when the source declares itself incompatible', () => {
    const d = classifyDrift(evidence({ declaresIncompatible: true }));
    expect(d.classification).toBe('BLOCKING_CONTRACT_DRIFT');
    expect(d.directive).toBe('REPLAN_REQUIRED');
  });

  it('replans when the lifecycle profile identity changes', () => {
    const d = classifyDrift(evidence({ lifecycleProfileChanged: true }));
    expect(d.classification).toBe('BLOCKING_CONTRACT_DRIFT');
    expect(d.directive).toBe('REPLAN_REQUIRED');
    expect(d.rationale).toMatch(/unsupported qualification subject/);
  });

  it('fails closed when the contract digest changed but no surface is attributable', () => {
    const d = classifyDrift(
      evidence({ currentContractDigest: DIGEST_B, changedSurfaces: [] }),
    );
    expect(d.classification).toBe('BLOCKING_CONTRACT_DRIFT');
    expect(d.directive).toBe('REPLAN_REQUIRED');
    expect(d.rationale).toMatch(/cannot be scoped/);
  });

  it('does not downgrade an explicit incompatibility when surfaces also changed', () => {
    const d = classifyDrift(
      evidence({ changedSurfaces: ['UI', 'REDUCER'], declaresIncompatible: true }),
    );
    expect(d.classification).toBe('BLOCKING_CONTRACT_DRIFT');
  });
});

describe('precedence — a reducer change is never masked by a UI change', () => {
  it('escalates to REDUCER_CHANGE when a reducer and UI surface both moved', () => {
    // After SCRUM-824 a reducer/core-contract review is mandatory so later UX work
    // cannot hide a reducer semantic defect.
    const d = classifyDrift(evidence({ changedSurfaces: ['UI', 'REDUCER'] }));
    expect(d.classification).toBe('REDUCER_CHANGE');
    expect(d.surfacesToRevalidate).toEqual(['REDUCER', 'UI']);
  });

  it('escalates to REDUCER_CHANGE over ADAPTER_CHANGE', () => {
    const d = classifyDrift(evidence({ changedSurfaces: ['ADAPTER', 'REDUCER'] }));
    expect(d.classification).toBe('REDUCER_CHANGE');
  });

  it('escalates to ADAPTER_CHANGE over QUALIFICATION and UI', () => {
    const d = classifyDrift(evidence({ changedSurfaces: ['UI', 'QUALIFICATION', 'ADAPTER'] }));
    expect(d.classification).toBe('ADAPTER_CHANGE');
    expect(d.surfacesToRevalidate).toEqual(['ADAPTER', 'QUALIFICATION', 'UI']);
  });

  it('deduplicates repeated surfaces in the revalidation set', () => {
    const d = classifyDrift(evidence({ changedSurfaces: ['UI', 'UI', 'ADAPTER'] }));
    expect(d.surfacesToRevalidate).toEqual(['ADAPTER', 'UI']);
  });
});

describe('drift observation grants no capability', () => {
  it('declares observe/classify only and denies ref resolution, rebind and authority', () => {
    expect(DRIFT_CAPABILITIES).toEqual({
      observe: true,
      classify: true,
      resolveRef: false,
      rebind: false,
      writeBinding: false,
      consumeAuthority: false,
    });
    expect(Object.isFrozen(DRIFT_CAPABILITIES)).toBe(true);
  });
});
