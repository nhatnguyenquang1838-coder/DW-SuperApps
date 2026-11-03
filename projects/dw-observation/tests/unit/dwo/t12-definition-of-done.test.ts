/**
 * TECH_SPEC §15 — Definition of Done guards.
 *
 * T12 reported "all 13 criteria PASS" while two of them were false:
 *   - "no raw anchor navigation remains where Next Link/router semantics are
 *      expected" — app/layout.tsx still shipped a parallel header built from
 *      <a href> tags, duplicating TopNavigation (which uses next/link).
 *   - "dev-only simulations are not primary product navigation" — /dev/fixtures
 *      was listed in the same nav array as /tasks and /runs.
 *
 * Both were true violations that 887 unit tests, 11 e2e tests and a clean tsc
 * all passed straight through. So they are asserted here as text, which is the
 * only thing that can catch them.
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(__dirname, "../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf-8");
}

/**
 * Match a real anchor tag only. `<a\s+href=` is WRONG: `\s` matches newlines,
 * so it latches onto prose in a block comment ("Root runs\nnavigation" reads as
 * `<a` + whitespace + `href=`). Require same-line whitespace and a tag boundary.
 */
const RAW_ANCHOR = /<a[ \t]+href=/;

describe("§15 — raw anchor navigation", () => {
  const SHELL_FILES = ["app/layout.tsx", "components/dwo/TopNavigation.tsx"];

  it("the app shell and primary nav contain no raw <a href>", () => {
    const offenders = SHELL_FILES.filter((f) => RAW_ANCHOR.test(read(f)));
    expect(
      offenders,
      `Raw <a href> in the shell — use next/link:\n  ${offenders.join("\n  ")}`,
    ).toEqual([]);
  });

  it("app/layout.tsx does not hand-roll a parallel header", () => {
    // One navigation authority. Two navs drift; that is how /dev/sim/g0g6 came
    // to sit in the product header beside /tasks.
    const layout = read("app/layout.tsx");
    expect(layout).toContain("TopNavigation");
    expect(layout).not.toMatch(/<nav\b/);
  });

  it("task runs back-link uses next/link, not an anchor", () => {
    expect(RAW_ANCHOR.test(read("app/tasks/[taskId]/runs/page.tsx"))).toBe(false);
  });

  it("the anchor pattern is not over-broad (self-check)", () => {
    // A guard that fails on prose is worse than no guard: it trains you to
    // ignore it. Prove the pattern needs a real tag.
    expect(RAW_ANCHOR.test("// Root runs\nnavigation")).toBe(false);
    expect(RAW_ANCHOR.test('<a href="/x">')).toBe(true);
  });
});

describe("§15 — dev-only routes are not primary product navigation", () => {
  it("TopNavigation's default items exclude every /dev route", () => {
    const src = read("components/dwo/TopNavigation.tsx");
    const block = src.slice(
      src.indexOf("const defaultItems"),
      src.indexOf("];", src.indexOf("const defaultItems")),
    );
    expect(block).not.toMatch(/href:\s*"\/dev\//);
  });

  it("product nav still offers the real product routes", () => {
    const src = read("components/dwo/TopNavigation.tsx");
    expect(src).toContain('href: "/tasks"');
    expect(src).toContain('href: "/runs"');
  });

  it("dev lanes stay reachable by direct URL", () => {
    // Not being in the nav must not mean deleted.
    for (const p of ["app/dev/fixtures/page.tsx", "app/dev/sim/g0g6/page.tsx"]) {
      expect(fs.existsSync(path.join(ROOT, p)), `${p} must still exist`).toBe(true);
    }
  });
});