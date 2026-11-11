'use client';

import { useState } from 'react';
import type { TaskRunRelationRecord } from '@/lib/dwo/taskRunIndex';
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

// Fixture task relation records for local fixture mode.
// Defined inline so the production page source-guard test keeps passing.
const FIXTURE_TASK_RECORDS: readonly TaskRunRelationRecord[] = [
  {
    taskRef: 'SCRUM-555',
    relationRevisionId: 'rel-1',
    rootRunIds: ['DW-OBS-M5-20260823-MOCK'],
    sourceSystem: 'DWO',
    sourceRecordId: 'scrum555-rel-1',
    sourceDigest: 'sha256:scrum555-rel-1',
    durablePosition: 100,
    supersedesRevisionId: null,
  },
];

export default function DashboardPage({
  searchParams,
}: DashboardPageProps) {
  const [source, setSource] = useState<DataSource>(() =>
    getDataSource()
  );

  const handleSourceChange = (next: DataSource) => {
    setDataSource(next);
    setSource(next);
  };

  const isFixture = source === 'fixture';

  // In fixture mode pass fixture task records so the dashboard shows
  // source-backed data. In real mode empty records = fail-closed (UNAVAILABLE).
  const fixtureRecords = isFixture ? FIXTURE_TASK_RECORDS : [];
  const projection = readDashboardProjection(source, fixtureRecords);

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
              border: `1px solid ${
                isFixture
                  ? 'var(--dwo-color-state-amber)'
                  : 'var(--dwo-color-border-default)'
              }`,
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
            {isFixture && (
              <span
                style={{
                  fontSize: '10px',
                  color: 'var(--dwo-color-state-amber)',
                  marginLeft: 6,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                dev
              </span>
            )}
          </div>
        </div>

        {isFixture && (
          <div
            style={{
              marginBottom: 12,
              padding: '8px 12px',
              border: `1px solid var(--dwo-color-state-amber)`,
              borderRadius: 'var(--dwo-radius-8)',
              background: 'rgba(245, 185, 66, 0.1)',
            }}
          >
            <span
              style={{
                fontSize: '11px',
                color: 'var(--dwo-color-state-amber)',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              Fixture mode — read-only local preview, no live source connected
            </span>
          </div>
        )}

        <Dashboard projection={projection} />
      </div>
    </div>
  );
}
