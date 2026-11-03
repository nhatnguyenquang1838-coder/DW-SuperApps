import { NextResponse } from 'next/server';
import { isLocalFixturePreview } from '@/lib/dwo/fixturePreviewMode';
import { readFixtureEvidence } from '@/lib/dwo/fixtureEvidenceRead';

export async function GET(request: Request, context: { params: { runId: string } | Promise<{ runId: string }> }) {
  if (!isLocalFixturePreview()) return NextResponse.json({ ok: false, error: 'Fixture preview unavailable' }, { status: 404 });
  const { runId } = await context.params;
  const rawPath = new URL(request.url).searchParams.get('path') ?? '';
  // URLSearchParams decodes once. Normal encoded slashes are expected from the
  // viewer; traversal and remaining/double encoding are denied by the reader.
  const ref = rawPath;
  const result = readFixtureEvidence(runId, ref);
  return NextResponse.json(result, { status: result.ok ? 200 : result.status, headers: { 'Cache-Control': 'no-store' } });
}
