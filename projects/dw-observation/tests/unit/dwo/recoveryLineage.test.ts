/**
 * Recovery lineage tests — AC-827-03 + GPT review cycle guard.
 *
 * Lineages are append-only/immutable; a cycle means corrupted history.
 * navigateLineage must FAIL CLOSED by throwing — never return a partial
 * path or [] — for both multi-node cycles (A->B->A) and self-referential
 * parents (parentGeneration pointing at itself).
 */
import { describe, expect, it } from 'vitest';
import {
  appendGeneration,
  navigateLineage,
} from '@/lib/dwo/recoveryLineage';
import type { RecoveryGeneration, RecoveryKind } from '@/lib/dwo/recoveryLineage';

function gen(id: string, parent: string | null, kind: RecoveryKind = 'RETRY'): RecoveryGeneration {
  return Object.freeze({ id, runId: `RUN-${id}`, kind, parentGeneration: parent });
}

describe('recovery lineage — navigation', () => {
  it('navigates from a leaf back to the root, ordered [root ... target]', () => {
    const lineage: RecoveryGeneration[] = [
      gen('GEN-0001', null, 'RESTART'),
      gen('GEN-0002', 'GEN-0001', 'RERUN'),
      gen('GEN-0003', 'GEN-0002', 'SUPERSESSION'),
    ];
    const path = navigateLineage(lineage, 'GEN-0003');
    expect(path.map((g) => g.id)).toEqual(['GEN-0001', 'GEN-0002', 'GEN-0003']);
  });

  it('returns the single node for a root target', () => {
    const lineage: RecoveryGeneration[] = [gen('GEN-0001', null, 'RESTART')];
    const path = navigateLineage(lineage, 'GEN-0001');
    expect(path.map((g) => g.id)).toEqual(['GEN-0001']);
  });

  it('throws when the target is not in the lineage', () => {
    const lineage: RecoveryGeneration[] = [gen('GEN-0001', null)];
    expect(() => navigateLineage(lineage, 'GEN-9999')).toThrow(/not in lineage/);
  });

  it('throws on a broken parent chain (absent parent)', () => {
    const lineage: RecoveryGeneration[] = [gen('GEN-0002', 'GEN-0001')];
    expect(() => navigateLineage(lineage, 'GEN-0002')).toThrow(/broken parent chain/);
  });
});

describe('recovery lineage — cycle guard (fail closed, never hang)', () => {
  it('throws on a multi-node cycle A->B->A instead of looping forever', () => {
    const lineage: RecoveryGeneration[] = [
      gen('GEN-0001', 'GEN-0002'),
      gen('GEN-0002', 'GEN-0001'),
    ];
    // Must throw — never return a partial path, never hang.
    expect(() => navigateLineage(lineage, 'GEN-0001')).toThrow(/cycle detected/);
  });

  it('throws on a self-referential parent (parentGeneration points at itself)', () => {
    const lineage: RecoveryGeneration[] = [gen('GEN-0001', 'GEN-0001')];
    expect(() => navigateLineage(lineage, 'GEN-0001')).toThrow(/cycle detected/);
  });

  it('throws on a 3-node cycle A->B->C->A (visited-set guard mid-walk)', () => {
    const lineage: RecoveryGeneration[] = [
      gen('GEN-0001', 'GEN-0002'),
      gen('GEN-0002', 'GEN-0003'),
      gen('GEN-0003', 'GEN-0001'),
    ];
    // Walk: GEN-0001 -> GEN-0002 -> GEN-0003 -> GEN-0001 (already visited).
    // The visited-set guard must throw — never hang, never return a partial path.
    expect(() => navigateLineage(lineage, 'GEN-0001')).toThrow(/cycle detected/);
  });

  it('does not throw on a diamond (two children, one root — not a cycle)', () => {
    const lineage: RecoveryGeneration[] = [
      gen('GEN-0000', null, 'RESTART'),
      gen('GEN-0001', 'GEN-0000'),
      gen('GEN-0002', 'GEN-0000'),
    ];
    const path = navigateLineage(lineage, 'GEN-0002');
    expect(path.map((g) => g.id)).toEqual(['GEN-0000', 'GEN-0002']);
  });
});

describe('recovery lineage — append', () => {
  it('appends an immutable frozen generation', () => {
    const lineage: RecoveryGeneration[] = [];
    const g = appendGeneration(lineage, { runId: 'RUN-1', kind: 'RETRY', parentGeneration: null });
    expect(lineage).toHaveLength(1);
    expect(g.id).toBe('GEN-0001');
    expect(Object.isFrozen(g)).toBe(true);
  });
});
