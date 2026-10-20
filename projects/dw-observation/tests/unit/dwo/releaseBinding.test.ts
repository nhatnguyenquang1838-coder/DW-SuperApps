/**
 * CR-821-A verification suite.
 *
 * Every test maps to an acceptance criterion. These assertions ARE the G3 evidence
 * for CR-821-A; the exit token is never claimed from implementation confidence.
 *
 * AC-821-01 registry records full source identity
 * AC-821-03 compatibility vs native namespace separation
 * AC-821-07 fail-closed on missing SHA / unresolvable ref / no main fallback
 */
import { describe, expect, it } from 'vitest';
import {
  BINDING_STAGES,
  DRIFT_CLASSIFICATIONS,
  DWO_BINDING_CAPABILITIES,
  UNIVERSAL_RUN_LIFECYCLE_PROFILE_V1,
  isExactSha,
  readNativeField,
  resolveCompatibilityBinding,
  resolveNativeBinding,
  type NativeSourceResolution,
  type SourceBinding,
} from '@/lib/dwo/releaseBinding';

const UR_DEV = '5c4e4a53fe6ceaceac05f233409c3dd20f17f4f3';
const GWC_MAIN = '414002f92d48083e7133236346b26e3a2a047e33';
const CONTRACT_DIGEST = '5ae7f38a4efe374966b497004dbe18ea30c24e3b';
const BOUND_AT = '2026-09-30T03:31:00Z';
const REPO = 'nhatnguyenquang1838-coder/gwc';

function nativeResolution(overrides: Partial<NativeSourceResolution> = {}): NativeSourceResolution {
  return {
    universalRepository: REPO,
    logicalReleaseDevelopmentRef: 'fix/SCRUM-781-m1-runtime-contract-convergence',
    exactConsumedSha: UR_DEV,
    contractDigest: CONTRACT_DIGEST,
    boundAt: BOUND_AT,
    affectedSurfaces: ['PROJECTION_CONTRACT_V2', 'UNIVERSAL_RUN_REDUCER'],
    ...overrides,
  };
}

describe('AC-821-01 · release-binding registry records exact source identity', () => {
  it('records repository, logical ref, exact consumed SHA, lifecycle profile, contract digest, timestamp and affected surfaces', () => {
    const result = resolveNativeBinding(nativeResolution());
    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error('unreachable');

    expect(result.binding.universalRepository).toBe(REPO);
    expect(result.binding.logicalReleaseDevelopmentRef).toBe('fix/SCRUM-781-m1-runtime-contract-convergence');
    expect(result.binding.exactConsumedSha).toBe(UR_DEV);
    expect(result.binding.lifecycleProfile).toEqual(UNIVERSAL_RUN_LIFECYCLE_PROFILE_V1);
    expect(result.binding.contractDigest).toBe(CONTRACT_DIGEST);
    expect(result.binding.boundAt).toBe(BOUND_AT);
    expect(result.binding.affectedSurfaces).toEqual(['PROJECTION_CONTRACT_V2', 'UNIVERSAL_RUN_REDUCER']);
    expect(result.binding.namespace).toBe('NATIVE_UNIVERSAL');
  });

  it('treats the bound Universal source as the designated release-development line, not a moving head', () => {
    // NBR-014: a moving ref is never certification evidence. The binding must carry
    // BOTH the logical line and the exact SHA, and the SHA is what is authoritative.
    const result = resolveNativeBinding(nativeResolution());
    if (!result.ok) throw new Error('unreachable');
    expect(isExactSha(result.binding.exactConsumedSha)).toBe(true);
    expect(result.binding.logicalReleaseDevelopmentRef).not.toBe(result.binding.exactConsumedSha);
  });

  it('exposes exactly the canonical binding-stage and drift vocabularies', () => {
    expect(BINDING_STAGES).toEqual([
      'RELEASE_DEV_TRACKING',
      'MAIN_REBIND_PENDING',
      'RELEASE_MAIN_BOUND',
    ]);
    expect(DRIFT_CLASSIFICATIONS).toEqual([
      'COMPATIBLE',
      'ADAPTER_CHANGE',
      'REDUCER_CHANGE',
      'UI_CHANGE',
      'QUALIFICATION_CHANGE',
      'BLOCKING_CONTRACT_DRIFT',
    ]);
  });
});

describe('AC-821-07 · registry fails closed', () => {
  it('rejects a missing exact SHA rather than accepting the branch name', () => {
    const result = resolveNativeBinding(nativeResolution({ exactConsumedSha: null }));
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error('unreachable');
    expect(result.code).toBe('SOURCE_REF_UNRESOLVABLE');
    expect(result.mainFallbackProhibited).toBe(true);
  });

  it('rejects a non-40-hex SHA (truncated, abbreviated or symbolic)', () => {
    for (const bad of ['5c4e4a53', '5c4e4a53fe6ceaceac05f233409c3dd20f17f4f3~1', 'main', '', 'ZZZZ']) {
      const result = resolveNativeBinding(nativeResolution({ exactConsumedSha: bad }));
      expect(result.ok, `expected reject for ${JSON.stringify(bad)}`).toBe(false);
      if (result.ok) throw new Error('unreachable');
      expect(['SOURCE_SHA_MISSING', 'SOURCE_REF_UNRESOLVABLE']).toContain(result.code);
    }
  });

  it('rejects a missing contract digest — an unpinned contract is not a binding', () => {
    const result = resolveNativeBinding(nativeResolution({ contractDigest: null }));
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error('unreachable');
    expect(result.code).toBe('SOURCE_SHA_MISSING');
  });

  it('rejects an unsupported lifecycle profile with the kernel reason code', () => {
    const result = resolveNativeBinding(
      nativeResolution({ lifecycleProfile: { id: 'gwc.universal-run', version: 2 } }),
    );
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error('unreachable');
    expect(result.code).toBe('CONTRACT_IDENTITY_UNSUPPORTED');
  });

  it('NEVER substitutes gwc/main when the native source is unresolvable (AC-RB-02 / ADR-11)', () => {
    const result = resolveNativeBinding(nativeResolution({ exactConsumedSha: null }));
    if (result.ok) throw new Error('unreachable');
    // The failure carries no binding at all, so there is nothing a caller could
    // mistake for the compatibility source.
    expect('binding' in result).toBe(false);
    expect(JSON.stringify(result)).not.toContain(GWC_MAIN);
    expect(result.mainFallbackProhibited).toBe(true);
  });

  it('has no API through which a compatibility SHA can be passed as the native source', () => {
    // Structural proof of the no-fallback rule: resolveNativeBinding's only SHA input
    // is the native resolution. There is no fallback/override parameter at all.
    const params = resolveNativeBinding.length;
    expect(params).toBe(1);
  });
});

describe('AC-821-03 · compatibility and native namespaces stay separate', () => {
  it('builds a compatibility binding in its own namespace with an effect-governance-only role', () => {
    const result = resolveCompatibilityBinding(
      nativeResolution({
        logicalReleaseDevelopmentRef: 'main',
        exactConsumedSha: GWC_MAIN,
        contractDigest: CONTRACT_DIGEST,
      }),
    );
    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error('unreachable');
    expect(result.binding.namespace).toBe('GWC_MAIN_COMPATIBILITY');
    expect(result.binding.role).toBe('COMPATIBILITY_AND_EFFECT_GOVERNANCE_ONLY');
    expect(result.binding.exactSha).toBe(GWC_MAIN);
  });

  it('returns null for native fields when handed a compatibility binding', () => {
    const compat = resolveCompatibilityBinding(
      nativeResolution({ exactConsumedSha: GWC_MAIN }),
    );
    if (!compat.ok) throw new Error('unreachable');
    const binding: SourceBinding = compat.binding;
    expect(readNativeField(binding, 'exactConsumedSha')).toBeNull();
    expect(readNativeField(binding, 'contractDigest')).toBeNull();
    expect(readNativeField(binding, 'logicalReleaseDevelopmentRef')).toBeNull();
  });

  it('returns the exact native field when handed a native binding', () => {
    const native = resolveNativeBinding(nativeResolution());
    if (!native.ok) throw new Error('unreachable');
    const binding: SourceBinding = native.binding;
    expect(readNativeField(binding, 'exactConsumedSha')).toBe(UR_DEV);
    expect(readNativeField(binding, 'contractDigest')).toBe(CONTRACT_DIGEST);
  });

  it('never lets a compatibility binding satisfy a native lookup', () => {
    // Even when the SHAs are equal, the namespaces do not cross.
    const same = resolveCompatibilityBinding(nativeResolution({ exactConsumedSha: UR_DEV }));
    if (!same.ok) throw new Error('unreachable');
    expect(readNativeField(same.binding, 'exactConsumedSha')).toBeNull();
  });
});

describe('AC-821-04 · DWO binding exposes no effect capability', () => {
  it('declares read/resolve only and denies every effect affordance', () => {
    expect(DWO_BINDING_CAPABILITIES).toEqual({
      read: true,
      resolve: true,
      write: false,
      approve: false,
      deny: false,
      consumeAuthority: false,
      merge: false,
      deploy: false,
    });
  });

  it('is frozen so no consumer can grant itself a capability', () => {
    expect(Object.isFrozen(DWO_BINDING_CAPABILITIES)).toBe(true);
  });
});

describe('exact-SHA validation primitive', () => {
  it('accepts only 40 lowercase hex characters', () => {
    expect(isExactSha(UR_DEV)).toBe(true);
    expect(isExactSha(UR_DEV.toUpperCase())).toBe(false);
    expect(isExactSha(UR_DEV.slice(0, 39))).toBe(false);
    expect(isExactSha(`${UR_DEV}0`)).toBe(false);
    expect(isExactSha(null)).toBe(false);
    expect(isExactSha(42)).toBe(false);
  });
});
