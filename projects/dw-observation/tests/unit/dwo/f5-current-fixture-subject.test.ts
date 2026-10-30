import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { deriveCurrentFixtureSubjectDigest } from '@/lib/dwo/currentFixtureSubject';
import { DWO_REDUCER_VERSION } from '@/lib/dwo/reducer';
import { fixtureReceiptToProjection, parseReceipt } from '@/lib/dwo/fixtureQualification';

const METADATA_PATH = 'lib/dwo/reducer-identity.json';
const files: Record<string, string> = {
  'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': [
    JSON.stringify({ event_id: 'event-4', run_id: 'DEV-RUN-006', ordinal: 4 }),
    JSON.stringify({ event_id: 'event-6', run_id: 'DEV-RUN-006', ordinal: 6 }),
  ].join('\n'),
  'dwo-v2/baseline/r0-rebind-evidence.yaml': 'binding_state:\n  native_universal:\n    lifecycle_profile: gwc.universal-run/1\n',
  'dwo-v2/contract/projection-contract-v2.yaml': 'schema_version: 2\n',
  [METADATA_PATH]: JSON.stringify({ schema_version: 'dwo.reducer-identity/1', version: 'dwo.reducer/2' }),
};

function derive(overrides: Record<string, string> = {}, sha = '1'.repeat(40)) {
  const source = { ...files, ...overrides };
  return deriveCurrentFixtureSubjectDigest('DEV-RUN-006', {
    repoRoot: 'test-repository',
    sourceIdentity: { repository: 'example/DW-SuperApps', sha },
    readText: (relativePath) => {
      const value = source[relativePath];
      if (value === undefined) throw new Error(`missing ${relativePath}`);
      return value;
    },
  });
}

function git(repo: string, ...args: string[]) {
  return execFileSync('git', args, { cwd: repo, encoding: 'utf8' }).trim();
}

describe('deriveCurrentFixtureSubjectDigest', () => {
  it('binds independently read current source facts, not the receipt', () => {
    const original = derive();
    expect(original).toMatch(/^sha256:[0-9a-f]{64}$/);
    const changedHistory = derive({ 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': JSON.stringify({ event_id: 'event-7', run_id: 'DEV-RUN-006', ordinal: 7 }) });
    expect(changedHistory).not.toBeNull();
    expect(changedHistory).not.toBe(original);
    const changedLifecycle = derive({ 'dwo-v2/baseline/r0-rebind-evidence.yaml': 'binding_state:\n  native_universal:\n    lifecycle_profile: gwc.universal-run/2\n' });
    expect(changedLifecycle).not.toBeNull();
    expect(changedLifecycle).not.toBe(original);
    expect(derive({ 'dwo-v2/contract/projection-contract-v2.yaml': 'schema_version: 3\n' })).not.toBe(original);
    expect(derive({ [METADATA_PATH]: JSON.stringify({ schema_version: 'dwo.reducer-identity/1', version: 'dwo.reducer/3' }) })).not.toBe(original);
    expect(derive({}, '2'.repeat(40))).not.toBe(original);
    expect(DWO_REDUCER_VERSION).toBe('dwo.reducer/2');
  });

  it('fails closed for malformed target rows and duplicate or blank event identities', () => {
    const malformed = JSON.stringify({ event_id: 'bad', run_id: 'DEV-RUN-006', ordinal: '7' });
    const valid = JSON.stringify({ event_id: 'valid', run_id: 'DEV-RUN-006', ordinal: 7 });
    expect(derive({ 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': `${valid}\n${malformed}` })).toBeNull();
    expect(derive({ 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': `${valid}\n${valid}` })).toBeNull();
    expect(derive({ 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': `${valid}\n${JSON.stringify({ event_id: 'other', run_id: 'DEV-RUN-006', ordinal: 7 })}` })).toBeNull();
    expect(derive({ 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': JSON.stringify({ event_id: ' ', run_id: 'DEV-RUN-006', ordinal: 7 }) })).toBeNull();
    expect(derive({ 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': JSON.stringify({ event_id: 'valid', run_id: '', ordinal: 7 }) })).toBeNull();
  });

  it('rejects ambiguous lifecycle and contract version declarations instead of selecting a decoy', () => {
    expect(derive({ 'dwo-v2/baseline/r0-rebind-evidence.yaml': `${files['dwo-v2/baseline/r0-rebind-evidence.yaml']}lifecycle_profile: gwc.decoy/9\n` })).toBeNull();
    expect(derive({ 'dwo-v2/baseline/r0-rebind-evidence.yaml': 'binding_state:\n  native_universal:\n    lifecycle_profile: gwc.universal-run/1\n    lifecycle_profile: gwc.universal-run/2\n' })).toBeNull();
    expect(derive({ 'dwo-v2/contract/projection-contract-v2.yaml': 'schema_version: 2\nschema_version: 9\n' })).toBeNull();
  });

  it('derives a committed clean default source subject and reports the historical receipt as drifted', () => {
    const scratch = process.env.DWO_R3_SCRATCH_ROOT ?? tmpdir();
    const repo = mkdtempSync(join(scratch, 'dwo-r3-subject-'));
    try {
      const root = process.cwd();
      const boundFiles = [
        'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl',
        'dwo-v2/baseline/r0-rebind-evidence.yaml',
        'dwo-v2/contract/projection-contract-v2.yaml',
        'lib/dwo/reducer.ts', 'lib/dwo/currentFixtureSubject.ts', METADATA_PATH,
      ];
      for (const relativePath of boundFiles) {
        const target = join(repo, relativePath);
        mkdirSync(dirname(target), { recursive: true });
        writeFileSync(target, readFileSync(join(root, relativePath)));
      }
      git(repo, 'init');
      git(repo, 'config', '--local', 'user.name', 'DWO R3 test');
      git(repo, 'config', '--local', 'user.email', 'dwo-r3-test@example.invalid');
      git(repo, 'remote', 'add', 'origin', 'https://github.com/example/DW-SuperApps.git');
      git(repo, 'add', '--all');
      git(repo, 'commit', '-m', 'fixture source subject test');

      const digest = deriveCurrentFixtureSubjectDigest('DEV-RUN-006', { repoRoot: repo });
      expect(digest).toMatch(/^sha256:[0-9a-f]{64}$/);
      const eventsPath = 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl';
      writeFileSync(join(repo, eventsPath), JSON.stringify({ event_id: 'tampered', run_id: 'DEV-RUN-006', ordinal: 99 }));
      git(repo, 'update-index', '--assume-unchanged', '--', eventsPath);
      expect(deriveCurrentFixtureSubjectDigest('DEV-RUN-006', { repoRoot: repo })).toBe(digest);
      git(repo, 'update-index', '--no-assume-unchanged', '--', eventsPath);
      git(repo, 'checkout', '--', eventsPath);
      const receiptRaw = JSON.parse(readFileSync(join(root, 'dwo-v2/fixtures/DWO-UR-30-V1/evidence/qualification/DEV-RUN-006-qualification.json'), 'utf8'));
      const receipt = parseReceipt(receiptRaw, 'DEV-RUN-006');
      expect(receipt).not.toBeNull();
      const drifted = fixtureReceiptToProjection('DEV-RUN-006', receipt, digest);
      expect(drifted.status).toBe('DRIFTED');
      expect(drifted.subjectDigest).toBe(digest);
      writeFileSync(join(repo, 'lib/dwo/reducer.ts'), `${readFileSync(join(repo, 'lib/dwo/reducer.ts'), 'utf8')}\n// dirty\n`);
      expect(deriveCurrentFixtureSubjectDigest('DEV-RUN-006', { repoRoot: repo })).toBeNull();
      git(repo, 'checkout', '--', 'lib/dwo/reducer.ts');
      writeFileSync(join(repo, 'lib/dwo/reducer-identity.json'), '{ malformed');
      git(repo, 'add', '--', METADATA_PATH);
      git(repo, 'commit', '-m', 'malformed bound metadata');
      expect(deriveCurrentFixtureSubjectDigest('DEV-RUN-006', { repoRoot: repo })).toBeNull();
      writeFileSync(join(repo, METADATA_PATH), readFileSync(join(root, METADATA_PATH), 'utf8'));
      git(repo, 'add', '--', METADATA_PATH);
      git(repo, 'commit', '-m', 'restore valid metadata');
      git(repo, 'rm', '--cached', '--', METADATA_PATH);
      git(repo, 'commit', '-m', 'leave bound metadata untracked');
      expect(deriveCurrentFixtureSubjectDigest('DEV-RUN-006', { repoRoot: repo })).toBeNull();
    } finally {
      rmSync(repo, { recursive: true, force: true });
    }
  });

  it('returns unavailable when current run history, source metadata, or reducer identity is missing or invalid', () => {
    expect(derive({ 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': '' })).toBeNull();
    expect(derive({ 'dwo-v2/baseline/r0-rebind-evidence.yaml': '' })).toBeNull();
    expect(derive({ [METADATA_PATH]: '{ broken' })).toBeNull();
    expect(derive({ [METADATA_PATH]: JSON.stringify({ schema_version: 'unknown', version: 'dwo.reducer/2' }) })).toBeNull();
  });
});
