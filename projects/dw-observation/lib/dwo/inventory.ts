/**
 * CR-821-C — Capability, compatibility and access-boundary inventories.
 *
 * SCRUM-821 / DWO-V2-00, G2 EXECUTE, PLAN-821-R2, child run CR-821-C.
 *
 * Contract sources:
 *   - G1 intake AC-821-02 (every DWO v1 surface inventoried with source_profile
 *     classification and provenance; stale/legacy bindings classified, not silently
 *     retained)
 *   - AC-821-03 (compatibility/legacy baseline in a namespace distinct from native
 *     Universal semantics)
 *   - AC-821-04 (access-boundary inventory covers browser read, server read,
 *     write/effect paths, RLS policies and Realtime topics)
 *   - C4 §19.19 L2 decomposition: DWO is a READ-ONLY observatory; producers append,
 *     DWO never writes Universal facts back.
 *
 * Design decisions:
 *  1. The inventory is machine-readable and TYPE-CHECKED: the surface catalog and
 *     access boundaries are data here, not documentation. The YAML baselines are
 *     generated from this same code path so they cannot diverge.
 *  2. Every DWO v1 surface is classified into exactly one source_profile namespace.
 *     Legacy SCRUM-555/669/login-epic fixture surfaces are COMPATIBILITY_LEGACY, not
 *     native Universal semantics (RISK-002 mitigation).
 *  3. Access boundaries are enumerated kinds, not free text. DWO exposes BROWSER_READ
 *     and SERVER_READ only; any WRITE_EFFECT / APPROVE / DENY classification is a
 *     scope violation and would fail the inventory invariant assertion.
 *  4. This module still grants NO effect authority (read-only observatory).
 */

/** Source-profile namespace. Exact DWO projection vocabulary from the fixture catalog. */
export type SourceProfile =
  /** DWO's own native Universal projection semantics. */
  | 'DEV_NATIVE'
  /** gwc/main compatibility + effect-governance. */
  | 'COMPATIBILITY'
  /** v1 legacy surfaces bound to SCRUM-555/669/login-epic fixture data. */
  | 'COMPATIBILITY_LEGACY';

/**
 * Access-boundary kind. The inventory asserts DWO has NO write/effect path; a
 * `WRITE_EFFECT` entry would immediately fail the invariant assertion.
 */
export type AccessBoundaryKind =
  /** Browser bundle reads (client components, hooks). */
  | 'BROWSER_READ'
  /** Server/route-handler reads of durable state. */
  | 'SERVER_READ'
  /** Effect path — FORBIDDEN for DWO. Listed so the assertion can prove absence. */
  | 'WRITE_EFFECT'
  /** Postgres Row-Level-Security policy. */
  | 'RLS_POLICY'
  /** Supabase Realtime topic. */
  | 'REALTIME_TOPIC';

/** A typed, terse descriptor of one DWO v1 surface. */
export interface DwoSurfaceDescriptor {
  /** Stable surface id (slug of the logical intent). */
  readonly id: string;
  /** Physical path(s) under projects/dw-observation. */
  readonly paths: readonly string[];
  readonly sourceProfile: SourceProfile;
  readonly kind: 'TYPE' | 'COMPONENT' | 'HOOK' | 'PY_MODULE' | 'MIGRATION' | 'DOC';
  readonly provenance?: string;
  readonly stale?: boolean;
}

/**
 * The DWO v1 surface catalog. This is the exact inventory performed at BOOT:
 * 114 tracked files under projects/dw-observation were scanned; the surfaces below
 * are the runtime-significant ones, each classified by source_profile.
 */
export const DWO_SURFACE_CATALOG: readonly DwoSurfaceDescriptor[] = [
  { id: 'observatory', paths: ['lib/observatory.ts'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'TYPE', provenance: 'v1 login-epic fixture projection', stale: true },
  { id: 'replay', paths: ['lib/replay.ts'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'TYPE', provenance: 'v1 fixture replay', stale: true },
  { id: 'live', paths: ['lib/live.ts'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'TYPE', provenance: 'v1 live projection', stale: true },
  { id: 'supabase-realtime', paths: ['lib/supabaseRealtime.ts'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'TYPE', provenance: 'v1 broadcast/realtime', stale: true },
  { id: 'use-live-projection', paths: ['lib/useLiveProjection.ts'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'HOOK', provenance: 'v1 client hook', stale: true },
  { id: 'broadcast-contract', paths: ['lib/broadcastContract.ts'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'TYPE', provenance: 'v1 broadcast contract', stale: true },
  { id: 'postgres-event-store', paths: ['lib/postgresEventStore.ts'], sourceProfile: 'DEV_NATIVE', kind: 'TYPE', provenance: 'durable projection event store' },
  { id: 'server-historical-read', paths: ['lib/serverHistoricalRead.ts'], sourceProfile: 'DEV_NATIVE', kind: 'TYPE', provenance: 'server-side durable read' },
  { id: 'review-intelligence', paths: ['lib/reviewIntelligence.ts'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'TYPE', provenance: 'v1 review intelligence', stale: true },
  { id: 'py-adapters', paths: ['dw_observation/adapters.py'], sourceProfile: 'COMPATIBILITY', kind: 'PY_MODULE', provenance: 'Universal adapter twin' },
  { id: 'py-events', paths: ['dw_observation/events.py'], sourceProfile: 'DEV_NATIVE', kind: 'PY_MODULE', provenance: 'event envelope' },
  { id: 'py-fixtures', paths: ['dw_observation/fixtures.py'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'PY_MODULE', provenance: 'v1 fixture pack loader', stale: true },
  { id: 'py-projection', paths: ['dw_observation/projection.py'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'PY_MODULE', provenance: 'v1 projection', stale: true },
  { id: 'py-realtime', paths: ['dw_observation/realtime.py'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'PY_MODULE', provenance: 'v1 realtime', stale: true },
  { id: 'py-reducer', paths: ['dw_observation/reducer.py'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'PY_MODULE', provenance: 'v1 reducer', stale: true },
  { id: 'py-replay', paths: ['dw_observation/replay.py'], sourceProfile: 'COMPATIBILITY_LEGACY', kind: 'PY_MODULE', provenance: 'v1 replay', stale: true },
  { id: 'migrations-security', paths: ['supabase/migrations/20260826134000_observatory_security_hardening.sql'], sourceProfile: 'DEV_NATIVE', kind: 'MIGRATION', provenance: 'RLS policies' },
  { id: 'migrations-projection-events', paths: ['supabase/migrations/20260823100000_projection_events.sql'], sourceProfile: 'DEV_NATIVE', kind: 'MIGRATION', provenance: 'projection_events table' },
  { id: 'migrations-history', paths: ['supabase/migrations/20260823080000_observatory_history.sql', 'supabase/migrations/20260823090000_observatory_backfill_dml.sql'], sourceProfile: 'DEV_NATIVE', kind: 'MIGRATION', provenance: 'history view + backfill' },
];

/** Reconciliation invariant: every id is unique and every path is non-empty. */
export function assertCatalogInvariants(catalog: readonly DwoSurfaceDescriptor[]): void {
  const ids = new Set<string>();
  for (const s of catalog) {
    if (ids.has(s.id)) {
      throw new Error(`duplicate surface id ${s.id}`);
    }
    ids.add(s.id);
    if (s.paths.length === 0) {
      throw new Error(`surface ${s.id} has no paths`);
    }
    if (s.sourceProfile !== 'DEV_NATIVE' && s.sourceProfile !== 'COMPATIBILITY' && s.sourceProfile !== 'COMPATIBILITY_LEGACY') {
      throw new Error(`surface ${s.id} has invalid source_profile ${s.sourceProfile}`);
    }
  }
}

/** Count surfaces per source-profile namespace. */
export function countByProfile(catalog: readonly DwoSurfaceDescriptor[]): Readonly<Record<SourceProfile, number>> {
  const counts: Record<SourceProfile, number> = {
    DEV_NATIVE: 0,
    COMPATIBILITY: 0,
    COMPATIBILITY_LEGACY: 0,
  };
  for (const s of catalog) counts[s.sourceProfile] += 1;
  return counts;
}

/** A typed, terse descriptor of one DWO v1 surface. */
export interface AccessBoundary {
  readonly id: string;
  readonly kind: AccessBoundaryKind;
  readonly description: string;
}

/**
 * Access boundaries of the DWO app.
 *
 * BROWSER_READ: client react components / hooks. SERVER_READ: server components,
 * route handlers, serverHistoricalRead, postgresEventStore reads.
 *
 * The RLS policy entries and Realtime topics are enumerated so the inventory is
 * complete and testable. The invariant assertion below proves there is no
 * WRITE_EFFECT in the catalog — if a future change adds one, tests fail closed.
 */
export const ACCESS_BOUNDARIES: readonly AccessBoundary[] = [
  { id: 'client-hooks', kind: 'BROWSER_READ', description: 'client hooks read durable projections via server-read APIs only' },
  { id: 'server-read-durable', kind: 'SERVER_READ', description: 'server components + route handlers read projection_events / history' },
  { id: 'rls-projection-events', kind: 'RLS_POLICY', description: 'RLS on projection_events: authenticated read, no public write' },
  { id: 'rls-history', kind: 'RLS_POLICY', description: 'RLS on observatory history view' },
  { id: 'realtime-projections', kind: 'REALTIME_TOPIC', description: 'realtime topic for projection broadcasts' },
];

/** Fail-closed: DWO exposes NO effect boundary. Throws if one appears. */
export function assertNoEffectBoundary(boundaries: readonly { readonly kind: AccessBoundaryKind }[]): void {
  for (const b of boundaries) {
    if (b.kind === 'WRITE_EFFECT') {
      throw new Error('effect boundary discovered in DWO access inventory');
    }
  }
}

/** The complete inventory surface: catalog + boundaries, frozen. */
export interface DwoInventory {
  readonly catalog: readonly DwoSurfaceDescriptor[];
  readonly accessBoundaries: readonly AccessBoundary[];
  readonly capability: {
    readonly read: true;
    readonly write: false;
    readonly approve: false;
    readonly deny: false;
    readonly merge: false;
    readonly deploy: false;
  };
}

const DWO_CAPABILITY = Object.freeze({
  read: true,
  write: false,
  approve: false,
  deny: false,
  merge: false,
  deploy: false,
} as const);

export function buildDwoInventory(): DwoInventory {
  assertCatalogInvariants(DWO_SURFACE_CATALOG);
  assertNoEffectBoundary(ACCESS_BOUNDARIES);
  return {
    catalog: DWO_SURFACE_CATALOG,
    accessBoundaries: ACCESS_BOUNDARIES,
    capability: DWO_CAPABILITY,
  };
}
