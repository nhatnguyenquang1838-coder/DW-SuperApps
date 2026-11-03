/**
 * CR-821-D — R0 rebind evidence record schema and DEV_BINDING_ACTIVE derivation.
 *
 * SCRUM-821 / DWO-V2-00, G2 EXECUTE, PLAN-821-R2, child run CR-821-D.
 *
 * Contract sources:
 *   - G1 intake AC-821-05 (recurring R0 rebind evidence record schema defined and
 *     immutable per revision)
 *   - AC-821-08 (exit token DEV_BINDING_ACTIVE derivable from machine-readable state)
 *   - C4 §21.4 source-binding / ADR-11 dual-source runtime binding
 *   - Roadmap WS0 exit token DEV_BINDING_ACTIVE
 *   - Handoff §17: exit tokens must be derived from machine-readable state, not
 *     asserted by intent.
 *
 * Design decisions:
 *  1. A rebind evidence record is IMMUTABLE per revision. Each record pins an exact
 *     previous SHA, an exact new SHA, the lifecycle profile identity, a JCS+SHA-256
 *     content digest of the consumed contract, a drift classification, and the
 *     affected-surface set. Historical revisions are never rewritten.
 *  2. DEV_BINDING_ACTIVE is DERIVED, not stored as a flare field. It holds exactly
 *     when: the active native binding exists AND is fail-closed (exact 40-hex SHA)
 *     AND is NOT in a blocking/drift-requires-replan state. If those inputs are not
 *     all present and coherent, the token is NOT derivable — it fails closed.
 *  3. This module observes and derives. It never writes to any repository, rebinds a
 *     source itself, or grants authority (read-only observatory).
 */

import {
  DRIFT_CLASSIFICATIONS,
  type DriftClassification,
} from './drift';
import {
  isExactSha,
  type ExactSha,
  type NativeUniversalSourceBinding,
} from './releaseBinding';

/** Immutable per-revision R0 rebind evidence record. */
export interface RebindEvidenceRecord {
  readonly schemaId: string;
  readonly schemaVersion: number;
  /** Monotonic, immutable revision number. Never reused, never rewritten in place. */
  readonly revision: number;
  readonly runId: string;
  readonly previousSha: ExactSha | null;
  readonly newSha: ExactSha;
  readonly lifecycleProfileId: string;
  readonly lifecycleProfileVersion: number;
  /** JCS+SHA-256 content digest of the consumed contract at the new SHA. */
  readonly contractDigest: ExactSha;
  readonly driftClassification: DriftClassification;
  /** Surfaces affected by this rebind, for targeted revalidation. */
  readonly affectedSurfaces: readonly string[];
  /** RFC3339 instant the rebind evidence was recorded. */
  readonly recordedAt: string;
  /** Exact provenance of the rebind decision. */
  readonly provenanceRef: string;
}

export const REBIND_RECORD_SCHEMA_ID = 'gwc.dwo.r0-rebind-evidence';
export const REBIND_RECORD_SCHEMA_VERSION = 1;

export interface RebindEvidenceInput {
  readonly previousSha: ExactSha | null;
  readonly newSha: ExactSha;
  readonly lifecycleProfileId: string;
  readonly lifecycleProfileVersion: number;
  readonly contractDigest: ExactSha;
  readonly driftClassification: DriftClassification;
  readonly affectedSurfaces: readonly string[];
  readonly provenanceRef: string;
}

export type RebindRecordResult =
  | { readonly ok: true; readonly record: RebindEvidenceRecord }
  | { readonly ok: false; readonly reason: string };

/**
 * Construct one immutable rebind evidence record revision.
 *
 * Fails closed on any malformed input: exact SHAs must be 40-hex, digest must be
 * 40-hex, the drift classification must be one of the canonical six values, and the
 * lifecycle profile identity must be supported.
 */
export function createRebindRecord(
  runId: string,
  revision: number,
  recordedAt: string,
  input: RebindEvidenceInput,
): RebindRecordResult {
  if (!runId) return { ok: false, reason: 'runId is required' };
  if (!Number.isInteger(revision) || revision < 1) {
    return { ok: false, reason: 'revision must be a positive integer' };
  }
  if (input.previousSha !== null && !isExactSha(input.previousSha)) {
    return { ok: false, reason: `previousSha must be 40-hex or null, got "${input.previousSha}"` };
  }
  if (!isExactSha(input.newSha)) {
    return { ok: false, reason: `newSha must be 40-hex, got "${input.newSha}"` };
  }
  if (!isExactSha(input.contractDigest)) {
    return { ok: false, reason: `contractDigest must be 40-hex, got "${input.contractDigest}"` };
  }
  if (!DRIFT_CLASSIFICATIONS.includes(input.driftClassification)) {
    return { ok: false, reason: `unknown drift classification "${input.driftClassification}"` };
  }
  if (input.lifecycleProfileId !== 'gwc.universal-run' || input.lifecycleProfileVersion !== 1) {
    return {
      ok: false,
      reason: `unsupported lifecycle profile ${input.lifecycleProfileId}/${input.lifecycleProfileVersion}`,
    };
  }
  return {
    ok: true,
    record: {
      schemaId: REBIND_RECORD_SCHEMA_ID,
      schemaVersion: REBIND_RECORD_SCHEMA_VERSION,
      revision,
      runId,
      previousSha: input.previousSha,
      newSha: input.newSha,
      lifecycleProfileId: input.lifecycleProfileId,
      lifecycleProfileVersion: input.lifecycleProfileVersion,
      contractDigest: input.contractDigest,
      driftClassification: input.driftClassification,
      affectedSurfaces: [...input.affectedSurfaces],
      recordedAt,
      provenanceRef: input.provenanceRef,
    },
  };
}

/** Machine-readable inputs from which DEV_BINDING_ACTIVE is derived. */
export interface BindingActiveInput {
  /** The active native Universal source binding, if one has been established. */
  readonly nativeBinding: NativeUniversalSourceBinding | null;
  /** The latest drift classification for the active binding. */
  readonly drift: DriftClassification | null;
}

export interface DevBindingActiveDecision {
  readonly derivable: boolean;
  readonly token: string | null;
  /** Reasons blocking derivation, for fail-closed projection. */
  readonly reasons: readonly string[];
}

/**
 * Derive DEV_BINDING_ACTIVE from machine-readable state (AC-821-08).
 *
 * HOLDS exactly when ALL of:
 *   1. a native Universal binding exists;
 *   2. its exact consumed SHA is a valid 40-hex SHA (binding must have been
 *      constructed fail-closed, so this is normally guaranteed);
 *   3. the binding carries a valid JCS+SHA-256 contract digest;
 *   4. the latest drift classification is NOT one that requires a replan
 *      (COMPATIBLE / ADAPTER_CHANGE / REDUCER_CHANGE / UI_CHANGE /
 *      QUALIFICATION_CHANGE hold; BLOCKING_CONTRACT_DRIFT does not).
 *
 * Any missing or incoherent input makes the token NON-derivable — it fails closed.
 */
export function deriveDevBindingActive(input: BindingActiveInput): DevBindingActiveDecision {
  const reasons: string[] = [];
  if (input.nativeBinding === null) {
    reasons.push('no active native Universal binding established');
  } else {
    if (input.nativeBinding.namespace !== 'NATIVE_UNIVERSAL') {
      reasons.push('active binding is not a native Universal binding');
    }
    if (!isExactSha(input.nativeBinding.exactConsumedSha)) {
      reasons.push('native binding lacks a valid exact consumed SHA');
    }
    if (!isExactSha(input.nativeBinding.contractDigest)) {
      reasons.push('native binding lacks a valid contract digest');
    }
  }
  if (input.drift === null) {
    reasons.push('no drift classification provided for the active binding');
  } else if (!DRIFT_CLASSIFICATIONS.includes(input.drift)) {
    reasons.push(`unknown drift classification "${input.drift}"`);
  } else if (input.drift === 'BLOCKING_CONTRACT_DRIFT') {
    reasons.push('drift classification is BLOCKING_CONTRACT_DRIFT — replan required');
  }

  if (reasons.length === 0) {
    return { derivable: true, token: 'DEV_BINDING_ACTIVE', reasons: [] };
  }
  return { derivable: false, token: null, reasons };
}

/** Exit-token registry so downstream packages read one canonical name. */
export const EXIT_TOKENS = Object.freeze({
  devBindingActive: 'DEV_BINDING_ACTIVE',
} as const);
