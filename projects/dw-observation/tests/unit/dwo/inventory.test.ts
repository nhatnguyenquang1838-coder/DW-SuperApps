/**
 * CR-821-C verification suite — capability / compatibility / access-boundary
 * inventories.
 *
 * AC-821-02  every DWO v1 surface inventoried with source_profile + provenance;
 *            stale/legacy classified, not silently retained
 * AC-821-03  compatibility/legacy baseline in a namespace distinct from native
 *            Universal semantics
 * AC-821-04  access-boundary inventory covers browser/server read, write/effect,
 *            RLS policies and Realtime topics
 */
import { describe, expect, it } from 'vitest';
import {
  DWO_SURFACE_CATALOG,
  ACCESS_BOUNDARIES,
  assertCatalogInvariants,
  assertNoEffectBoundary,
  buildDwoInventory,
  countByProfile,
  type AccessBoundaryKind,
} from '@/lib/dwo/inventory';

describe('AC-821-02 · every DWO v1 surface is inventoried with source_profile and provenance', () => {
  it('catalog invariants hold: unique ids, non-empty paths, valid source_profile', () => {
    expect(() => assertCatalogInvariants(DWO_SURFACE_CATALOG)).not.toThrow();
    expect(DWO_SURFACE_CATALOG.length).toBeGreaterThan(10);
  });

  it('every surface carries a provenance (non-empty)', () => {
    for (const s of DWO_SURFACE_CATALOG) {
      expect(s.provenance, `surface ${s.id}`).toBeTruthy();
    }
  });

  it('stale/legacy surfaces are explicitly classified, not silently retained', () => {
    const staleSurfaces = DWO_SURFACE_CATALOG.filter((s) => s.stale === true);
    expect(staleSurfaces.length).toBeGreaterThan(0);
    for (const s of staleSurfaces) {
      expect(s.sourceProfile).toBe('COMPATIBILITY_LEGACY');
    }
  });
});

describe('AC-821-03 · compatibility/legacy baseline lives in a distinct namespace', () => {
  it('classifies every surface into exactly one source_profile namespace', () => {
    const counts = countByProfile(DWO_SURFACE_CATALOG);
    const total = counts.DEV_NATIVE + counts.COMPATIBILITY + counts.COMPATIBILITY_LEGACY;
    expect(total).toBe(DWO_SURFACE_CATALOG.length);
  });

  it('native surfaces are distinct from compatibility surfaces by profile, not by path', () => {
    const nativeIds = DWO_SURFACE_CATALOG.filter((s) => s.sourceProfile === 'DEV_NATIVE').map((s) => s.id);
    const legacyIds = DWO_SURFACE_CATALOG.filter((s) => s.sourceProfile === 'COMPATIBILITY_LEGACY').map((s) => s.id);
    expect(nativeIds).not.toEqual(legacyIds);
    // The type system forbids a legacy surface populating a native field; here we
    // assert the catalog itself never mislabels a documented native durable surface.
    expect(nativeIds).toContain('postgres-event-store');
    expect(nativeIds).toContain('server-historical-read');
    expect(legacyIds).toContain('observatory'); // v1 observatory is legacy, not native
  });

  it('reports the expected profile split (DEV_NATIVE 6 / COMPATIBILITY 1 / LEGACY 12)', () => {
    const counts = countByProfile(DWO_SURFACE_CATALOG);
    expect(counts.DEV_NATIVE).toBe(6);
    expect(counts.COMPATIBILITY).toBe(1);
    expect(counts.COMPATIBILITY_LEGACY).toBe(12);
  });
});

describe('AC-821-04 · access-boundary inventory is complete and fail-closed', () => {
  it('covers browser read, server read, RLS policies and Realtime topics', () => {
    const kinds = new Set(ACCESS_BOUNDARIES.map((b) => b.kind));
    expect(kinds.has('BROWSER_READ')).toBe(true);
    expect(kinds.has('SERVER_READ')).toBe(true);
    expect(kinds.has('RLS_POLICY')).toBe(true);
    expect(kinds.has('REALTIME_TOPIC')).toBe(true);
  });

  it('asserts there is no write/effect boundary, now or after future edits', () => {
    expect(() => assertNoEffectBoundary(ACCESS_BOUNDARIES)).not.toThrow();
    // Fail-closed proof: if anyone ever adds a WRITE_EFFECT boundary, the same
    // assertion must throw.
    expect(() =>
      assertNoEffectBoundary([{ id: 'evil', kind: 'WRITE_EFFECT', description: '' }] as unknown as { kind: AccessBoundaryKind }[]),
    ).toThrow(/effect boundary/i);
  });

  it('buildDwoInventory() returns a frozen read-only capability surface', () => {
    const inventory = buildDwoInventory();
    expect(inventory.capability).toEqual({
      read: true,
      write: false,
      approve: false,
      deny: false,
      merge: false,
      deploy: false,
    });
    expect(Object.isFrozen(inventory.capability)).toBe(true);
  });
});
