import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, chmodSync, copyFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const SCRIPT = fileURLToPath(new URL("./typecheck-tests.mjs", import.meta.url));

function runWithFakeNpx({ stdout, exitCode }) {
  const dir = mkdtempSync(join(tmpdir(), "typecheck-tests-"));
  const scriptsDir = join(dir, "scripts");
  const binDir = join(dir, "bin");
  mkdirSync(scriptsDir);
  mkdirSync(binDir);
  copyFileSync(SCRIPT, join(scriptsDir, "typecheck-tests.mjs"));
  writeFileSync(join(dir, "tsconfig.json"), JSON.stringify({ compilerOptions: {} }));
  writeFileSync(join(scriptsDir, "typecheck-tests-baseline.json"), JSON.stringify({ count: 86 }));
  const fakeNpx = join(binDir, "npx");
  writeFileSync(fakeNpx, `#!/bin/sh\nprintf '%s' '${stdout.replaceAll("'", "'\\''")}'\nexit ${exitCode}\n`);
  chmodSync(fakeNpx, 0o755);
  try {
    return spawnSync(process.execPath, [join(scriptsDir, "typecheck-tests.mjs"), "--strict"], {
      cwd: dir,
      encoding: "utf8",
      env: { ...process.env, PATH: `${binDir}:${process.env.PATH ?? ""}` },
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("counts TypeScript diagnostics even when tsc exits nonzero", () => {
  const result = runWithFakeNpx({
    stdout: "tests/sample.test.ts(1,1): error TS1234: expected diagnostic\n",
    exitCode: 1,
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /errors\s+: 1/);
  assert.match(result.stdout, /OK: 1 <= baseline 86/);
});

test("fails closed when tsc exits nonzero without diagnostics", () => {
  const result = runWithFakeNpx({ stdout: "compiler process failed\n", exitCode: 1 });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /Test-code typecheck is NOT verified/);
});
