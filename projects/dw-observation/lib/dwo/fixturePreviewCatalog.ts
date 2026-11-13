// Additive preview registry. The canonical 30-run contract remains unchanged.
import { FIXTURE_CATALOG } from './fixtureSpec';
import workCatalog from '@/dwo-v2/fixtures/DWO-WORK-DEMO-V1/catalog.json';

export const WORK_DEMO_PACK = 'DWO-WORK-DEMO-V1';
export const WORK_DEMO_CATALOG: typeof FIXTURE_CATALOG = workCatalog;
export const PREVIEW_FIXTURE_CATALOG: typeof FIXTURE_CATALOG = [
  ...FIXTURE_CATALOG, ...WORK_DEMO_CATALOG,
];

/** Explicit membership, never a request-controlled directory or inferred id. */
export function fixturePackForRun(runId: string): string | null {
  if (FIXTURE_CATALOG.some(row => row.id === runId)) return 'DWO-UR-30-V1';
  if (WORK_DEMO_CATALOG.some(row => row.id === runId)) return WORK_DEMO_PACK;
  return null;
}

export function catalogForFixtureRun(runId: string): typeof FIXTURE_CATALOG {
  return fixturePackForRun(runId) === WORK_DEMO_PACK ? WORK_DEMO_CATALOG : FIXTURE_CATALOG;
}
