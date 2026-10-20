// Server Component — Run Replay redirect (compatibility deep-link only).
//
// Legacy /runs/[runId]/replay redirects to the canonical route:
//   /runs/[runId]?mode=replay&seq=<resolved durableSequence>
// It must not render a second UI — the main run page renders
// UnifiedRunWorkspace for both LIVE and REPLAY modes.

import { redirect } from "next/navigation";
import { readHistoricalEvents } from "@/lib/serverHistoricalRead";
import { buildReplayRoute } from "@/lib/dwo/replayRoute";

export default async function RunReplayRedirect({
  params,
}: {
  params: { runId: string };
}) {
  const result = await readHistoricalEvents(params.runId);

  // No canonical history → redirect to LIVE; main page handles UNKNOWN/UNAVAILABLE.
  if (result.degraded || result.events.length === 0) {
    redirect(`/runs/${encodeURIComponent(params.runId)}?mode=live`);
  }

  const sequences = result.events
    .map((e) => (typeof e.sequence === "number" ? e.sequence : -1))
    .filter((s) => s >= 0);

  const maxSequence =
    sequences.length > 0 ? Math.max(...sequences) : 0;

  // Redirect to the canonical replay route (same-shell UnifiedRunWorkspace).
  redirect(buildReplayRoute(params.runId, maxSequence));
}
