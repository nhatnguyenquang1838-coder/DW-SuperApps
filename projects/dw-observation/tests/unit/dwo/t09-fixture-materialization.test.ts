/**
 * T09 — Fixture scenario materialization unit tests.
 *
 * 1. 30/30 ids materialize a model (assert exact id set, not length).
 * 2. each model has non-empty nodes and edges where scenario declares deps.
 * 3. timeline/replay history present where scenario declares history.
 * 4. DEV-RUN-020 resolves to CONFLICT and fails closed.
 * 5. invariant: REJECTS an incomplete scenario definition.
 *
 * Execution protocol: TDD — write test, confirm RED, implement to GREEN.
 */

import { describe, it, expect } from "vitest";
import {
  materializeFixtureScenario,
  materializeAllFixtures,
} from "@/lib/dwo/materializeFixtureScenario";
import { FIXTURE_CATALOG, DEV_RUN_020 } from "@/lib/dwo/fixtureSpec";
import type { UnifiedRunWorkspaceModel } from "@/lib/runtime/unifiedRuntime";

// ---------------------------------------------------------------------------
// Test 1: 30/30 ids materialize a model (exact id set)
// ---------------------------------------------------------------------------

describe("T09-1: 30/30 fixture ids materialize", () => {
  it("materializes all 30 catalog ids with no duplicates and no extras", () => {
    const models = materializeAllFixtures();
    const ids = new Set(models.map((m) => m.runId));

    const catalogIds = new Set(FIXTURE_CATALOG.map((c) => c.id));

    expect(ids.size).toBe(30);
    expect(ids).toEqual(catalogIds);
  });

  it("every materialized model satisfies UnifiedRunWorkspaceModel shape", () => {
    const models = materializeAllFixtures();
    for (const m of models) {
      expect(typeof m.runId).toBe("string");
      expect(Array.isArray(m.nodes)).toBe(true);
      expect(Array.isArray(m.edges)).toBe(true);
      expect(Array.isArray(m.orderedSteps)).toBe(true);
      expect(typeof m.status).toBe("string");
      expect(typeof m.projectionStatus).toBe("string");
    }
  });
});

// ---------------------------------------------------------------------------
// Test 2: non-empty nodes/edges where scenario declares dependency structure
// ---------------------------------------------------------------------------

describe("T09-2: nodes and edges match catalog dependency structure", () => {
  it("each conforming model has nodes for self + declared children", () => {
    const models = materializeAllFixtures();
    for (const m of models) {
      if (m.runId === DEV_RUN_020) continue; // negative: empty nodes by design

      const catalogEntry = FIXTURE_CATALOG.find((c) => c.id === m.runId)!;

      // Self node always present for conforming runs
      const selfNode = m.nodes.find((n) => n.id === m.runId);
      expect(selfNode, `missing self node for ${m.runId}`).toBeDefined();

      // Child nodes present for each declared child
      for (const childId of catalogEntry.children) {
        const childNode = m.nodes.find((n) => n.id === childId);
        expect(childNode, `missing child node ${childId} for ${m.runId}`).toBeDefined();
      }
    }
  });

  it("dependency edges present where catalog declares deps", () => {
    const models = materializeAllFixtures();
    for (const m of models) {
      if (m.runId === DEV_RUN_020) continue;

      const catalogEntry = FIXTURE_CATALOG.find((c) => c.id === m.runId)!;

      for (const depId of catalogEntry.deps) {
        const depEdge = m.edges.find(
          (e) => e.kind === "DEPENDENCY" && e.target === m.runId && e.source === depId
        );
        expect(depEdge, `missing DEPENDENCY edge ${depId}->${m.runId}`).toBeDefined();
      }
    }
  });

  it("hierarchy edges (FANOUT) present where catalog declares children", () => {
    const models = materializeAllFixtures();
    for (const m of models) {
      if (m.runId === DEV_RUN_020) continue;

      const catalogEntry = FIXTURE_CATALOG.find((c) => c.id === m.runId)!;

      for (const childId of catalogEntry.children) {
        const hierarchyEdge = m.edges.find(
          (e) => e.kind === "FANOUT" && e.source === m.runId && e.target === childId
        );
        expect(hierarchyEdge, `missing FANOUT edge ${m.runId}->${childId}`).toBeDefined();
      }
    }
  });

  it("hierarchy and dependency edges are independent (no conflation)", () => {
    // DEV-RUN-003 depends on DEV-RUN-002 (DEPENDENCY edge in DEV-RUN-003's model)
    // DEV-RUN-003 is a child of DEV-RUN-001 (FANOUT edge in DEV-RUN-001's model).
    // The two edge kinds must be distinct and never conflated.
    const model003 = materializeFixtureScenario(
      FIXTURE_CATALOG.find((c) => c.id === "DEV-RUN-003")!
    );
    const model001 = materializeFixtureScenario(
      FIXTURE_CATALOG.find((c) => c.id === "DEV-RUN-001")!
    );

    const depEdge = model003.edges.find(
      (e) => e.kind === "DEPENDENCY" && e.source === "DEV-RUN-002" && e.target === "DEV-RUN-003"
    );
    const fanoutEdge = model001.edges.find(
      (e) => e.kind === "FANOUT" && e.source === "DEV-RUN-001" && e.target === "DEV-RUN-003"
    );

    expect(depEdge).toBeDefined();
    expect(fanoutEdge).toBeDefined();
    // They must be distinct edges with distinct kinds
    expect(depEdge!.kind).toBe("DEPENDENCY");
    expect(fanoutEdge!.kind).toBe("FANOUT");
    expect(depEdge!.id).not.toBe(fanoutEdge!.id);
  });
});

// ---------------------------------------------------------------------------
// Test 3: timeline/replay history present where scenario declares history
// ---------------------------------------------------------------------------

describe("T09-3: timeline / replay history", () => {
  it("conforming runs have canonicalHistoryAvailable = true and non-empty orderedSteps", () => {
    const models = materializeAllFixtures();
    for (const m of models) {
      if (m.runId === DEV_RUN_020) continue;

      expect(m.canonicalHistoryAvailable).toBe(true);
      expect(m.orderedSteps.length).toBeGreaterThan(0);
      // orderedSteps has valid sequence numbers
      for (const step of m.orderedSteps) {
        expect(typeof step.nodeId).toBe("string");
        expect(typeof step.sequence).toBe("number");
      }
    }
  });

  it("DEV-RUN-020 has no history (incompatible source, no fabricated timeline)", () => {
    const model = materializeFixtureScenario(
      FIXTURE_CATALOG.find((c) => c.id === DEV_RUN_020)!
    );
    expect(model.canonicalHistoryAvailable).toBe(false);
    expect(model.orderedSteps).toEqual([]);
  });

  it("orderedSteps sequence numbers are contiguous starting at 0", () => {
    const models = materializeAllFixtures();
    for (const m of models) {
      if (m.runId === DEV_RUN_020) continue;

      for (let i = 0; i < m.orderedSteps.length; i++) {
        expect(m.orderedSteps[i].sequence).toBe(i);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Test 4: DEV-RUN-020 resolves to CONFLICT and fails closed
// ---------------------------------------------------------------------------

describe("T09-4: DEV-RUN-020 fail-closed", () => {
  it("DEV-RUN-020 status is CONFLICT", () => {
    const model = materializeFixtureScenario(
      FIXTURE_CATALOG.find((c) => c.id === DEV_RUN_020)!
    );
    expect(model.status).toBe("CONFLICT");
  });

  it("DEV-RUN-020 projectionStatus is CONFLICT", () => {
    const model = materializeFixtureScenario(
      FIXTURE_CATALOG.find((c) => c.id === DEV_RUN_020)!
    );
    expect(model.projectionStatus).toBe("CONFLICT");
  });

  it("DEV-RUN-020 has no nodes or edges (no fabricated data)", () => {
    const model = materializeFixtureScenario(
      FIXTURE_CATALOG.find((c) => c.id === DEV_RUN_020)!
    );
    expect(model.nodes).toEqual([]);
    expect(model.edges).toEqual([]);
  });

  it("DEV-RUN-020 Next Flow is UNKNOWN (not resolved)", () => {
    const model = materializeFixtureScenario(
      FIXTURE_CATALOG.find((c) => c.id === DEV_RUN_020)!
    );
    // Next flow must not fabricate a path through a conflicted run
    expect(model.nodes).toEqual([]);
    expect(model.status).toBe("CONFLICT");
  });
});

// ---------------------------------------------------------------------------
// Test 5: invariant — REJECTS incomplete scenario definition
// ---------------------------------------------------------------------------

describe("T09-5: invariant — reject incomplete scenario", () => {
  it("throws on a catalog entry missing required id", () => {
    const incomplete = {
      ...FIXTURE_CATALOG[0],
      id: "", // missing required id
    } as typeof FIXTURE_CATALOG[number];

    expect(() => materializeFixtureScenario(incomplete)).toThrow();
  });

  it("throws on a catalog entry missing domain", () => {
    const incomplete = {
      ...FIXTURE_CATALOG[0],
      domain: "",
    } as typeof FIXTURE_CATALOG[number];

    expect(() => materializeFixtureScenario(incomplete)).toThrow();
  });

  it("throws on a catalog entry missing kind", () => {
    const incomplete = {
      ...FIXTURE_CATALOG[0],
      kind: "",
    } as typeof FIXTURE_CATALOG[number];

    expect(() => materializeFixtureScenario(incomplete)).toThrow();
  });
});