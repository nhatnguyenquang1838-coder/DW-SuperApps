/** Build a replay URL without allowing a run ID to escape its path segment. */
export function buildReplayRoute(runId: string, sequence: number): string {
  return `/runs/${encodeURIComponent(runId)}?mode=replay&seq=${sequence}`;
}
