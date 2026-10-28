/**
 * F1 — Fixture gate-state + Task-context materialization.
 *
 * Closes two gaps found while validating the F1 acceptance criteria against the
 * materialized DWO-UR-30-V1 pack:
 *
 *  1. `buildRuntimeNode` dropped the catalog's `gateState`, so the preview could
 *     not show e.g. "G5 WAITING" for DEV-RUN-022. The node now carries it.
 *  2. `UnifiedRunWorkspaceModel.taskRef` was hard-coded `null`, so the workspace
 *     had no Task context. It is now derived from the materialized
 *     TaskRunIndexV2 records (tasks/task-relations.jsonl), fail-closed.
 *
 * Both guarantees are additive: no fabricated value ever replaces a missing one.
 */

import { describe, it, expect } from "vitest";
import {
  materializeFixtureScenario,
  materializeAllFixtures,
} from "@/lib/dwo/materializeFixtureScenario";
import { FIXTURE_CATALOG, DEV_RUN_020 } from "@/lib/dwo/fixtureSpec";

const byId = (id: string) =>
  materializeFixtureScenario(FIXTURE_CATALOG.find((c) => c.id === id)!);

// ---------------------------------------------------------------------------
// 1. gateState is carried through from the catalog
// ---------------------------------------------------------------------------

describe("F1-1: gateState is materialized (not dropped)", () => {
  it("DEV-RUN-022 keeps G5 WAITING", () => {
    const model = byId("DEV-RUN-022");
    const self = model.nodes.find((n) => n.id === "DEV-RUN-022");
    expect(self, "self node for DEV-RUN-022").toBeDefined();
    expect(self!.gateId).toBe("G5");
    expect(self!.gateState).toBe("WAITING");
  });

  it("every conforming node's gateId/gateState matches the catalog exactly", () => {
    const models = materializeAllFixtures();
    for (const m of models) {
      if (m.runId === DEV_RUN_020) continue;
      for (const node of m.nodes) {
        const entry = FIXTURE_CATALOG.find((c) => c.id === node.id);
        expect(entry, `catalog entry for ${node.id}`).toBeDefined();
        expect(node.gateId, `${node.id} gateId`).toBe(entry!.gate ?? null);
        expect(node.gateState, `${node.id} gateState`).toBe(entry!.gateState ?? null);
      }
    }
  });

  it("carries every distinct gate state present in the catalog", () => {
    const models = materializeAllFixtures();
    const seen = new Set<string>();
    for (const m of models) {
      if (m.runId === DEV_RUN_020) continue;
      for (const n of m.nodes) {
        if (n.gateState) seen.add(n.gateState);
      }
    }
    // The catalog declares these; a dropped field would shrink the set.
    for (const s of ["ACTIVE", "WAITING", "BLOCKED", "FAILED", "PASSED"]) {
      expect(seen.has(s), `gate state ${s} should be materialized`).toBe(true);
    }
  });

  it("DEV-RUN-022's WAITING is not upgraded to a terminal state", () => {
    const model = byId("DEV-RUN-022");
    const self = model.nodes.find((n) => n.id === "DEV-RUN-022")!;
    expect(self.gateState).toBe("WAITING");
    expect(self.gateState).not.toBe("PASSED");
    expect(self.gateState).not.toBe("ACTIVE");
    // Run lifecycle state stays OPEN — WAITING is a gate state, not closure.
    expect(model.status).toBe("OPEN");
  });

  it("negative fixture still has no nodes and therefore no gateState", () => {
    const model = byId(DEV_RUN_020);
    expect(model.nodes).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// 2. taskRef is derived from the materialized relation records
// ---------------------------------------------------------------------------

// Expected mapping, read from tasks/task-relations.jsonl (durablePosition 1..5).
const EXPECTED: Record<string, string> = {
  "DEV-RUN-001": "TASK-CORE",
  "DEV-RUN-005": "TASK-CORE",
  "DEV-RUN-008": "TASK-CORE",
  "DEV-RUN-012": "TASK-CORE",
  "DEV-RUN-014": "TASK-CORE",
  "DEV-RUN-015": "TASK-CORE",
  "DEV-RUN-016": "TASK-CORE",
  "DEV-RUN-020": "TASK-CORE",
  "DEV-RUN-017": "TASK-EVENT",
  "DEV-RUN-021": "TASK-PARTY",
  "DEV-RUN-024": "TASK-RESEARCH",
  "DEV-RUN-027": "TASK-WEDDING",
};

describe("F1-2: taskRef comes from TaskRunIndexV2 relation records", () => {
  it("root runs claimed by a relation record get that taskRef", () => {
    for (const [runId, taskRef] of Object.entries(EXPECTED)) {
      const model = byId(runId);
      expect(model.taskRef, `${runId} taskRef`).toBe(taskRef);
    }
  });

  it("child runs are not silently attached to their root's task", () => {
    // DEV-RUN-002 is a child of DEV-RUN-001 (which is TASK-CORE), but no
    // relation record claims DEV-RUN-002 itself — so taskRef must stay null
    // rather than being inferred from the hierarchy.
    const child = byId("DEV-RUN-002");
    expect(child.taskRef).toBeNull();
  });

  it("unclaimed runs stay null — no task id is ever inferred", () => {
    for (const m of materializeAllFixtures()) {
      if (Object.prototype.hasOwnProperty.call(EXPECTED, m.runId)) continue;
      expect(m.taskRef, `${m.runId} must not be claimed`).toBeNull();
    }
  });

  it("exactly the claimed runs carry a taskRef", () => {
    const claimed = materializeAllFixtures()
      .filter((m) => m.taskRef !== null)
      .map((m) => m.runId)
      .sort();
    expect(claimed).toEqual(Object.keys(EXPECTED).sort());
  });

  it("negative fixture keeps no task context of its own beyond its record", () => {
    // DEV-RUN-020 IS claimed by TASK-CORE's record — but it must still fail
    // closed as a projection: no nodes, no edges, no history.
    const model = byId(DEV_RUN_020);
    expect(model.taskRef).toBe("TASK-CORE");
    expect(model.nodes).toEqual([]);
    expect(model.edges).toEqual([]);
    expect(model.orderedSteps).toEqual([]);
    expect(model.canonicalHistoryAvailable).toBe(false);
    expect(model.status).toBe("CONFLICT");
    expect(model.projectionStatus).toBe("CONFLICT");
  });
});
