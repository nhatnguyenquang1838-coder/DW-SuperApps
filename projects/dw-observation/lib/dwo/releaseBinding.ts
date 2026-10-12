/**
 * CR-821-A — Release-binding registry with fail-closed exact-SHA resolution.
 *
 * SCRUM-821 / DWO-V2-00, G2 EXECUTE, PLAN-821-R2, child run CR-821-A.
 *
 * Contract sources:
 *   - Universal Run Kernel Contract Freeze v1.1 (gwc.universal-run/1)
 *   - C4 Solution Design §0 source binding, §21.4 source_binding record, ADR-11
 *   - BRD AC-RB-01 (exact-source pin), AC-RB-02 (no-main fallback)
 *   - BRD AC-RT-01 (development binding explicit + exact resolved head SHA)
 *   - BRD NFR-014 (moving refs are not certification evidence)
 *   - DWO-UR-30-V1 catalog §0.1 (DWO projection defaults)
 *
 * Invariants this module owns:
 *   1. An exact 40-hex consumed SHA is MANDATORY. A branch name is never evidence.
 *   2. A missing/incompatible UR-DEV native source FAILS CLOSED. It must never
 *      fall back to gwc/main (ADR-11, AC-RB-02).
 *   3. The UR-DEV native semantic source and the GWC-MAIN compatibility source are
 *      SEPARATE records in separate namespaces. One can never populate the other.
 *   4. DWO is a read-only observatory: this registry exposes NO effect capability.
 *   5. Nothing here grants authority. Binding is provenance, not permission.
 */

/** Exact 40-character lowercase hex. Anything else is not an exact source identity. */
export type ExactSha = string;

const EXACT_SHA_PATTERN = /^[0-9a-f]{40}$/;

export function isExactSha(value: unknown): value is ExactSha {
  return typeof value === 'string' && EXACT_SHA_PATTERN.test(value);
}

/**
 * Why a binding could not be established. These are stable reason codes and are
 * deliberately distinct so a failure can be projected without inventing a value.
 */
export type BindingFailureCode =
  /** exact_consumed_sha absent, not 40-hex, or not the resolved SHA. */
  | 'SOURCE_SHA_MISSING'
  /** The logical release-development ref could not be resolved to a SHA. */
  | 'SOURCE_REF_UNRESOLVABLE'
  /** Ref resolved, but a source demanded native semantics it cannot provide. */
  | 'SOURCE_INCOMPATIBLE'
  /** The contract/lifecycle profile identity is missing or unsupported. */
  | 'CONTRACT_IDENTITY_UNSUPPORTED'
  /** Recorded in a namespace that may not hold this record kind. */
  | 'NAMESPACE_VIOLATION';

/**
 * A resolved result that is deliberately NOT a binding. Fail-closed means we return
 * this rather than a partially-populated binding.
 */
export interface BindingFailure {
  readonly ok: false;
  readonly code: BindingFailureCode;
  readonly message: string;
  /** True when the caller was tempted to substitute the compatibility source. */
  readonly mainFallbackProhibited: boolean;
}

export interface BindingSuccess<T> {
  readonly ok: true;
  readonly binding: T;
}

export type BindingResult<T> = BindingSuccess<T> | BindingFailure;

/** The Universal lifecycle profile identity. `gwc.universal-run/1` is the v1 baseline. */
export interface LifecycleProfileIdentity {
  readonly id: string;
  readonly version: number;
}

export const UNIVERSAL_RUN_LIFECYCLE_PROFILE_V1: LifecycleProfileIdentity = {
  id: 'gwc.universal-run',
  version: 1,
};

/** Projection event types, used only to compute the affected-surface set. */
export type DwoSurface =
  | 'PROJECTION_CONTRACT_V2'
  | 'UNIVERSAL_RUN_REDUCER'
  | 'DURABLE_RECONCILIATION'
  | 'RUN_LIST_UX'
  | 'RUN_DETAIL_UX'
  | 'EVIDENCE_INSPECTOR'
  | 'REPLAY_CONTROLLER'
  | 'REALTIME_LIVE'
  | 'QUALIFICATION';

/**
 * The NATIVE Universal semantic source binding.
 *
 * Namespace: native Universal semantics. This is the only record kind that may be
 * projected as native Universal runtime truth.
 */
export interface NativeUniversalSourceBinding {
  readonly namespace: 'NATIVE_UNIVERSAL';
  readonly universalRepository: string;
  /** The LOGICAL release-development line. Never sufficient as evidence on its own. */
  readonly logicalReleaseDevelopmentRef: string;
  /** The exact SHA actually consumed. Mandatory, 40-hex. */
  readonly exactConsumedSha: ExactSha;
  readonly lifecycleProfile: LifecycleProfileIdentity;
  /** JCS + SHA-256 content digest of the consumed contract, per kernel §25.14. */
  readonly contractDigest: ExactSha;
  /** RFC3339 instant the binding was established. */
  readonly boundAt: string;
  readonly affectedSurfaces: readonly DwoSurface[];
}

/**
 * The GWC-MAIN compatibility + effect-governance source.
 *
 * Namespace: compatibility. This record can never satisfy a native semantic lookup.
 */
export interface CompatibilitySourceBinding {
  readonly namespace: 'GWC_MAIN_COMPATIBILITY';
  readonly universalRepository: string;
  readonly ref: string;
  readonly exactSha: ExactSha;
  readonly role: 'COMPATIBILITY_AND_EFFECT_GOVERNANCE_ONLY';
  readonly boundAt: string;
}

export type SourceBinding = NativeUniversalSourceBinding | CompatibilitySourceBinding;

/** Input to the fail-closed native resolver. */
export interface NativeSourceResolution {
  readonly universalRepository: string;
  readonly logicalReleaseDevelopmentRef: string;
  /** Resolver output. `null` means the ref could not be resolved. */
  readonly exactConsumedSha: ExactSha | null;
  readonly contractDigest: ExactSha | null;
  readonly lifecycleProfile?: LifecycleProfileIdentity;
  readonly affectedSurfaces?: readonly DwoSurface[];
  readonly boundAt: string;
}

/** Injected ref resolver, used by callers that own transport. Not a fallback path. */
export type NativeSourceResolver = (ref: string) => ExactSha | null;

function fail(
  code: BindingFailureCode,
  message: string,
  mainFallbackProhibited = true,
): BindingFailure {
  return { ok: false, code, message, mainFallbackProhibited };
}

/**
 * Resolve a NATIVE Universal semantic source binding, failing closed.
 *
 * There is deliberately no parameter through which a caller could supply a
 * compatibility SHA to fall back to. That is the structural enforcement of ADR-11 /
 * AC-RB-02: the fallback is not a runtime branch someone can forget to guard, it is
 * unrepresentable. This function accepts exactly one argument and that argument's
 * only SHA field is the native consumed SHA.
 */
export function resolveNativeBinding(
  resolution: NativeSourceResolution,
): BindingResult<NativeUniversalSourceBinding> {
  if (!resolution.universalRepository) {
    return fail('SOURCE_REF_UNRESOLVABLE', 'universalRepository is required');
  }
  if (!resolution.logicalReleaseDevelopmentRef) {
    return fail('SOURCE_REF_UNRESOLVABLE', 'logicalReleaseDevelopmentRef is required');
  }
  if (resolution.exactConsumedSha === null) {
    return fail(
      'SOURCE_REF_UNRESOLVABLE',
      `Universal release-development ref "${resolution.logicalReleaseDevelopmentRef}" could not be resolved to an exact SHA`,
    );
  }
  if (!isExactSha(resolution.exactConsumedSha)) {
    return fail(
      'SOURCE_SHA_MISSING',
      `exactConsumedSha must be 40 lowercase hex characters, got "${resolution.exactConsumedSha}"`,
    );
  }
  if (resolution.contractDigest === null || !isExactSha(resolution.contractDigest)) {
    return fail(
      'SOURCE_SHA_MISSING',
      'contractDigest must be a 40-hex JCS+SHA-256 digest of the consumed contract',
    );
  }
  const profile = resolution.lifecycleProfile ?? UNIVERSAL_RUN_LIFECYCLE_PROFILE_V1;
  if (profile.id !== 'gwc.universal-run' || profile.version !== 1) {
    return fail(
      'CONTRACT_IDENTITY_UNSUPPORTED',
      `Unsupported lifecycle profile ${profile.id}/${profile.version}; kernel §1.2 requires LIFECYCLE_PROFILE_UNSUPPORTED`,
    );
  }
  return {
    ok: true,
    binding: {
      namespace: 'NATIVE_UNIVERSAL',
      universalRepository: resolution.universalRepository,
      logicalReleaseDevelopmentRef: resolution.logicalReleaseDevelopmentRef,
      exactConsumedSha: resolution.exactConsumedSha,
      lifecycleProfile: profile,
      contractDigest: resolution.contractDigest,
      boundAt: resolution.boundAt,
      affectedSurfaces: resolution.affectedSurfaces ?? [],
    },
  };
}

/**
 * Build a GWC-MAIN compatibility binding.
 *
 * This does NOT accept a logical release-development ref, and its namespace makes it
 * structurally impossible to pass where a native binding is required.
 */
export function resolveCompatibilityBinding(
  resolution: NativeSourceResolution,
): BindingResult<CompatibilitySourceBinding> {
  if (!isExactSha(resolution.exactConsumedSha)) {
    return fail('SOURCE_SHA_MISSING', 'compatibility source requires an exact 40-hex SHA');
  }
  return {
    ok: true,
    binding: {
      namespace: 'GWC_MAIN_COMPATIBILITY',
      universalRepository: resolution.universalRepository,
      ref: resolution.logicalReleaseDevelopmentRef,
      exactSha: resolution.exactConsumedSha,
      role: 'COMPATIBILITY_AND_EFFECT_GOVERNANCE_ONLY',
      boundAt: resolution.boundAt,
    },
  };
}

/**
 * Read a native field off a binding WITHOUT narrowing by assumption.
 *
 * Returns `null` for any compatibility record. This is the runtime companion to the
 * compile-time namespace separation: a legacy/compat source can never populate a
 * native Universal field (AC-821-03).
 */
export function readNativeField(
  binding: SourceBinding,
  field: 'exactConsumedSha' | 'contractDigest' | 'logicalReleaseDevelopmentRef',
): string | null {
  if (binding.namespace !== 'NATIVE_UNIVERSAL') {
    return null;
  }
  return binding[field];
}

/**
 * Capability surface of this module.
 *
 * DWO v2 is a read-only observatory (BRD BR-09, NFR-002, AC-821-04). This registry
 * therefore exposes no write, approve, deny, retry, merge or deploy capability. The
 * type exists so a test can assert the absence rather than trusting a comment.
 */
export interface DwoBindingCapabilities {
  readonly read: true;
  readonly resolve: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly consumeAuthority: false;
  readonly merge: false;
  readonly deploy: false;
}

export const DWO_BINDING_CAPABILITIES: DwoBindingCapabilities = Object.freeze({
  read: true,
  resolve: true,
  write: false,
  approve: false,
  deny: false,
  consumeAuthority: false,
  merge: false,
  deploy: false,
} as const);

/** The release-binding stages. Exact vocabulary from Roadmap §14.1 / C4 §21.2. */
export type BindingStage = 'RELEASE_DEV_TRACKING' | 'MAIN_REBIND_PENDING' | 'RELEASE_MAIN_BOUND';

export const BINDING_STAGES: readonly BindingStage[] = [
  'RELEASE_DEV_TRACKING',
  'MAIN_REBIND_PENDING',
  'RELEASE_MAIN_BOUND',
];

/** Registered DRIFT taxonomy, exact FNR-03 vocabulary. No numeric threshold. */
export type DriftClassification =
  | 'COMPATIBLE'
  | 'ADAPTER_CHANGE'
  | 'REDUCER_CHANGE'
  | 'UI_CHANGE'
  | 'QUALIFICATION_CHANGE'
  | 'BLOCKING_CONTRACT_DRIFT';

export const DRIFT_CLASSIFICATIONS: readonly DriftClassification[] = [
  'COMPATIBLE',
  'ADAPTER_CHANGE',
  'REDUCER_CHANGE',
  'UI_CHANGE',
  'QUALIFICATION_CHANGE',
  'BLOCKING_CONTRACT_DRIFT',
];

export interface SourceBindingState {
  readonly stage: BindingStage;
  readonly native: NativeUniversalSourceBinding | null;
  readonly compatibility: CompatibilitySourceBinding | null;
}
