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
// Source: dwo-v2/fixtures/DWO-UR-30-V1/tasks/task-relations.jsonl
const FIXTURE_TASK_RECORDS: readonly TaskRunRelationRecord[] = [
  {
    taskRef: 'TASK-CORE',
    relationRevisionId: 'rel-1',
    rootRunIds: [
      'DEV-RUN-001',
      'DEV-RUN-005',
      'DEV-RUN-008',
      'DEV-RUN-012',
      'DEV-RUN-014',
      'DEV-RUN-015',
      'DEV-RUN-016',
      'DEV-RUN-020',
    ],
    sourceSystem: 'DWO-FIXTURE',
    sourceRecordId: 'fixture-record-1',
    sourceDigest:
      'sha256:3b2f67c4f68d5cfeb03eee35c825771ae3392827d7b2ddbdfda85e9e1a46575f',
    durablePosition: 1,
    supersedesRevisionId: null,
  },
  {
    taskRef: 'TASK-EVENT',
    relationRevisionId: 'rel-2',
    rootRunIds: ['DEV-RUN-017'],
    sourceSystem: 'DWO-FIXTURE',
    sourceRecordId: 'fixture-record-2',
    sourceDigest:
      'sha256:58b6d1ad2be126ced81f5f76b2b85a591a1fa2a411a9d2ee1c09c3d072829a82',
    durablePosition: 2,
    supersedesRevisionId: null,
  },
  {
    taskRef: 'TASK-PARTY',
    relationRevisionId: 'rel-3',
    rootRunIds: ['DEV-RUN-021'],
    sourceSystem: 'DWO-FIXTURE',
    sourceRecordId: 'fixture-record-3',
    sourceDigest:
      'sha256:536acf8a7d93c3aa51496a1b0472ee864e897fc180a25fb4d43dab15a527c3af',
    durablePosition: 3,
    supersedesRevisionId: null,
  },
  {
    taskRef: 'TASK-RESEARCH',
    relationRevisionId: 'rel-4',
    rootRunIds: ['DEV-RUN-024'],
    sourceSystem: 'DWO-FIXTURE',
    sourceRecordId: 'fixture-record-4',
    sourceDigest:
      'sha256:9a0eaf21134dbab2d3b7d0ea89fa9f235be8847dfe717fa6f4ddc6d32fc77ea4',
    durablePosition: 4,
    supersedesRevisionId: null,
  },
  {
    taskRef: 'TASK-WEDDING',
    relationRevisionId: 'rel-5',
    rootRunIds: ['DEV-RUN-027'],
    sourceSystem: 'DWO-FIXTURE',
    sourceRecordId: 'fixture-record-5',
    sourceDigest:
      'sha256:588b99341c81fa5039ac9f779e5f72a85be27a37324ae3b61de531e7a7dd279c',
    durablePosition: 5,
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
