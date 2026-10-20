// Fixture Lab — SERVER entry point.
//
// All scenario materialization happens here, on the server, where the
// DWO-UR-30-V1 evidence pack under dwo-v2/fixtures/ is readable. The client
// shell receives finished models as props; it never touches the filesystem.
//
// Previous behaviour (P5): this route was `"use client"` and called
// materializeFixtureScenario in the browser. Webpack could not resolve `fs`,
// every loader took its `if (!fs) return []` branch, and the Lab rendered an
// empty projection while all 11 Playwright tests still passed. That is
// fail-OPEN, which the fail-closed contract forbids.

import { FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";
import { materializeFixtureScenario } from "@/lib/dwo/materializeFixtureScenario";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

import FixtureLabClient from "./FixtureLabClient";

const DEFAULT_ID = "DEV-RUN-001";

export default function DevFixturesPage() {
  const models: Record<string, UnifiedRunWorkspaceModel> = {};
  const failed: string[] = [];

  for (const entry of FIXTURE_CATALOG) {
    try {
      models[entry.id] = materializeFixtureScenario(entry);
    } catch {
      // Fail closed: an unreadable scenario is reported, never faked. The client
      // renders the UNAVAILABLE notice for any id missing from `models`.
      failed.push(entry.id);
    }
  }

  const defaultId = models[DEFAULT_ID]
    ? DEFAULT_ID
    : (Object.keys(models)[0] ?? DEFAULT_ID);

  return (
    <>
      {failed.length > 0 && (
        <div
          className="dwo-fixture-conflict"
          role="alert"
          data-testid="fixture-pack-degraded"
        >
          DWO-UR-30-V1 materialization UNAVAILABLE for: {failed.join(", ")} —
          fail-closed, no projection shown.
        </div>
      )}
      <FixtureLabClient
        catalog={FIXTURE_CATALOG}
        models={models}
        defaultId={defaultId}
      />
    </>
  );
}