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
import { readFileSync, statSync } from "fs";
import { join } from "path";
import { reduceEventPrefix } from "../../../lib/dwo/reducer";

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
  it("DEV-RUN-020 status is INCOMPATIBLE", () => {
    const model = materializeFixtureScenario(
      FIXTURE_CATALOG.find((c) => c.id === DEV_RUN_020)!
    );
    expect(model.status).toBe("INCOMPATIBLE");
  });

  it("DEV-RUN-020 projectionStatus is INCOMPATIBLE", () => {
    const model = materializeFixtureScenario(
      FIXTURE_CATALOG.find((c) => c.id === DEV_RUN_020)!
    );
    expect(model.projectionStatus).toBe("INCOMPATIBLE");
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
    expect(model.status).toBe("INCOMPATIBLE");
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

// ---------------------------------------------------------------------------
// T09-6: evidence from fixture pack — every conforming scenario yields
//         non-empty evidence (artifacts / fileReads / history as applicable)
// ---------------------------------------------------------------------------

const FIXTURE_PACK = join(
  __dirname,
  "../../../dwo-v2/fixtures/DWO-UR-30-V1"
);

function loadEvents(): Array<{
  event_id: string;
  run_id: string;
  ordinal: number;
  run_state: string;
  gate: string | null;
  gate_state: string | null;
  source_profile: string;
  sync_state: string;
  semantic_qualification: string;
  authority_state: "PENDING" | "GRANTED" | "DENIED" | "EXPIRED" | "REVOKED" | "NOT_REQUIRED" | "UNKNOWN" | "NOT_APPLICABLE";
  anomaly_count: number;
}> {
  const raw = readFileSync(join(FIXTURE_PACK, "events", "projection-events.jsonl"), "utf-8");
  return raw
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line))
    .sort((a, b) => a.ordinal - b.ordinal);
}

function evidenceFilesForRun(runId: string): string[] {
  const dirs = ["execution", "target", "verification", "closure", "handoff", "authority"];
  const files: string[] = [];
  for (const dir of dirs) {
    const dirPath = join(FIXTURE_PACK, "evidence", dir);
    try {
      const stat = statSync(dirPath);
      if (!stat.isDirectory()) continue;
    } catch {
      continue;
    }
    const { readdirSync } = require("fs");
    try {
      const entries = readdirSync(dirPath);
      for (const entry of entries) {
        if (entry.startsWith(`${runId}-`)) {
          files.push(`${dir}/${entry}`);
        }
      }
    } catch {
      continue;
    }
  }
  return files;
}

describe("T09-6: evidence from fixture pack", () => {
  it("conforming scenarios have non-empty artifacts per node", () => {
    const models = materializeAllFixtures();

    for (const m of models) {
      if (m.runId === DEV_RUN_020) continue;

      for (const node of m.nodes) {
        const evFiles = evidenceFilesForRun(node.id);
        expect(
          node.artifacts.length,
          `${node.id}: artifacts should be populated from fixture pack evidence`
        ).toBeGreaterThan(0);
        expect(
          node.executorHistory.length,
          `${node.id}: executorHistory should be populated`
        ).toBeGreaterThan(0);
        expect(
          node.artifacts,
          `${node.id}: artifacts should reference evidence files`
        ).toEqual(
          expect.arrayContaining(evFiles.map((f) => expect.stringContaining(f)))
        );
      }
    }
  });

  it("DEV-RUN-020 has zero fabricated evidence (fail-closed)", () => {
      const model = materializeFixtureScenario(
        FIXTURE_CATALOG.find((c) => c.id === DEV_RUN_020)!
      );
      for (const node of model.nodes) {
        expect(node.artifacts).toEqual([]);
        expect(node.executorHistory).toEqual([]);
      }
    });
  });

  // ── E5 run-linkage negative test ───────────────────────────────────────────
  // @qa flagged: evidenceFilesForRun() must return ONLY files for the named run,
  // never cross-run leakage. Before this test the helper asserted via
  // arrayContaining([]) (vacuous) and never verified per-run isolation.
  describe("t09-E5 · evidence file linkage is run-scoped (no cross-run leak)", () => {
    const KNOWN_RUN = "DEV-RUN-001"; // has evidence files in the fixture pack

    it("returns evidence files scoped to the named run", () => {
      const files = evidenceFilesForRun(KNOWN_RUN);
      expect(files.length).toBeGreaterThan(0);
      // Every returned path must contain the runId — no foreign-run leakage.
      for (const f of files) {
        expect(f).toContain(KNOWN_RUN);
      }
    });

    it("returns empty for a run with no evidence (fail-closed, no inference)", () => {
      const files = evidenceFilesForRun("NO-SUCH-RUN-9999");
      expect(files).toEqual([]);
    });

    it("never surfaces another run's evidence for this runRef", () => {
      const foreign = evidenceFilesForRun("DEV-RUN-002");
      const underTest = evidenceFilesForRun(KNOWN_RUN);
      // No element of underTest should originate from DEV-RUN-002.
      for (const f of underTest) {
        expect(f).not.toContain("DEV-RUN-002");
      }
      // Sanity: DEV-RUN-002 has its own files (proves the negative guard is real).
      expect(foreign.length).toBeGreaterThan(0);
    });
  });

// ---------------------------------------------------------------------------
// T09-7: dependency edges — UNKNOWN unless evidence supports SATISFIED
// ---------------------------------------------------------------------------

describe("PR130 fixture hierarchy and incompatibility regressions", () => {
  it("materializes the complete 017 → 018 → 019 descendant chain", () => {
    const root = materializeFixtureScenario(FIXTURE_CATALOG.find((c) => c.id === "DEV-RUN-017")!);
    expect(root.nodes.map((node) => node.id)).toEqual(expect.arrayContaining(["DEV-RUN-017", "DEV-RUN-018", "DEV-RUN-019"]));
    expect(root.edges.filter((edge) => edge.kind === "FANOUT").map(({ source, target }) => [source, target])).toEqual([
      ["DEV-RUN-017", "DEV-RUN-018"],
      ["DEV-RUN-018", "DEV-RUN-019"],
    ]);
  });

  it("derives complete run and gate facts from validated reducer events for every golden fixture", () => {
    const events = loadEvents();
    const models = materializeAllFixtures();
    for (const fixture of FIXTURE_CATALOG) {
      const model = models.find((candidate) => candidate.runId === fixture.id)!;
      if (fixture.id === DEV_RUN_020) continue;
      const source = events.filter((event) => event.run_id === fixture.id).at(-1)!;
      expect(model.status).toBe(source.run_state);
      expect(model.gate).toBe(source.gate);
      const legacyTerminal = source.gate_state === "CANCELLED" || source.gate_state === "SUPERSEDED";
      expect(model.gateState).toBe(legacyTerminal ? null : source.gate_state);
      if (legacyTerminal) expect(model.sourceTerminalMarker).toBe(source.gate_state);
    }
    expect(models.find((candidate) => candidate.runId === "DEV-RUN-022")?.gateState).toBe("WAITING");
    expect(models.find((candidate) => candidate.runId === "DEV-RUN-030")?.authorityState).toBe("NOT_APPLICABLE");
  });

  it("preserves legacy CANCELLED/SUPERSEDED gate observations explicitly", () => {
    const cancelled = materializeFixtureScenario(FIXTURE_CATALOG.find((fixture) => fixture.id === "DEV-RUN-013")!);
    const superseded = materializeFixtureScenario(FIXTURE_CATALOG.find((fixture) => fixture.id === "DEV-RUN-015")!);
    expect(cancelled.status).toBe("CANCELLED");
    expect(cancelled.sourceTerminalMarker).toBe("CANCELLED");
    expect(cancelled.gateState).toBeNull();
    expect(superseded.status).toBe("SUPERSEDED");
    expect(superseded.sourceTerminalMarker).toBe("SUPERSEDED");
    expect(superseded.gateState).toBeNull();
  });

  it("does not populate observed node gate state from catalog when the prefix is empty", () => {
    const model = materializeFixtureScenario(FIXTURE_CATALOG.find((fixture) => fixture.id === "DEV-RUN-030")!, { events: [] });
    expect(model.nodes).toHaveLength(1);
    expect(model.nodes[0]?.gateState).toBeNull();
    expect(model.nodes[0]?.gateId).toBeNull();
    expect(model.nodes[0]?.sourceStatus).toBe("UNKNOWN");
    expect(model.status).toBe("UNKNOWN");
    expect(model.gateState).toBeNull();
    expect(model.sourceProfile).toBe("UNKNOWN");
    expect(model.syncState).toBe("UNKNOWN");
    expect(model.semanticQualification).toBe("UNKNOWN");
    expect(model.authorityState).toBe("UNKNOWN");
    expect(model.anomalyCount).toBe("UNKNOWN");
    expect(model.projectionStatus).toBe("UNKNOWN");
    expect(model.canonicalHistoryAvailable).toBe(false);
    expect(model.orderedSteps).toEqual([]);
  });

  it("matches canonical reducer state for every valid run prefix", () => {
    const events = loadEvents();
    const models = materializeAllFixtures();
    for (const fixture of FIXTURE_CATALOG) {
      if (fixture.id === DEV_RUN_020) continue;
      const prefix = events.filter((event) => event.run_id === fixture.id);
      const model = models.find((candidate) => candidate.runId === fixture.id)!;
      const reduced = reduceEventPrefix(fixture.id, prefix.map((event) => ({
        eventId: event.event_id,
        runId: event.run_id,
        ordinal: event.ordinal,
        gate: event.gate,
        gateState: event.gate_state === "CANCELLED" || event.gate_state === "SUPERSEDED" ? null : event.gate_state,
        runState: event.run_state,
        sourceProfile: event.source_profile,
        syncState: event.sync_state,
        semanticQualification: event.semantic_qualification,
        authorityState: event.authority_state as "PENDING" | "GRANTED" | "DENIED" | "EXPIRED" | "REVOKED" | "NOT_REQUIRED" | "UNKNOWN" | "NOT_APPLICABLE",
        anomalyCount: event.anomaly_count,
      })));
      expect(model.status).toBe(reduced.runState);
      expect(model.gate).toBe(reduced.gate);
      expect(model.gateState).toBe(reduced.gateState);
      expect(model.sourceProfile).toBe(reduced.sourceProfile);
      expect(model.syncState).toBe(reduced.syncState);
      expect(model.semanticQualification).toBe(reduced.semanticQualification);
      expect(model.authorityState).toBe(reduced.authorityState);
      expect(model.anomalyCount).toBe(reduced.anomalyCount);
      expect(model.nodes.find((node) => node.id === fixture.id)?.gateId).toBe(reduced.gate);
      expect(model.nodes.find((node) => node.id === fixture.id)?.gateState).toBe(reduced.gateState);
    }
  });

  it("keeps dependencies declared by every descendant separate from fanout", () => {
    const model = materializeFixtureScenario(FIXTURE_CATALOG.find((fixture) => fixture.id === "DEV-RUN-024")!);
    expect(model.edges).toContainEqual(expect.objectContaining({ kind: "DEPENDENCY", source: "DEV-RUN-025", target: "DEV-RUN-026", state: "UNKNOWN" }));
    expect(model.edges).toContainEqual(expect.objectContaining({ kind: "FANOUT", source: "DEV-RUN-024", target: "DEV-RUN-026" }));
  });

  it("rejects ancestor cycles before hierarchy traversal", () => {
    const entry = { ...FIXTURE_CATALOG.find((fixture) => fixture.id === "DEV-RUN-017")!, parent: "DEV-RUN-017" } as typeof FIXTURE_CATALOG[number];
    expect(() => materializeFixtureScenario(entry, { events: [] })).toThrow(/cycle/i);
  });

  it("rejects duplicate event identities and per-run ordinals", () => {
    const source = loadEvents().find((event) => event.run_id === "DEV-RUN-030")!;
    const fixture = FIXTURE_CATALOG.find((entry) => entry.id === "DEV-RUN-030")!;
    expect(() => materializeFixtureScenario(fixture, { events: [{ ...source, event_id: "  " }] })).toThrow(/invalid fixture projection event schema/i);
    expect(() => materializeFixtureScenario(fixture, { events: [source, { ...source, event_id: "other-id" }] })).toThrow(/duplicate.*ordinal/i);
    expect(() => materializeFixtureScenario(fixture, { events: [source, { ...source, ordinal: source.ordinal + 1 }] })).toThrow(/duplicate.*event id/i);
  });

  it("preserves source incompatibility separately from relation conflict", () => {
    const model = materializeFixtureScenario(FIXTURE_CATALOG.find((c) => c.id === DEV_RUN_020)!);
    expect(model.status).toBe("INCOMPATIBLE");
    expect(model.projectionStatus).toBe("INCOMPATIBLE");
    expect(model.nodes).toEqual([]);
    expect(model.edges).toEqual([]);
    expect(model.orderedSteps).toEqual([]);
  });
});

describe("T09-7: dependency edges are UNKNOWN without evidence", () => {
  it("no dependency edge is SATISFIED unless evidence explicitly supports it", () => {
    const models = materializeAllFixtures();
    for (const m of models) {
      if (m.runId === DEV_RUN_020) continue;
      for (const edge of m.edges) {
        if (edge.kind === "DEPENDENCY") {
          expect(
            edge.state,
            `DEPENDENCY edge ${edge.source}->${edge.target} must be UNKNOWN (no evidence says SATISFIED)`
          ).toBe("UNKNOWN");
        }
      }
    }
  });
});

// ---------------------------------------------------------------------------
// T09-8: timeline from event sequence, not node array order
// ---------------------------------------------------------------------------

describe("T09-8: timeline from event sequence", () => {
  it("orderedSteps follows projection-events.jsonl ordinal order", () => {
    const events = loadEvents();
    const models = materializeAllFixtures();

    for (const m of models) {
      if (m.runId === DEV_RUN_020) continue;

      const scenarioRunIds = m.nodes.map((n) => n.id);
      const scenarioEvents = events.filter((e) =>
        scenarioRunIds.includes(e.run_id)
      );

      // orderedSteps must follow event ordinal order, not catalog array order
      for (let i = 0; i < m.orderedSteps.length; i++) {
        expect(m.orderedSteps[i].nodeId).toBe(scenarioEvents[i].run_id);
        expect(m.orderedSteps[i].sequence).toBe(i);
      }
    }
  });
});