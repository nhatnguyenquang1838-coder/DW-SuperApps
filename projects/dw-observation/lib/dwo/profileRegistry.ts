/**
 * CR-823-B — DWO source/profile registry.
 *
 * SCRUM-823 / DWO-V2-02, G2 EXECUTE, PLAN-823-R1, child run CR-823-B.
 *
 * The source/profile registry classifies every DWO projection source into a
 * namespace: native Universal, compatibility, or legacy. Unsupported profiles
 * FAIL CLOSED as UNKNOWN/INCOMPATIBLE — they never receive heuristic Universal
 * semantics (AC-823-03).
 *
 * Design decisions:
 *  1. A profile is one of DEV_NATIVE | COMPATIBILITY | COMPATIBILITY_LEGACY |
 *     UNKNOWN. UNKNOWN is the fail-closed bucket for anything not recognized.
 *  2. An unsupported/incompatible profile projects INCOMPATIBLE and receives NO
 *     fabricated G0..G6 lifecycle. This is the DEV-RUN-020 rule generalized.
 *  3. The registry is read-only; it grants no effect capability.
 */

/** Source profile namespace. */
export type SourceProfile =
  | 'DEV_NATIVE'
  | 'COMPATIBILITY'
  | 'COMPATIBILITY_LEGACY'
  | 'UNKNOWN';

/** The fail-closed projection for an unsupported/incompatible profile. */
export interface IncompatibleProjection {
  readonly sourceProfile: 'UNKNOWN';
  readonly syncState: 'UNAVAILABLE';
  readonly semanticQualification: 'INCOMPATIBLE';
  readonly authorityState: 'NOT_REQUIRED';
  readonly anomalyCount: 0;
  /** True: this profile must NOT receive heuristic Universal G0..G6 semantics. */
  readonly failClosed: true;
}

export const INCOMPATIBLE_PROJECTION: IncompatibleProjection = Object.freeze({
  sourceProfile: 'UNKNOWN',
  syncState: 'UNAVAILABLE',
  semanticQualification: 'INCOMPATIBLE',
  authorityState: 'NOT_REQUIRED',
  anomalyCount: 0,
  failClosed: true,
} as const);

/** A registered profile entry. */
export interface ProfileEntry {
  readonly profile: SourceProfile;
  readonly description: string;
  /** True when this profile is a supported Universal semantic source. */
  readonly supportsUniversalSemantics: boolean;
}

/** The canonical profile registry. */
export const PROFILE_REGISTRY: readonly ProfileEntry[] = [
  { profile: 'DEV_NATIVE', description: 'DWO native Universal projection semantics', supportsUniversalSemantics: true },
  { profile: 'COMPATIBILITY', description: 'gwc/main compatibility + effect-governance', supportsUniversalSemantics: true },
  { profile: 'COMPATIBILITY_LEGACY', description: 'v1 legacy surfaces (SCRUM-555/669/login-epic)', supportsUniversalSemantics: false },
  { profile: 'UNKNOWN', description: 'unsupported/unrecognized source — fail closed', supportsUniversalSemantics: false },
];

/**
 * Resolve a source profile to its projection.
 *
 * UNKNOWN (and any unrecognized profile) fails closed as INCOMPATIBLE with no
 * fabricated Universal semantics. Recognized profiles project their own values.
 */
export function resolveProfileProjection(
  profile: string,
): IncompatibleProjection | { sourceProfile: SourceProfile; syncState: string; semanticQualification: string; authorityState: string; anomalyCount: number; failClosed: false } {
  switch (profile) {
    case 'DEV_NATIVE':
      return { sourceProfile: 'DEV_NATIVE', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, failClosed: false };
    case 'COMPATIBILITY':
      return { sourceProfile: 'COMPATIBILITY', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, failClosed: false };
    case 'COMPATIBILITY_LEGACY':
      return { sourceProfile: 'COMPATIBILITY_LEGACY', syncState: 'LIVE', semanticQualification: 'PENDING', authorityState: 'NOT_REQUIRED', anomalyCount: 0, failClosed: false };
    default:
      return INCOMPATIBLE_PROJECTION;
  }
}

/** True when a profile supports Universal semantics (never heuristic for others). */
export function supportsUniversalSemantics(profile: string): boolean {
  const entry = PROFILE_REGISTRY.find((p) => p.profile === profile);
  return entry ? entry.supportsUniversalSemantics : false;
}

/** The registry is read-only; it grants no effect capability. */
export interface RegistryCapabilities {
  readonly read: true;
  readonly write: false;
  readonly approve: false;
  readonly deny: false;
  readonly merge: false;
  readonly deploy: false;
}

export const REGISTRY_CAPABILITIES: RegistryCapabilities = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);
