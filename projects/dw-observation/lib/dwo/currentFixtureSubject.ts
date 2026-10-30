import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';

const FIXTURE_ROOT = 'dwo-v2/fixtures/DWO-UR-30-V1';

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

function localSourceIdentity(repoRoot: string): { repository: string; sha: string } | null {
  try {
    const sha = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repoRoot, encoding: 'utf8' }).trim();
    const remote = execFileSync('git', ['config', '--get', 'remote.origin.url'], { cwd: repoRoot, encoding: 'utf8' }).trim();
    const repository = repositoryName(remote);
    if (!repository || !/^[0-9a-f]{40}$/.test(sha)) return null;
    const dirty = execFileSync('git', ['status', '--porcelain', '--untracked-files=no', '--', `${FIXTURE_ROOT}/events/projection-events.jsonl`, 'dwo-v2/baseline/r0-rebind-evidence.yaml', 'dwo-v2/contract/projection-contract-v2.yaml', 'lib/dwo/reducer.ts', 'lib/dwo/currentFixtureSubject.ts'], { cwd: repoRoot, encoding: 'utf8' }).trim();
    return dirty ? null : { repository, sha };
  } catch {
    return null;
  }
}

/** Derive the current subject independently from receipt contents. */
export function deriveCurrentFixtureSubjectDigest(
  runId: string,
  options: CurrentFixtureSubjectOptions = {},
): string | null {
  const repoRoot = options.repoRoot ?? process.cwd();
  const readText = options.readText ?? ((relativePath: string) => fs.readFileSync(path.join(repoRoot, relativePath), 'utf8'));
  try {
    const identity = options.sourceIdentity ?? localSourceIdentity(repoRoot);
    if (!identity || !/^[0-9a-f]{40}$/.test(identity.sha) || !/^[^/]+\/[^/]+$/.test(identity.repository)) return null;

    const lines = readText(`${FIXTURE_ROOT}/events/projection-events.jsonl`).split(/\r?\n/).filter((line) => line.trim());
    const ordinals = lines
      .map((line) => JSON.parse(line) as Record<string, unknown>)
      .filter((event) => event.run_id === runId && Number.isSafeInteger(event.ordinal) && (event.ordinal as number) >= 0)
      .map((event) => event.ordinal as number);
    if (ordinals.length === 0) return null;

    const lifecycleSource = readText('dwo-v2/baseline/r0-rebind-evidence.yaml');
    const lifecycle = lifecycleSource.split('lifecycle_profile:').at(-1)?.trim().split(/\s/)[0];
    const contractSource = readText('dwo-v2/contract/projection-contract-v2.yaml');
    const contractVersion = contractSource.match(/^schema_version:\s*(\d+)\s*$/m)?.[1];
    const reducerSource = readText('lib/dwo/reducer.ts');
    const versionDeclaration = reducerSource.split('export const DWO_REDUCER_VERSION = ')[1];
    const declaredVersion = versionDeclaration?.split(';')[0]?.trim();
    const quote = declaredVersion?.[0];
    const reducerVersion = quote && (quote === "'" || quote === '"') && declaredVersion?.endsWith(quote)
      ? declaredVersion.slice(1, -1)
      : null;
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
      durable_position: `projection_ordinal=${Math.max(...ordinals)}`,
    };
    return `sha256:${sha256(canonicalJson(subject))}`;
  } catch {
    return null;
  }
}
