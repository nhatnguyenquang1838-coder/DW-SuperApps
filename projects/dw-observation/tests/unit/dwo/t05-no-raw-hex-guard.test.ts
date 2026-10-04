/**
 * Repo-wide guard: raw hex literals are forbidden outside the single token file.
 *
 * Spec rule: DWO tokens live ONLY in app/globals.css. Components and pages use
 * semantic tokens or CSS vars. Naming the rule in a task body is not enforcement —
 * a worker reaches for the most familiar palette it already sees in the repo
 * (here: the legacy Notion `#37352f` / `#787774` headings and the invented edge
 * colors `#ffd34d` / `#6ca9ff`, none of which exist in the 22 Penpot tokens) and
 * reports "no raw hex" while adding six.
 *
 * TWO TIERS, because the legacy pre-DWO pages still carry their Notion palette
 * and the DAG that retires them is still running:
 *
 *   Tier 1 — ABSOLUTE. The DWO v2 surface established by T05 must have zero raw
 *   hex: `components/dwo/**` and the live run workspace page.
 *   Tier 2 — RATCHET. Every other scanned file is a debt ledger: the count may
 *   shrink as T06/T09/T12 rewrite them, but it may never grow. Asserting
 *   `count <= CEILING` (not `=== 0`) is what makes this a ratchet — each task
 *   that cleans a file lowers the number, and nothing can quietly re-add.
 *
 * A guard that only checks tier 1 would pass while ~60 literals rot; one that
 * only checks tier 2 would go red on every task and block the DAG.
 *
 * NOTE the self-check assertions at the bottom: a guard whose file walk resolves
 * to the wrong directory scans zero files and passes VACUOUSLY — that is a real
 * failure mode, observed when this file was first written with an off-by-one
 * `__dirname` depth and reported 3/3 green. Prove the scan is non-empty, and that
 * the hex regex matches a known-bad string, before trusting a green run.
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(__dirname, "../../..");
const SCAN_DIRS = ["app", "components", "lib"];
const ALLOWED_FILES = new Set(["app/globals.css"]);

/** Tier 1 — zero tolerance. */
const DWO_SURFACE = ["components/dwo/", "app/runs/[runId]/page.tsx"];

/**
 * Tier 2 debt ceiling, measured 2026-10-04 with the SAME matcher as this guard
 * (per-match, not per-line — `grep -c` undercounts lines that carry two literals).
 * Lower it as each legacy file is rewritten; NEVER raise it.
 *
 *   start        85  (baseline after the T05 supervisor fix)
 *   - T06        17  app/runs/[runId]/replay/page.tsx fully de-hexed
 *   current      68
 *
 *   app/dev/fixtures/page.tsx          31  -> T09 Fixture Lab
 *   app/runs/page.tsx                  25  -> T12 Run Explorer
 *   components/RunGraphEdge.tsx         6
 *   components/RunGraphView.tsx         2
 *   components/login-epic/*             3  -> legacy, superseded by dwo/
 *   components/DagView.tsx              1
 */
const DEBT_CEILING = 68;

const SOURCE_RE = /\.(tsx?|jsx?)$/;
// 3-digit shorthand counts too: #fff is the same drift as #ffffff.
const HEX_RE = /#[0-9a-fA-F]{3,8}\b/g;

type Offence = { file: string; line: number; value: string; text: string };

function walk(dir: string, acc: string[] = []): string[] {
  const abs = path.join(ROOT, dir);
  if (!fs.existsSync(abs)) return acc;
  for (const entry of fs.readdirSync(abs, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
    const rel = `${dir}/${entry.name}`;
    if (entry.isDirectory()) walk(rel, acc);
    else if (SOURCE_RE.test(entry.name)) acc.push(rel);
  }
  return acc;
}

function isDwoSurface(file: string): boolean {
  return DWO_SURFACE.some((p) => file.startsWith(p));
}

const files = SCAN_DIRS.flatMap((d) => walk(d)).filter((f) => !ALLOWED_FILES.has(f));

const offences: Offence[] = [];
for (const file of files) {
  const src = fs.readFileSync(path.join(ROOT, file), "utf-8");
  src.split("\n").forEach((text, i) => {
    for (const m of text.match(HEX_RE) ?? []) {
      // A hex length outside 3/4/6/8 is not a color literal (e.g. an id fragment).
      if (![3, 4, 6, 8].includes(m.length - 1)) continue;
      offences.push({ file, line: i + 1, value: m, text: text.trim().slice(0, 100) });
    }
  });
}

const fmt = (os: Offence[]) => os.map((o) => `  ${o.file}:${o.line}  ${o.value}  ${o.text}`).join("\n");

describe("raw hex guard (DWO token single-source rule)", () => {
  it("scans a non-trivial file set — a zero-file scan passes vacuously", () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it("the regex matches a known-bad literal and ignores a token var", () => {
    // `.match` returns null (not []) on no match — assert the length explicitly.
    expect(`color: "#37352f"`.match(HEX_RE)).toHaveLength(1);
    expect(`color: "var(--dwo-color-text-muted)"`.match(HEX_RE) ?? []).toHaveLength(0);
  });

  it("tier 1: zero raw hex on the DWO v2 surface", () => {
    const onDwo = offences.filter((o) => isDwoSurface(o.file));
    expect(
      onDwo,
      `Raw hex on the DWO surface — use a semantic token or CSS var:\n${fmt(onDwo)}`,
    ).toEqual([]);
  });

  it("tier 2: legacy debt ratchet never grows", () => {
    expect(offences.length).toBeLessThanOrEqual(DEBT_CEILING);
  });
});