import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const FIXTURE_ROOT = 'dwo-v2/fixtures/DWO-UR-30-V1';
const BOUND_SOURCE_PATHS = [
  `${FIXTURE_ROOT}/events/projection-events.jsonl`,
  'dwo-v2/baseline/r0-rebind-evidence.yaml',
  'dwo-v2/contract/projection-contract-v2.yaml',
  'lib/dwo/reducer.ts',
  'lib/dwo/currentFixtureSubject.ts',
  'lib/dwo/reducer-identity.json',
] as const;
const REDUCER_IDENTITY_PATH = 'lib/dwo/reducer-identity.json';

export interface CurrentFixtureSubjectOptions {
  readonly repoRoot?: string;
  /** Injection seam for deterministic tests; production reads local Git identity. */
  readonly sourceIdentity?: { readonly repository: string; readonly sha: string };
  readonly readText?: (relativePath: string) => string;
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(object[key])}`).join(',')}}`;
}

function sha256(value: string): string {
  return createHash('sha256').update(value, 'utf8').digest('hex');
}

function repositoryName(remote: string): string | null {
  return remote.trim().match(/(?:github\.com[:/])([^/]+\/[^/]+?)(?:\.git)?$/i)?.[1] ?? null;
}

function localSourceIdentity(repoRoot: string): { repository: string; sha: string; prefix: string } | null {
  try {
    const sha = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repoRoot, encoding: 'utf8' }).trim();
    const remote = execFileSync('git', ['config', '--get', 'remote.origin.url'], { cwd: repoRoot, encoding: 'utf8' }).trim();
    const prefix = execFileSync('git', ['rev-parse', '--show-prefix'], { cwd: repoRoot, encoding: 'utf8' }).trim();
    const repository = repositoryName(remote);
    if (!repository || !/^[0-9a-f]{40}$/.test(sha) || prefix.split('/').some((part) => part === '..')) return null;
    for (const sourcePath of BOUND_SOURCE_PATHS) {
      execFileSync('git', ['ls-files', '--error-unmatch', '--', sourcePath], { cwd: repoRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
    }
    const dirty = execFileSync('git', [
      'status', '--porcelain', '--untracked-files=all', '--', ...BOUND_SOURCE_PATHS,
    ], { cwd: repoRoot, encoding: 'utf8' }).trim();
    return dirty ? null : { repository, sha, prefix };
  } catch {
    return null;
  }
}

function readReducerVersion(readText: (relativePath: string) => string): string | null {
  try {
    const raw = readText(REDUCER_IDENTITY_PATH);
    if ((raw.match(/"schema_version"\s*:/g) ?? []).length !== 1 || (raw.match(/"version"\s*:/g) ?? []).length !== 1) return null;
    const identity = JSON.parse(raw) as Record<string, unknown>;
    if (identity.schema_version !== 'dwo.reducer-identity/1') return null;
    if (typeof identity.version !== 'string' || !/^dwo\.reducer\/[1-9][0-9]*$/.test(identity.version)) return null;
    return identity.version;
  } catch {
    return null;
  }
}

function uniqueCanonicalValue(source: string, key: string, indentation: number, pattern: RegExp): string | null {
  const lines = source.split(/\r?\n/);
  const declarations = lines.flatMap((line, index) => {
    const match = line.match(/^( *)([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*$/);
    return match?.[2] === key ? [{ indentation: match[1].length, value: match[3], index }] : [];
  });
  if (declarations.length !== 1 || declarations[0].indentation !== indentation || !pattern.test(declarations[0].value)) return null;
  return declarations[0].value;
}

function readLifecycleProfile(source: string): string | null {
  const lines = source.split(/\r?\n/);
  const bindingLines = lines.flatMap((line, index) => line === 'binding_state:' ? [index] : []);
  const nativeLines = lines.flatMap((line, index) => line === '  native_universal:' ? [index] : []);
  if (bindingLines.length !== 1 || nativeLines.length !== 1 || nativeLines[0] <= bindingLines[0]) return null;
  const bindingChildren = lines.slice(bindingLines[0] + 1, nativeLines[0]).filter((line) => line.trim() && !/^\s*#/.test(line));
  if (bindingChildren.length !== 0) return null;
  const nativeIndex = nativeLines[0];
  if (lines.filter((line) => /^\s*lifecycle_profile\s*:/.test(line)).length !== 1) return null;
  const profileLines: string[] = [];
  for (const line of lines.slice(nativeIndex + 1)) {
    if (line.trim() && !/^ {4}/.test(line) && !/^\s*#/.test(line)) break;
    if (/^    lifecycle_profile:/.test(line)) profileLines.push(line);
  }
  if (profileLines.length !== 1) return null;
  const profileMatch = profileLines[0].match(/^    lifecycle_profile:\s*([A-Za-z0-9.-]+\/[1-9][0-9]*)\s*$/);
  return profileMatch?.[1] ?? null;
}

function readContractVersion(source: string): string | null {
  return uniqueCanonicalValue(source, 'schema_version', 0, /^[1-9][0-9]*$/);
}

/** Derive the current subject independently from receipt contents. */
export function deriveCurrentFixtureSubjectDigest(
  runId: string,
  options: CurrentFixtureSubjectOptions = {},
): string | null {
  const repoRoot = options.repoRoot ?? process.cwd();
  const injectedReadText = options.readText;
  try {
    const identity = options.sourceIdentity ?? localSourceIdentity(repoRoot);
    if (!identity || !/^[0-9a-f]{40}$/.test(identity.sha) || !/^[^/]+\/[^/]+$/.test(identity.repository)) return null;
    const readText = injectedReadText ?? ((relativePath: string) => {
      const prefix = 'prefix' in identity && typeof identity.prefix === 'string'
        ? identity.prefix
        : '';
      if (prefix.startsWith('/') || prefix.split('/').some((part) => part === '..')) throw new Error('unsafe Git prefix');
      const blobPath = `${prefix}${relativePath}`;
      if (blobPath.split('/').some((part) => part === '..')) throw new Error('unsafe Git blob path');
      return execFileSync('git', ['show', `${identity.sha}:${blobPath}`], { cwd: repoRoot, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 });
    });

    if (!runId.trim()) return null;
    const lines = readText(`${FIXTURE_ROOT}/events/projection-events.jsonl`).split(/\r?\n/).filter((line) => line.trim());
    const eventIds = new Set<string>();
    const ordinals = new Set<number>();
    const targetOrdinals: number[] = [];
    for (const line of lines) {
      const parsed: unknown = JSON.parse(line);
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
      const event = parsed as Record<string, unknown>;
      if (typeof event.event_id !== 'string' || !event.event_id.trim() || typeof event.run_id !== 'string' || !event.run_id.trim()
        || !Number.isSafeInteger(event.ordinal) || (event.ordinal as number) < 0) return null;
      if (eventIds.has(event.event_id) || ordinals.has(event.ordinal as number)) return null;
      eventIds.add(event.event_id);
      ordinals.add(event.ordinal as number);
      if (event.run_id === runId) targetOrdinals.push(event.ordinal as number);
    }
    if (targetOrdinals.length === 0) return null;

    const lifecycle = readLifecycleProfile(readText('dwo-v2/baseline/r0-rebind-evidence.yaml'));
    const contractVersion = readContractVersion(readText('dwo-v2/contract/projection-contract-v2.yaml'));
    const reducerVersion = readReducerVersion(readText);
    if (!lifecycle || !contractVersion || !reducerVersion) return null;

    const subject = {
      schema_version: 'dwo.qualification-subject/1',
      dwo_run_id: runId,
      task_ref: null,
      source_repository: identity.repository,
      source_sha: identity.sha,
      lifecycle_profile: lifecycle,
      projection_contract_version: `dwo.projection-contract/${contractVersion}`,
      reducer_version: reducerVersion,
      durable_position: `projection_ordinal=${Math.max(...targetOrdinals)}`,
    };
    return `sha256:${sha256(canonicalJson(subject))}`;
  } catch {
    return null;
  }
}
