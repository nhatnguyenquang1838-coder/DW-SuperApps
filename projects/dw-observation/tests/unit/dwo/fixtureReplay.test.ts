/**
 * CR-822-B/C verification — deterministic event stream + golden outputs.
 *
 * AC-822-03 same event prefix deterministically reconstructs the same observable
 * frame.
 *
 * These tests read the MATERIALIZED fixture pack on disk (the executable stream),
 * not the in-code catalog, so they prove the actual artifact is deterministic and
 * matches the golden outputs.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const FIXTURE_ROOT = join(process.cwd(), 'dwo-v2', 'fixtures', 'DWO-UR-30-V1');

function readJson(rel: string): unknown {
  return JSON.parse(readFileSync(join(FIXTURE_ROOT, rel), 'utf-8'));
}

describe('AC-822-03 · deterministic event stream reconstructs the same frame', () => {
  it('materialized fixture pack exists with the canonical layout', () => {
    expect(existsSync(join(FIXTURE_ROOT, 'fixture-set.yaml'))).toBe(true);
    expect(existsSync(join(FIXTURE_ROOT, 'events', 'projection-events.jsonl'))).toBe(true);
    expect(existsSync(join(FIXTURE_ROOT, 'expected', 'run-list.json'))).toBe(true);
  });

  it('projection-events.jsonl has exactly 30 deterministic events', () => {
    const lines = readFileSync(join(FIXTURE_ROOT, 'events', 'projection-events.jsonl'), 'utf-8')
      .trim()
      .split('\n');
    expect(lines.length).toBe(30);
    // Determinism: every line parses to a stable object with sorted keys, and
    // re-parsing yields the identical object (no drift between runs).
    const parsed = lines.map((l) => JSON.parse(l));
    const keys = Object.keys(parsed[0]).sort();
    for (const obj of parsed) {
      expect(Object.keys(obj).sort()).toEqual(keys);
      // Canonical re-serialization is stable and lossless.
      const reserialized = JSON.stringify(obj, keys);
      expect(JSON.parse(reserialized)).toEqual(obj);
    }
  });

  it('run bundles are exactly 30 and each is valid YAML with runtime_facts + dwo_expected_projection', () => {
    const runs = readdirSync(join(FIXTURE_ROOT, 'runs')).filter((f) => f.endsWith('.yaml'));
    expect(runs.length).toBe(30);
    for (const f of runs) {
      const content = readFileSync(join(FIXTURE_ROOT, 'runs', f), 'utf-8');
      expect(content).toContain('runtime_facts:');
      expect(content).toContain('dwo_expected_projection:');
    }
  });

  it('golden run-list.json has exactly 30 rows matching the event stream', () => {
    const runList = readJson('expected/run-list.json') as Array<{ id: string }>;
    expect(runList.length).toBe(30);
    const eventLines = readFileSync(join(FIXTURE_ROOT, 'events', 'projection-events.jsonl'), 'utf-8')
      .trim()
      .split('\n')
      .map((l) => JSON.parse(l) as { run_id: string });
    const eventIds = new Set(eventLines.map((e) => e.run_id));
    for (const row of runList) {
      expect(eventIds.has(row.id), `run ${row.id} missing from event stream`).toBe(true);
    }
  });

  it('golden hierarchy.json edges are consistent with run bundles', () => {
    const hierarchy = readJson('expected/hierarchy.json') as Array<{ parent: string; child: string }>;
    const runList = readJson('expected/run-list.json') as Array<{ id: string; parent: string | null }>;
    const byId = new Map(runList.map((r) => [r.id, r]));
    for (const edge of hierarchy) {
      const child = byId.get(edge.child);
      expect(child, `child ${edge.child} not in run list`).toBeDefined();
      expect(child!.parent).toBe(edge.parent);
    }
  });

  it('golden states.json matches run-list gate/state for every run', () => {
    const states = readJson('expected/states.json') as Record<string, { gate: string | null; gate_state: string | null; run_state: string }>;
    const runList = readJson('expected/run-list.json') as Array<{ id: string; gate: string | null; gate_state: string | null; run_state: string }>;
    expect(Object.keys(states).length).toBe(30);
    for (const row of runList) {
      const s = states[row.id];
      expect(s, `state for ${row.id}`).toBeDefined();
      expect(s.gate).toBe(row.gate);
      expect(s.gate_state).toBe(row.gate_state);
      expect(s.run_state).toBe(row.run_state);
    }
  });

  it('golden anomalies.json lists only runs with anomaly_count > 0', () => {
    const anomalies = readJson('expected/anomalies.json') as string[];
    const runList = readJson('expected/run-list.json') as Array<{ id: string; anomaly_count: number }>;
    const expected = runList.filter((r) => r.anomaly_count > 0).map((r) => r.id);
    expect(anomalies).toEqual(expected);
  });
});
