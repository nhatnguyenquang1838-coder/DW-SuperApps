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

export function parseReceipt(raw: unknown, runId: string): FixtureQualificationReceipt | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (r.run_id !== runId && (r.subject as Record<string, unknown> | undefined)?.dwo_run_id !== runId) return null;
  if (typeof r.receipt_id !== 'string' || !r.receipt_id.startsWith('receipt:')) return null;
  if (r.authority_granted !== false || r.projection_events_mutated !== false) return null;
  const subject = (r.subject as Record<string, unknown> | undefined) ?? {};
  const status: string = typeof r.status === 'string' ? r.status : 'UNKNOWN';
  const subjectDigest: string = typeof r.subject_digest === 'string' ? r.subject_digest : '';
  const receiptId: string = r.receipt_id as string;
  const graphVersion: string = typeof r.graph_version === 'string' ? (r.graph_version as string) : '';
  const sourceRepository: string = typeof subject.source_repository === 'string' ? (subject.source_repository as string) : '';
  const sourceSha: string = typeof subject.source_sha === 'string' ? (subject.source_sha as string) : '';
  const durablePosition: string = typeof subject.durable_position === 'string' ? (subject.durable_position as string) : '';
  const evidenceRefs = Array.isArray(r.evidence_refs)
    ? (r.evidence_refs as unknown[]).filter((x): x is string => typeof x === 'string')
    : [];
  if (!subjectDigest || !receiptId || !graphVersion) return null;
  return {
    runId,
    status,
    subjectDigest,
    receiptId,
    graphVersion,
    sourceRepository,
    sourceSha,
    durablePosition,
    evidenceRefs,
    authorityGranted: false,
    projectionEventsMutated: false,
    reasonCode: status === 'QUALIFIED' ? 'MATCHED_IMMUTABLE_RECEIPT' : 'NO_IMMUTABLE_RECEIPT',
  };
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
  const digest = currentSubjectDigest ?? receipt.subjectDigest;
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