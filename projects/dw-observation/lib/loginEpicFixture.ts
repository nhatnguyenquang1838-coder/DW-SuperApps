import { readFileSync } from "fs";
import path from "path";
import type { LoginEpicRuntimeFixture } from "@/lib/loginEpicRuntimeGraph";

/**
 * Load the Login Epic fixture deterministically in Node (server page + tests).
 * The Controller-transferred generator emits the canonical fixture as a JS module
 * (`window.EPIC = {...};`) under fixtures/. We strip the wrapper and parse the JSON
 * so there is ONE source of truth (no duplicated raw copy). A sibling
 * `login_epic_10_runs_gwc_taskcontroller_data.raw.json` at the repo root is also
 * accepted if present.
 */
export function loadLoginEpicFixture(): LoginEpicRuntimeFixture {
  const cwd = process.cwd();
  const candidates = [
    path.join(cwd, "login_epic_10_runs_gwc_taskcontroller_data.raw.json"),
    path.join(cwd, "projects/dw-observation/fixtures", "login_epic_10_runs_gwc_taskcontroller_data.json"),
    path.join(cwd, "fixtures", "login_epic_10_runs_gwc_taskcontroller_data.json"),
  ];
  for (const f of candidates) {
    try {
      const txt = readFileSync(f, "utf8").trim();
      if (txt.startsWith("{")) return JSON.parse(txt) as LoginEpicRuntimeFixture;
      if (txt.startsWith("window.EPIC")) {
        const json = txt.replace(/^window\.EPIC\s*=\s*/, "").replace(/;\s*$/, "");
        return JSON.parse(json) as LoginEpicRuntimeFixture;
      }
    } catch {
      // try next candidate
    }
  }
  throw new Error("login epic fixture not found in any known location");
}
