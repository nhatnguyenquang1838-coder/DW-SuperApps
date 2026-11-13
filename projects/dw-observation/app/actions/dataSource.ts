'use server';

import { cookies } from 'next/headers';
import { DATA_SOURCE_COOKIE } from '@/lib/dwo/requestDataSource';
import type { DataSource } from '@/lib/dwo/dataSourceConfig';

/** Next server actions enforce same-origin POSTs. Only a non-secret UI preference is stored. */
export async function changeDataSource(source: DataSource): Promise<void> {
  if (source !== 'real' && source !== 'fixture') throw new Error('Invalid datasource');
  if (source === 'fixture' && process.env.NODE_ENV === 'production') {
    throw new Error('Fixture mode is disabled in production');
  }
  cookies().set(DATA_SOURCE_COOKIE, source, {
    path: '/', httpOnly: true, sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production', maxAge: 60 * 60 * 24 * 30,
  });
}
