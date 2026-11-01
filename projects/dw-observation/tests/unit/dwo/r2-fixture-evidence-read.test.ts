import { describe, expect, it } from 'vitest';
import { readFixtureEvidence } from '@/lib/dwo/fixtureEvidenceRead';

describe('R2 fixture evidence reader', () => {
  it('returns actual same-run evidence text for a catalogued reference', () => {
    const result = readFixtureEvidence('DEV-RUN-024', 'execution/DEV-RUN-024-execution.json', { NODE_ENV: 'test', OBSERVATORY_DATA_SOURCE: 'fixture' });
    expect(result).toMatchObject({ ok: true, runId: 'DEV-RUN-024', path: 'execution/DEV-RUN-024-execution.json' });
    if (result.ok) expect(result.text).toContain('"record_id": "DEV-RUN-024-ExecutionReceipt"');
  });
  it.each(['../execution/DEV-RUN-024-execution.json', 'execution/DEV-RUN-025-execution.json', 'execution%2fDEV-RUN-024-execution.json', 'C:/secrets.json'])('rejects unsafe or foreign path %s', (path) => {
    expect(readFixtureEvidence('DEV-RUN-024', path, { NODE_ENV: 'test', OBSERVATORY_DATA_SOURCE: 'fixture' }).ok).toBe(false);
  });
});
