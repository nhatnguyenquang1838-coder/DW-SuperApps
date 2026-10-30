/**
 * Fixture qualification loader — dev / simulation only.
 *
 * Loads the deterministic synthetic qualification receipts from the
 * materialized DWO-UR-30-V1 evidence pack and validates them against the
 * canonical QualificationReceipt contract (dw_observation/qualification_models.py).
 *
 * The loader is read-only: it never writes receipts, never opens a LangGraph
 * checkpointer, and never mutates projection_events. DEV-RUN-020 has no receipt
 * (INCOMPATIBLE, fail closed); every other run has exactly one.
 */

import { createHash } from 'node:crypto';
import {
  parseQualificationProjection,
  unknownQualificationProjection,
  type QualificationProjection,
} from '@/lib/dwo/qualificationProjection';

export const FIXTURE_QUALIFICATION_PATH =
  'dwo-v2/fixtures/DWO-UR-30-V1/evidence/qualification';

export interface FixtureQualificationReceipt {
  readonly runId: string;
  readonly status: string;
  readonly subjectDigest: string;
  readonly receiptId: string;
  readonly graphVersion: string;
  readonly sourceRepository: string;
  readonly sourceSha: string;
  readonly durablePosition: string;
  readonly evidenceRefs: readonly string[];
  readonly authorityGranted: false;
  readonly projectionEventsMutated: false;
  readonly reasonCode: string;
}

let _fs: typeof import('fs') | null = null;
let _path: typeof import('path') | null = null;

function ensureFs(): typeof import('fs') | null {
  if (_fs !== null) return _fs;
  try {
    _fs = require('fs');
    _path = require('path');
  } catch {
    // Client bundle cannot resolve fs — loader is server-only.
  }
  return _fs;
}

function canonicalJson(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('non-finite JSON number');
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (typeof value === 'object') {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(object[key])}`).join(',')}}`;
  }
  throw new Error('unsupported canonical JSON value');
}

function sha256(value: unknown): string {
  return `sha256:${createHash('sha256').update(canonicalJson(value), 'utf8').digest('hex')}`;
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, i) => key === expected[i]);
}

/**
 * Parse and validate a canonical synthetic qualification receipt. In addition
 * to the authority/no-mutation guard, recompute the immutable subject digest,
 * qualification id, receipt digest, and receipt id exactly as
 * dw_observation/qualification_models.py does. Any mismatch fails closed.
 */
export function parseReceipt(raw: unknown, runId: string): FixtureQualificationReceipt | null {
  try {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
    const r = raw as Record<string, unknown>;
    const subject = r.subject;
    if (!subject || typeof subject !== 'object' || Array.isArray(subject)) return null;
    const s = subject as Record<string, unknown>;

    if (r.schema_version !== 'dwo.qualification-receipt/1') return null;
    if (s.schema_version !== 'dwo.qualification-subject/1' || s.dwo_run_id !== runId) return null;
    if (r.run_id !== undefined && r.run_id !== runId) return null;
    if (r.authority_granted !== false || r.projection_events_mutated !== false) return null;

    const subjectKeys = [
      'schema_version', 'dwo_run_id', 'task_ref', 'source_repository', 'source_sha',
      'lifecycle_profile', 'projection_contract_version', 'reducer_version', 'durable_position',
    ];
    if (!hasExactKeys(s, subjectKeys)) return null;
    if (s.task_ref !== null && (typeof s.task_ref !== 'string' || !s.task_ref.trim())) return null;
    for (const field of ['source_repository', 'lifecycle_profile', 'projection_contract_version', 'reducer_version', 'durable_position'] as const) {
      if (typeof s[field] !== 'string' || !s[field].trim() || s[field] !== s[field].trim()) return null;
    }
    if (typeof s.source_sha !== 'string' || !/^[0-9a-f]{40}$/.test(s.source_sha)) return null;
    const sourceRepository = s.source_repository as string;
    if (sourceRepository.split('/').length !== 2 || sourceRepository.split('/').some((part) => !part)) return null;

    const status = r.status;
    if (typeof status !== 'string' || !['QUALIFIED', 'FAILED', 'DRIFTED', 'UNKNOWN'].includes(status)) return null;
    const subjectDigest = r.subject_digest;
    const graphVersion = r.graph_version;
    if (typeof subjectDigest !== 'string' || !/^sha256:[0-9a-f]{64}$/.test(subjectDigest)) return null;
    if (typeof graphVersion !== 'string' || !graphVersion.trim()) return null;
    if (sha256(s) !== subjectDigest) return null;

    const qualificationId = r.qualification_id;
    const expectedQualificationId = `qualification:${sha256({ subject_digest: subjectDigest, graph_version: graphVersion }).slice('sha256:'.length)}`;
    if (qualificationId !== expectedQualificationId) return null;

    if (!Array.isArray(r.checks) || !Array.isArray(r.evidence_refs)) return null;
    const checks: Array<{ check_id: string; status: string; evidence_refs: string[] }> = [];
    for (const rawCheck of r.checks) {
      if (!rawCheck || typeof rawCheck !== 'object' || Array.isArray(rawCheck)) return null;
      const check = rawCheck as Record<string, unknown>;
      if (!hasExactKeys(check, ['check_id', 'status', 'evidence_refs'])) return null;
      if (typeof check.check_id !== 'string' || !check.check_id.trim()) return null;
      if (typeof check.status !== 'string' || !['PASS', 'FAIL', 'DRIFTED', 'UNKNOWN'].includes(check.status)) return null;
      if (!Array.isArray(check.evidence_refs) || check.evidence_refs.some((ref) => typeof ref !== 'string' || !ref.trim())) return null;
      checks.push({
        check_id: check.check_id,
        status: check.status,
        evidence_refs: [...new Set(check.evidence_refs as string[])].sort(),
      });
    }
    checks.sort((a, b) => a.check_id.localeCompare(b.check_id));
    const evidenceRefs = [...new Set((r.evidence_refs as unknown[]).filter((ref): ref is string => typeof ref === 'string' && !!ref.trim()))].sort();
    if ((r.evidence_refs as unknown[]).some((ref) => typeof ref !== 'string' || !ref.trim())) return null;
    if (status === 'QUALIFIED' && (checks.length === 0 || checks.some((check) => check.status !== 'PASS') || evidenceRefs.length === 0)) return null;

    const receiptContent = {
      schema_version: r.schema_version,
      qualification_id: qualificationId,
      subject: s,
      subject_digest: subjectDigest,
      graph_version: graphVersion,
      status,
      checks,
      evidence_refs: evidenceRefs,
      authority_granted: false,
      projection_events_mutated: false,
    };
    const receiptDigest = sha256(receiptContent);
    if (r.receipt_digest !== receiptDigest) return null;
    const receiptId = r.receipt_id;
    if (receiptId !== `receipt:${receiptDigest.slice('sha256:'.length)}`) return null;

    return {
      runId,
      status,
      subjectDigest,
      receiptId,
      graphVersion,
      sourceRepository,
      sourceSha: s.source_sha as string,
      durablePosition: s.durable_position as string,
      evidenceRefs,
      authorityGranted: false,
      projectionEventsMutated: false,
      reasonCode: status === 'QUALIFIED' ? 'MATCHED_IMMUTABLE_RECEIPT' : 'NO_IMMUTABLE_RECEIPT',
    };
  } catch {
    return null;
  }
}

/**
 * Load the fixture qualification receipt for a run.
 *
 * Returns null when no receipt exists (DEV-RUN-020) — the caller must surface
 * INCOMPATIBLE/UNKNOWN, never fabricate a receipt.
 */
export function loadFixtureQualificationReceipt(
  runId: string,
  config: { path?: string; readText?: (path: string) => string } = {},
): FixtureQualificationReceipt | null {
  const fs = ensureFs();
  if (!fs) return null;
  const p = _path!;
  const filePath = config.path ?? p.join(process.cwd(), FIXTURE_QUALIFICATION_PATH, `${runId}-qualification.json`);
  let raw: string;
  try {
    raw = config.readText ? config.readText(filePath) : fs.readFileSync(filePath, 'utf-8');
  } catch {
    return null;
  }
  try {
    return parseReceipt(JSON.parse(raw), runId);
  } catch {
    return null;
  }
}

/**
 * Convert a fixture receipt into the read-only projection shape consumed by
 * RunStatusAxes. A missing receipt yields UNKNOWN — never QUALIFIED.
 */
export function fixtureReceiptToProjection(
  runId: string,
  receipt: FixtureQualificationReceipt | null,
  currentSubjectDigest?: string | null,
): QualificationProjection {
  if (!receipt) {
    return unknownQualificationProjection(runId, runId === 'DEV-RUN-020' ? 'INCOMPATIBLE_SOURCE' : 'NO_IMMUTABLE_RECEIPT');
  }
  if (currentSubjectDigest === undefined || currentSubjectDigest === null) {
    return {
      runId,
      status: 'UNKNOWN',
      subjectDigest: null,
      receiptSubjectDigest: receipt.subjectDigest,
      receiptId: receipt.receiptId,
      graphVersion: receipt.graphVersion,
      sourceRepository: receipt.sourceRepository,
      sourceSha: receipt.sourceSha,
      durablePosition: receipt.durablePosition,
      evidenceRefs: [...receipt.evidenceRefs],
      authorityGranted: false,
      projectionEventsMutated: false,
      reasonCode: 'CURRENT_SUBJECT_UNAVAILABLE',
    };
  }
  const digest = currentSubjectDigest;
  if (digest !== receipt.subjectDigest) {
    // Drift must surface as DRIFTED, not silently UNKNOWN — the projection
    // contract distinguishes "no receipt" (UNKNOWN) from "receipt exists but
    // the current subject no longer matches it" (DRIFTED).
    return {
      runId,
      status: 'DRIFTED',
      subjectDigest: digest,
      receiptSubjectDigest: receipt.subjectDigest,
      receiptId: receipt.receiptId,
      graphVersion: receipt.graphVersion,
      sourceRepository: receipt.sourceRepository,
      sourceSha: receipt.sourceSha,
      durablePosition: receipt.durablePosition,
      evidenceRefs: [...receipt.evidenceRefs],
      authorityGranted: false,
      projectionEventsMutated: false,
      reasonCode: 'SUBJECT_OR_GRAPH_VERSION_DRIFT',
    };
  }
  return parseQualificationProjection({
    schema_version: 'dwo.qualification-projection/1',
    run_id: runId,
    status: receipt.status,
    subject_digest: receipt.subjectDigest,
    current_subject_digest: digest,
    receipt_subject_digest: receipt.subjectDigest,
    receipt_id: receipt.receiptId,
    graph_version: receipt.graphVersion,
    source_repository: receipt.sourceRepository,
    source_sha: receipt.sourceSha,
    durable_position: receipt.durablePosition,
    evidence_refs: [...receipt.evidenceRefs],
    authority_granted: false,
    projection_events_mutated: false,
    reason_code: receipt.reasonCode,
  });
}

/** Fixture qualification grants no effect capability. */
export const FIXTURE_QUALIFICATION_CAPABILITIES = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);