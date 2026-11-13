import { constants, openSync, closeSync, readSync, fstatSync, lstatSync, realpathSync } from 'node:fs';
import { isAbsolute, resolve, sep } from 'node:path';
import { fixturePackForRun } from './fixturePreviewCatalog';

const ALLOWED = /^(execution|target|verification|closure|handoff|authority)\/(DEV-RUN-\d{3}|DEMO-(?:DELIVERY|BLOCKED|RETRY|RECURSIVE)-(?:ROOT|CHILD|API|UI))-(execution|target|verification|closure|handoff|authority)\.json$/;
const MAX_BYTES = 128 * 1024;
export type FixtureEvidenceResult =
  | { ok: true; runId: string; path: string; text: string; bytes: number }
  | { ok: false; status: 400 | 403 | 404 | 413; error: string };

export function readFixtureEvidence(runId: string, ref: string, env: Readonly<Record<string, string | undefined>> = process.env): FixtureEvidenceResult {
  if (env.NODE_ENV === 'production' || env.OBSERVATORY_DATA_SOURCE !== 'fixture') return { ok: false, status: 404, error: 'Fixture preview unavailable' };
  const pack = fixturePackForRun(runId);
  if (!pack) return { ok: false, status: 404, error: 'Unknown fixture run' };
  const ROOT_PARTS = ['dwo-v2', 'fixtures', pack, 'evidence'];
  if (typeof ref !== 'string' || /[%\\\0]/.test(ref) || isAbsolute(ref) || /^[A-Za-z]:/.test(ref) || ref.split('/').some((s) => !s || s === '.' || s === '..')) return { ok: false, status: 400, error: 'Invalid evidence reference' };
  const match = ALLOWED.exec(ref);
  if (!match || match[2] !== runId || match[1] !== match[3]) return { ok: false, status: 403, error: 'Evidence reference is not allowlisted for this run' };
  try {
    const base = resolve(process.cwd(), ...ROOT_PARTS);
    let directory = resolve(process.cwd());
    for (const part of ROOT_PARTS) {
      directory = resolve(directory, part);
      if (lstatSync(directory).isSymbolicLink()) return { ok: false, status: 403, error: 'Fixture directories must not be links' };
    }
    const target = resolve(base, ref);
    if (!target.startsWith(base + sep)) return { ok: false, status: 400, error: 'Path escaped evidence root' };
    const stat = lstatSync(target);
    const folder = resolve(base, match[1]);
    if (lstatSync(folder).isSymbolicLink() || stat.isSymbolicLink() || !stat.isFile()) return { ok: false, status: 403, error: 'Evidence must be a regular file' };
    if (stat.size > MAX_BYTES) return { ok: false, status: 413, error: 'Evidence exceeds size limit' };
    if (!realpathSync(target).startsWith(realpathSync(base) + sep)) return { ok: false, status: 403, error: 'Evidence escaped root' };
    // Bound the read itself, not only a preceding size check.
    const fd = openSync(target, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
    let text: string;
    try {
      if (!fstatSync(fd).isFile()) return { ok: false, status: 403, error: 'Evidence must be a regular file' };
      const buffer = new Uint8Array(MAX_BYTES + 1);
      let bytes = 0;
      while (bytes < buffer.length) {
        const count = readSync(fd, buffer, bytes, buffer.length - bytes, bytes);
        if (!count) break;
        bytes += count;
      }
      if (bytes > MAX_BYTES) return { ok: false, status: 413, error: 'Evidence exceeds size limit' };
      text = Buffer.from(buffer.subarray(0, bytes)).toString('utf8');
    } finally { closeSync(fd); }
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { ok: false, status: 400, error: 'Evidence must be a JSON object' };
    const record = parsed as Record<string, unknown>;
    const bindings = [record.run_id, record.dwo_run_id].filter((value) => value !== undefined);
    if (!bindings.length || bindings.some((value) => value !== runId)) return { ok: false, status: 403, error: 'Evidence does not belong to this run' };
    return { ok: true, runId, path: ref, text, bytes: Buffer.byteLength(text, 'utf8') };
  } catch { return { ok: false, status: 404, error: 'Evidence unavailable' }; }
}
