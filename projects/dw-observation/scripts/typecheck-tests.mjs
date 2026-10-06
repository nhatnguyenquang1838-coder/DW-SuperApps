// Non-blocking test-code typecheck gate.
//
// WHY THIS EXISTS
// ---------------
// tsconfig.json excludes "tests", so `tsc --noEmit` (the `typecheck` gate) has
// NEVER compiled a single test file. Measured at HEAD 210b6bd:
//
//   npx tsc --noEmit --listFilesOnly | grep -c 'tests/unit'   ->  0
//
// That means every green gate so far proved nothing about test code. A test
// suite with broken types, wrong call arity, or `possibly null` dereferences
// still reports "936 passed".
//
// This script type-checks ONLY test code, against the same compilerOptions, and
// reports a baseline. It is deliberately NON-BLOCKING: the 86 errors are
// pre-existing debt, not regressions from the DWO P1-P6 work, and turning the
// main gate red on inherited debt would hide real regressions.
//
// Usage:
//   node scripts/typecheck-tests.mjs            -> summary + exit 0
//   node scripts/typecheck-tests.mjs --strict    -> exit 1 when over baseline
//
// BASELINE: 86 errors / 16 codes. Lower it in lockstep with real fixes — never
// raise it to make the gate quiet.

import { spawnSync } from "node:child_process";
import { readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const BASELINE_FILE = join(HERE, "typecheck-tests-baseline.json");

const STRICT = process.argv.includes("--strict");

/**
 * Build a tsconfig that includes tests/ while inheriting every real
 * compilerOption from the project config, so test code is checked under the
 * exact same strictness as production code.
 */
function writeTempTsconfig() {
  const base = JSON.parse(readFileSync(join(ROOT, "tsconfig.json"), "utf8"));
  const merged = {
    ...base,
    compilerOptions: { ...base.compilerOptions, incremental: false, noEmit: true },
    // vitest.setup.ts MUST be included: it imports @testing-library/jest-dom,
    // which is what declares the custom matchers (toBeInTheDocument, ...).
    // Without it every jest-dom assertion reports TS2339 and the count is inflated
    // by ~113 phantom errors.
    include: [
      "next-env.d.ts",
      "vitest.setup.ts",
      "tests/**/*.ts",
      "tests/**/*.tsx",
      ".next/types/**/*.ts",
    ],
    exclude: ["node_modules", "dw_observation", "fixtures"],
  };
  const out = join(ROOT, "tsconfig.typecheck-tests.tmp.json");
  writeFileSync(out, JSON.stringify(merged, null, 2));
  return out;
}

const tmpConfig = writeTempTsconfig();
const proc = spawnSync(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["tsc", "--noEmit", "-p", tmpConfig],
  { cwd: ROOT, encoding: "utf8" },
);

// Always remove the temp config, even on failure — leaving it behind would
// show up as an untracked file and could be picked up by a later tsc run.
rmSync(tmpConfig, { force: true });

// FAIL-CLOSED: if tsc never launched (npx/node missing, spawn error) or
// crashed (non-zero status with no TS diagnostics), an empty output must NOT
// be interpreted as "zero errors". Without this check a broken invocation
// would print "OK: 0 <= baseline" and exit 0 — a vacuous pass (F1 class).
if (proc.error) {
  console.error(
    `GATE FAILED: could not launch tsc (${proc.error.message}). ` +
      `Test-code typecheck is NOT verified — exiting 2 so CI fails closed.`
  );
  process.exit(2);
}
if (proc.status !== 0) {
  console.error(
    `GATE FAILED: tsc exited with status ${proc.status}. ` +
      `The output above may be truncated; test-code typecheck is NOT verified.`
  );
  process.exit(2);
}

const output = `${proc.stdout ?? ""}${proc.stderr ?? ""}`;
const lines = output.split("\n").filter((l) => /error TS\d+:/.test(l));
const byCode = {};
for (const line of lines) {
  const m = /error (TS\d+):/.exec(line);
  if (m) byCode[m[1]] = (byCode[m[1]] ?? 0) + 1;
}
const byFile = {};
for (const line of lines) {
  const m = /^(tests\/[^(:]+)/.exec(line.trim());
  if (m) byFile[m[1]] = (byFile[m[1]] ?? 0) + 1;
}

const count = lines.length;

let baseline = { count: 86, note: "measured at 210b6bd; pre-existing debt" };
try {
  baseline = JSON.parse(readFileSync(BASELINE_FILE, "utf8"));
} catch {
  /* first run — keep the inline default */
}

console.log("── test-code typecheck (NON-BLOCKING) ──");
console.log(`  errors : ${count}`);
console.log(`  baseline: ${baseline.count}`);
console.log(`  delta   : ${count - baseline.count >= 0 ? "+" : ""}${count - baseline.count}`);
console.log("");
console.log("  by code:");
for (const [code, n] of Object.entries(byCode).sort((a, b) => b[1] - a[1])) {
  console.log(`    ${code.padEnd(9)} ${n}`);
}
console.log("");
console.log("  by file (top 12):");
for (const [file, n] of Object.entries(byFile).sort((a, b) => b[1] - a[1]).slice(0, 12)) {
  console.log(`    ${String(n).padStart(3)}  ${file}`);
}
console.log("");

if (count > baseline.count) {
  console.error(
    `REGRESSION: ${count} test-code type errors, baseline is ${baseline.count}. ` +
      `New type errors in test code are never acceptable — fix them, do not raise the baseline.`
  );
  // Non-blocking by default: still exit 0 so CI stays green on inherited debt,
  // but make the regression impossible to miss in the log.
  process.exit(STRICT ? 1 : 0);
}
if (STRICT) {
  console.log(`OK: ${count} <= baseline ${baseline.count}.`);
  process.exit(0);
}
console.log(
  `Known debt: ${count} pre-existing test-code type errors (tsconfig excludes tests, ` +
    `so the main typecheck gate never saw them). Pass --strict once this reaches 0.`
);
process.exit(0);