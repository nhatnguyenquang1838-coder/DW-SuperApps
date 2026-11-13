'use client';

import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { changeDataSource } from '@/app/actions/dataSource';
import type { DataSource } from '@/lib/dwo/dataSourceConfig';

export default function DataSourceSelector({ source, fixtureAllowed }: { source: DataSource; fixtureAllowed: boolean }) {
  const router = useRouter();
  const [refreshing, startTransition] = useTransition();
  const [saving, setSaving] = useState(false);
  const pending = saving || refreshing;
  const [error, setError] = useState('');
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-sm" data-testid="global-data-source">
      <label className="flex items-center gap-2">
        Datasource
        <select aria-label="Datasource" value={source} disabled={pending} onChange={(event) => {
          const next = event.target.value as DataSource;
          setError('');
          setSaving(true);
          void (async () => {
            try {
              await changeDataSource(next);
              // React 18 tracks synchronous transitions, not the preceding async action.
              startTransition(() => router.refresh());
            } catch (cause) {
              setError(cause instanceof Error ? cause.message : 'Could not change datasource');
            } finally {
              setSaving(false);
            }
          })();
        }} className="rounded border px-2 py-1" style={{ background: 'var(--dwo-color-bg-subtle)', borderColor: 'var(--dwo-color-border-default)' }}>
          <option value="real">Real</option>
          {fixtureAllowed && <option value="fixture">Fixture</option>}
        </select>
      </label>
      <span role="status">{pending ? 'Switching datasource…' : source === 'fixture' ? 'DEV FIXTURE · entire application' : 'REAL · entire application'}</span>
      {error && <span role="alert">{error}</span>}
    </div>
  );
}
