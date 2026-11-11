'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { readDashboardProjection } from '@/lib/dashboard/readDashboardProjection';
import Dashboard from '@/components/dwo/Dashboard';
import {
  getDataSource,
  setDataSource,
  type DataSource,
} from '@/lib/dwo/dataSourceConfig';

interface DashboardPageProps {
  searchParams?: { [key: string]: string | string[] | undefined };
}

export default function DashboardPage({
  searchParams,
}: DashboardPageProps) {
  const router = useRouter();
  const [source, setSource] = useState<DataSource>(() =>
    getDataSource()
  );

  const handleSourceChange = (next: DataSource) => {
    setDataSource(next);
    setSource(next);
    router.refresh();
  };

  // Real source — empty records = source unavailable (fail-closed).
  const projection = readDashboardProjection(source, []);

  return (
    <div
      className="min-h-screen"
      style={{
        background: 'var(--dwo-color-bg-canvas)',
        color: 'var(--dwo-color-text-primary)',
        fontFamily:
          'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoo UI", Helvetica, "Apple Color Emoji", Arial, sans-serif',
      }}
    >
      <div className="mx-auto max-w-5xl px-6 py-10">
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            marginBottom: 12,
            flexWrap: 'wrap',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 10px',
              border: `1px solid var(--dwo-color-border-default)`,
              borderRadius: 'var(--dwo-radius-8)',
              background: 'var(--dwo-color-bg-subtle)',
            }}
          >
            <span
              style={{
                fontSize: '11px',
                color: 'var(--dwo-color-text-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              Datasource
            </span>
            <select
              value={source}
              onChange={(e) =>
                handleSourceChange(
                  e.target.value as DataSource
                )
              }
              style={{
                fontSize: '12px',
                color: 'var(--dwo-color-text-primary)',
                background: 'transparent',
                border: 'none',
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              <option value="real">Real</option>
              <option value="fixture">Fixture</option>
            </select>
          </div>
        </div>

        <Dashboard projection={projection} />
      </div>
    </div>
  );
}
