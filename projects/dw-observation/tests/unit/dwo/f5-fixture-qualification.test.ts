/**
 * F5-1 — Fixture qualification receipts.
 *
 * Verifies the materialized DWO-UR-30-V1 evidence/qualification/*.json receipts
 * against the canonical QualificationReceipt contract (dw_observation/qualification_models.py).
 *
 * Coverage:
 *   - exactly 29 receipts (30 runs minus DEV-RUN-020 INCOMPATIBLE)
 *   - DEV-RUN-020 has no receipt (fail closed)
 *   - every receipt round-trips through QualificationReceipt.from_dict
 *   - every receipt grants no authority and mutates no projection_events
 *   - subject_digest, receipt_id, and graph_version are canonical
 *   - DEV-RUN-006 / DEV-RUN-007 / DEV-RUN-009 / DEV-RUN-010 / DEV-RUN-019 /
 *     DEV-RUN-025 / DEV-RUN-026 / DEV-RUN-028 are QUALIFIED
 *   - all other conforming runs are UNKNOWN (never fabricated)
 */

import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  parseReceipt,
  fixtureReceiptToProjection,
  type FixtureQualificationReceipt,
} from '@/lib/dwo/fixtureQualification';
import { unknownQualificationProjection } from '@/lib/dwo/qualificationProjection';

const FIXTURE_DIR = join(
  fileURLToPath(import.meta.url),
  '..', '..', '..', '..', 'dwo-v2', 'fixtures', 'DWO-UR-30-V1',
  'evidence', 'qualification',
);

const QUALIFIED_RUNS = new Set([
  'DEV-RUN-006', 'DEV-RUN-007', 'DEV-RUN-009', 'DEV-RUN-010',
  'DEV-RUN-019', 'DEV-RUN-025', 'DEV-RUN-026', 'DEV-RUN-028',
]);

function readReceipt(runId: string): FixtureQualificationReceipt | null {
  const p = join(FIXTURE_DIR, `${runId}-qualification.json`);
  let raw: string;
  try {
    raw = readFileSync(p, 'utf-8');
  } catch {
    return null;
  }
  return parseReceipt(JSON.parse(raw), runId);
}

describe('F5-1 fixture qualification receipts', () => {
  const files = readdirSync(FIXTURE_DIR).filter((f) => f.endsWith('-qualification.json'));

  it('has exactly 29 receipts (30 runs minus DEV-RUN-020 INCOMPATIBLE)', () => {
    expect(files.length).toBe(29);
  });

  it('DEV-RUN-020 has no receipt (fail closed)', () => {
    expect(readReceipt('DEV-RUN-020')).toBeNull();
  });

  it('every receipt parses through the canonical TS adapter', () => {
    for (let i = 1; i <= 30; i++) {
      const runId = `DEV-RUN-${String(i).padStart(3, '0')}`;
      if (runId === 'DEV-RUN-020') continue;
      const r = readReceipt(runId);
      expect(r, `receipt for ${runId}`).not.toBeNull();
    }
  });

  it('rejects a receipt whose subject changes without recomputing its binding digest', () => {
    const runId = 'DEV-RUN-006';
    const raw = JSON.parse(readFileSync(join(FIXTURE_DIR, `${runId}-qualification.json`), 'utf-8'));
    const tampered = {
      ...raw,
      subject: { ...raw.subject, durable_position: 'projection_ordinal=999' },
    };
    expect(parseReceipt(tampered, runId)).toBeNull();
  });

  it('rejects receipt/qualification ids not bound to canonical receipt content', () => {
    const runId = 'DEV-RUN-006';
    const raw = JSON.parse(readFileSync(join(FIXTURE_DIR, `${runId}-qualification.json`), 'utf-8'));
    expect(parseReceipt({ ...raw, receipt_id: 'receipt:forged' }, runId)).toBeNull();
    expect(parseReceipt({ ...raw, qualification_id: 'qualification:forged' }, runId)).toBeNull();
  });

  it('QUALIFIED receipts require all checks PASS and evidence refs', () => {
    const runId = 'DEV-RUN-006';
    const raw = JSON.parse(readFileSync(join(FIXTURE_DIR, `${runId}-qualification.json`), 'utf-8'));
    const noEvidence = { ...raw, evidence_refs: [] };
    expect(parseReceipt(noEvidence, runId)).toBeNull();
  });

  it('QUALIFIED runs are exactly the expected set', () => {
    for (let i = 1; i <= 30; i++) {
      const runId = `DEV-RUN-${String(i).padStart(3, '0')}`;
      if (runId === 'DEV-RUN-020') continue;
      const r = readReceipt(runId);
      if (QUALIFIED_RUNS.has(runId)) {
        expect(r?.status).toBe('QUALIFIED');
        expect(r?.reasonCode).toBe('MATCHED_IMMUTABLE_RECEIPT');
      } else {
        expect(r?.status).toBe('UNKNOWN');
        expect(r?.reasonCode).toBe('NO_IMMUTABLE_RECEIPT');
      }
    }
  });

  it('every receipt grants no authority and mutates no projection_events', () => {
    for (let i = 1; i <= 30; i++) {
      const runId = `DEV-RUN-${String(i).padStart(3, '0')}`;
      if (runId === 'DEV-RUN-020') continue;
      const r = readReceipt(runId);
      expect(r?.authorityGranted).toBe(false);
      expect(r?.projectionEventsMutated).toBe(false);
    }
  });

  it('every receipt pins a stable subject digest', () => {
    for (let i = 1; i <= 30; i++) {
      const runId = `DEV-RUN-${String(i).padStart(3, '0')}`;
      if (runId === 'DEV-RUN-020') continue;
      const r = readReceipt(runId);
      expect(r?.subjectDigest.length).toBeGreaterThan(0);
      expect(r?.sourceRepository).toBe('nhatnguyenquang1838-coder/DW-SuperApps');
      expect(r?.graphVersion).toBe('dwo.langgraph-qualification/1');
    }
  });

  it('fixtureReceiptToProjection maps QUALIFIED → QUALIFIED and missing → UNKNOWN', () => {
    const q = readReceipt('DEV-RUN-006')!;
    const proj = fixtureReceiptToProjection('DEV-RUN-006', q, q.subjectDigest);
    expect(proj.status).toBe('QUALIFIED');
    expect(proj.authorityGranted).toBe(false);
    expect(proj.projectionEventsMutated).toBe(false);

    const unknown = fixtureReceiptToProjection('DEV-RUN-020', null);
    expect(unknown.status).toBe('UNKNOWN');
    expect(unknown.reasonCode).toBe('INCOMPATIBLE_SOURCE');

    const missing = fixtureReceiptToProjection('DEV-RUN-001', null);
    expect(missing.status).toBe('UNKNOWN');
    expect(missing.reasonCode).toBe('NO_IMMUTABLE_RECEIPT');
  });

  it('missing independent current subject is UNKNOWN, never echoed from the receipt', () => {
    const q = readReceipt('DEV-RUN-006')!;
    const unavailable = fixtureReceiptToProjection('DEV-RUN-006', q);
    expect(unavailable.status).toBe('UNKNOWN');
    expect(unavailable.reasonCode).toBe('CURRENT_SUBJECT_UNAVAILABLE');
    expect(unavailable.subjectDigest).toBeNull();
    expect(unavailable.receiptSubjectDigest).toBe(q.subjectDigest);
  });

  it('subject digest drift is surfaced as DRIFTED, never QUALIFIED', () => {
    const q = readReceipt('DEV-RUN-006')!;
    const drifted = fixtureReceiptToProjection('DEV-RUN-006', q, `sha256:${'f'.repeat(64)}`);
    expect(drifted.status).toBe('DRIFTED');
  });

  it('unknownQualificationProjection is the fail-closed default', () => {
    const u = unknownQualificationProjection('DEV-RUN-020');
    expect(u.status).toBe('UNKNOWN');
    expect(u.authorityGranted).toBe(false);
    expect(u.projectionEventsMutated).toBe(false);
  });
});