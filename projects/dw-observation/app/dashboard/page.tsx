// Server component: Dashboard and every other route share the request selection.
import Dashboard from '@/components/dwo/Dashboard';
import { readDashboardProjection } from '@/lib/dashboard/readDashboardProjection';
import { getRequestDataSource } from '@/lib/dwo/requestDataSource';

export default async function DashboardPage() {
  const source = getRequestDataSource();
  const projection = source === 'fixture'
    ? (await import('@/lib/dwo/previewDashboard')).readPreviewDashboardProjection()
    : readDashboardProjection(source, []);
  const FixtureWorkShowcase = source === 'fixture'
    ? (await import('@/components/dwo/FixtureWorkShowcase')).default
    : null;
  return (
    <section className="py-6" data-source={source}>
      {source === 'fixture' && <p className="mb-4 text-sm" style={{ color: 'var(--dwo-color-state-amber)' }}>DEV FIXTURE — read-only local preview</p>}
      <Dashboard projection={projection} />
      {FixtureWorkShowcase && <FixtureWorkShowcase />}
    </section>
  );
}
