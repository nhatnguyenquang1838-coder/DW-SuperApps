/**
 * Fixture scenario adapter — adapts the DWO-UR-30-V1 catalog from
 * lib/dwo/fixtureSpec.ts into the UnifiedRunWorkspaceModel.
 *
 * Pure TypeScript — no React import, no DOM access.
 * Incomplete scenarios are kept explicit — no node fabrication.
 */

import type { UnifiedRunWorkspaceModel } from "../unifiedRuntime";
import { FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";
import { materializeFixtureScenario } from "@/lib/dwo/materializeFixtureScenario";

/**
 * Adapt a single DWO-UR-30-V1 catalog entry into a unified model.
 * For negative fixtures (DEV-RUN-020), the projection is INCOMPATIBLE
 * and no nodes are fabricated — the model is returned with empty nodes
 * and an explicit status.
 */
export function fixtureScenarioAdapter(
  catalogEntry: (typeof FIXTURE_CATALOG)[number],
): UnifiedRunWorkspaceModel {
  // Delegate to the canonical fixture pipeline. A parallel implementation here
  // previously drifted from the materializer (taskRef hard-coded null, gateState
  // dropped, DEPENDENCY edges marked SATISFIED without evidence, empty
  // artifacts) and the UI surfaced that drift as truth.
  return materializeFixtureScenario(catalogEntry);
}
