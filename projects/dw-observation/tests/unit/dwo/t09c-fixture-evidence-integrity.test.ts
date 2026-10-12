// T09c — Fixture Lab evidence integrity (P5 follow-up).
//
// INVARIANT: the DWO-UR-30-V1 fixture pack is real, on-disk evidence. The
// Fixture Lab surface must never render a materialized model whose evidence was
// silently dropped because the browser bundle could not reach `fs`.
//
// The previous implementation imported materializeFixtureScenario from a
// "use client" page. That page shipped `require("fs")` into the browser bundle,
// the bundler logged `Can't resolve 'fs'`, every loader hit its `if (!fs) return
// []` branch, and the Lab rendered an EMPTY projection while every visual test
// still passed. That is fail-OPEN behaviour, which the fail-closed contract
// forbids.
//
// These tests pin the boundary:
//   1. the server-side loader really does read the pack (events are non-empty),
//   2. a missing/unreadable pack yields UNAVAILABLE, never a fabricated model,
//   3. the "use client" page must not reach the filesystem loader at all.

import { describe, it, expect } from "vitest";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import {
  materializeFixtureScenario,
  materializeAllFixtures,
} from "@/lib/dwo/materializeFixtureScenario";
import { FIXTURE_CATALOG } from "@/lib/dwo/fixtureSpec";

const PACK = join(process.cwd(), "dwo-v2/fixtures/DWO-UR-30-V1");

describe("Fixture Lab evidence is read from the real pack (never fail-open)", () => {
  it("the DWO-UR-30-V1 pack exists on disk", () => {
    expect(existsSync(join(PACK, "events", "projection-events.jsonl"))).toBe(true);
    expect(existsSync(join(PACK, "evidence"))).toBe(true);
  });

  it("materializing a real scenario yields a non-empty projection", () => {
    const entry = FIXTURE_CATALOG.find((f) => f.kind !== "NEGATIVE")!;
    const model = materializeFixtureScenario(entry);

    // A fail-open materialization would produce zero nodes/edges here.
    expect(model.nodes.length).toBeGreaterThan(0);
    expect(model.orderedSteps.length).toBeGreaterThan(0);
    expect(model.projectionStatus).not.toBe("PROJECTION_UNAVAILABLE");
  });

  it("every POSITIVE catalog scenario materializes real nodes", () => {
    const positive = FIXTURE_CATALOG.filter((f) => f.kind !== "NEGATIVE");
    expect(positive.length).toBeGreaterThan(0);

    for (const entry of positive) {
      const model = materializeFixtureScenario(entry);
      expect(
        model.nodes.length,
        `scenario ${entry.id} materialized with zero nodes — evidence was dropped`
      ).toBeGreaterThan(0);
    }
  });

  it("materializeAllFixtures covers the 30-scenario catalog without empties", () => {
    const all = materializeAllFixtures();
    expect(all.length).toBe(FIXTURE_CATALOG.length);

    const empties = all.filter(
      (m) => m.status !== "CONFLICT" && m.nodes.length === 0
    );
    expect(
      empties.map((m) => m.runId),
      "these scenarios rendered an empty projection — that is fail-open"
    ).toEqual([]);
  });

  it("the fixture events file actually has events (the loaders are not vacuous)", () => {
    const raw = readFileSync(
      join(PACK, "events", "projection-events.jsonl"),
      "utf-8"
    );
    const lines = raw.trim().split("\n").filter(Boolean);
    expect(lines.length).toBeGreaterThan(0);
  });
});

describe("fixture page boundary: no filesystem loader behind \"use client\"", () => {
  const pagePath = join(
    process.cwd(),
    "app/dev/fixtures/page.tsx"
  );

  it("the dev fixtures route is NOT a client component", () => {
    const src = readFileSync(pagePath, "utf-8");
    expect(
      src.startsWith('"use client"'),
      "app/dev/fixtures/page.tsx is still \"use client\" — it can never read the evidence pack"
    ).toBe(false);
  });

  it("no client component imports the filesystem materializer directly", () => {
    const offenders: string[] = [];
    // Match real import/require statements only — a prose mention in a comment
    // (e.g. "do NOT import materializeFixtureScenario here") must not trip this.
    const importRe =
      /(?:from\s+|require\(\s*|import\(\s*)["'][^"']*materializeFixtureScenario["']/;
    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === "node_modules" || entry.name === ".next") continue;
        const full = join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(full);
        } else if (/\.(ts|tsx)$/.test(entry.name)) {
          const src = readFileSync(full, "utf-8");
          // Only a directive-leading file is a client component.
          const isClient = /^\s*["']use client["']/.test(src);
          if (isClient && importRe.test(src)) {
            offenders.push(full);
          }
        }
      }
    };
    walk(join(process.cwd(), "app"));
    walk(join(process.cwd(), "components"));
    expect(offenders).toEqual([]);
  });
});