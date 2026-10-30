import { spawnSync } from "node:child_process";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("scripts/typecheck-tests.mjs launcher", () => {
  it("runs the local TypeScript compiler on Windows instead of failing on npx.cmd", () => {
    const script = path.resolve(process.cwd(), "scripts/typecheck-tests.mjs");
    const result = spawnSync(process.execPath, [script, "--strict"], {
      cwd: process.cwd(),
      encoding: "utf8",
      timeout: 120_000,
    });
    const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;

    expect(result.error, output).toBeUndefined();
    expect(result.status, output).not.toBe(2);
    expect(output).toContain("test-code typecheck");
  });
});
