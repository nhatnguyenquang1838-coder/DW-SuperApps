import { cookies } from 'next/headers';
import { readDataSourceConfig, type DataSource } from './dataSourceConfig';

export const DATA_SOURCE_COOKIE = 'dwo-data-source';

/** Request-local selection: a browser preference never changes another user's process state. */
export function getRequestDataSource(): DataSource {
  if (process.env.NODE_ENV === 'production') return 'real';
  let selected: string | undefined;
  try {
    selected = cookies().get(DATA_SOURCE_COOKIE)?.value;
  } catch (error) {
    // Direct server-component unit tests run without Next's request store.
    if (process.env.NODE_ENV !== 'test') throw error;
  }
  if (selected !== undefined) return selected === 'fixture' ? 'fixture' : 'real';
  return readDataSourceConfig();
}

export function isLocalFixturePreview(): boolean {
  return getRequestDataSource() === 'fixture';
}
