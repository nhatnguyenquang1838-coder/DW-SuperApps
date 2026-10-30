import { describe, expect, it } from 'vitest';
import { deriveCurrentFixtureSubjectDigest } from '@/lib/dwo/currentFixtureSubject';

const files: Record<string, string> = {
  'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': [
    JSON.stringify({ run_id: 'DEV-RUN-006', ordinal: 4 }),
    JSON.stringify({ run_id: 'DEV-RUN-006', ordinal: 6 }),
  ].join('\n'),
  'dwo-v2/baseline/r0-rebind-evidence.yaml': 'binding_state:\n  native_universal:\n    lifecycle_profile: gwc.universal-run/1\n',
  'dwo-v2/contract/projection-contract-v2.yaml': 'schema_version: 2\n',
  'lib/dwo/reducer.ts': "export const DWO_REDUCER_VERSION = 'dwo.reducer/1';\n",
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

describe('deriveCurrentFixtureSubjectDigest', () => {
  it('binds independently read current source facts, not the receipt', () => {
    const original = derive();
    expect(original).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(derive({ 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': JSON.stringify({ run_id: 'DEV-RUN-006', ordinal: 7 }) })).not.toBe(original);
    expect(derive({ 'dwo-v2/baseline/r0-rebind-evidence.yaml': 'lifecycle_profile: gwc.universal-run/2\n' })).not.toBe(original);
    expect(derive({ 'dwo-v2/contract/projection-contract-v2.yaml': 'schema_version: 3\n' })).not.toBe(original);
    expect(derive({ 'lib/dwo/reducer.ts': "export const DWO_REDUCER_VERSION = 'dwo.reducer/2';\n" })).not.toBe(original);
    expect(derive({}, '2'.repeat(40))).not.toBe(original);
  });

  it('does not manufacture the reducer identity from current source bytes when no version is declared', () => {
    expect(deriveCurrentFixtureSubjectDigest('DEV-RUN-006')).toBeNull();
  });

  it('returns unavailable when current run history, source metadata, or reducer version declaration is missing', () => {
    expect(derive({ 'dwo-v2/fixtures/DWO-UR-30-V1/events/projection-events.jsonl': '' })).toBeNull();
    expect(derive({ 'dwo-v2/baseline/r0-rebind-evidence.yaml': '' })).toBeNull();
    expect(derive({ 'lib/dwo/reducer.ts': 'export function reduceEvent() {}' })).toBeNull();
  });
});
