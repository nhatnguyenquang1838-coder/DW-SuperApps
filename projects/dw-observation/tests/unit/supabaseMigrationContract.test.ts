/**
 * supabaseMigrationContract.test.ts
 * TASK 2 RED — contract test for the single approved new migration:
 *   projects/dw-observation/supabase/migrations/20260823T100000Z_projection_events.sql
 *
 * This test binds the migration SQL file directly (no live Supabase / no network)
 * and asserts the full projection_events contract. It must be RED until the
 * migration is implemented (GREEN), proving the intended behavior is absent.
 *
 * Contract (from Correction-3 G2 envelope / written-proposal):
 *   - projection_events table
 *   - unique canonical event identity (run_id, source_system, source_event_id)
 *   - durable projection_ordinal ordering + required indexes
 *   - notify_projection_event() + AFTER INSERT trigger
 *   - exact broadcast: realtime.send(payload, 'projection_event', 'observatory:' || run_id, false)
 *   - RLS enabled
 *   - SELECT-only policy for anon/authenticated (publishable-key read path)
 *   - NO client INSERT/UPDATE/DELETE policy
 *   - NO historical projection-event backfill (migration must not INSERT rows)
 * Guard (unchanged existing migrations):
 *   - DDL 20260823T080000Z_observatory_history.sql sha256 = 346d805c...
 *   - DML 20260823T090000Z_observatory_backfill_dml.sql sha256 = f5255eea...
 */

import { describe, it, expect, beforeAll } from "vitest";
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";

const MIGRATIONS_DIR = path.resolve(__dirname, "..", "..", "supabase", "migrations");
const NEW_MIGRATION = path.join(
  MIGRATIONS_DIR,
  "20260823T100000Z_projection_events.sql",
);
const DDL_FILE = path.join(
  MIGRATIONS_DIR,
  "20260823T080000Z_observatory_history.sql",
);
const DML_FILE = path.join(
  MIGRATIONS_DIR,
  "20260823T090000Z_observatory_backfill_dml.sql",
);

// Raw-file SHA256 of the two existing migrations at the approved base
// (pre-prod@0ee1b41b). Used to prove the migration contract test does not
// silently drift the existing DDL/DML bytes.
const EXPECTED_DDL_SHA256 =
  "346d805c224075503abce772257e283e6d10c35ccff981e234c64eea7ada4361";
const EXPECTED_DML_SHA256 =
  "f5255eeae820861ab143ea9e3327a725728647a4f28c939685a809e30e5a5c0f";

function sha256File(p: string): Promise<string> {
  return fs.readFile(p).then((b) =>
    crypto.createHash("sha256").update(b).digest("hex"),
  );
}

let sql = "";
let migrationExists = false;

beforeAll(async () => {
  migrationExists = await fs
    .access(NEW_MIGRATION)
    .then(() => true)
    .catch(() => false);
  if (migrationExists) {
    sql = (await fs.readFile(NEW_MIGRATION, "utf8")).toLowerCase();
  }
});

describe("Task 2 RED — new projection_events migration contract", () => {
  it("new migration file exists (RED until implemented)", () => {
    expect(
      migrationExists,
      `new migration must exist at ${NEW_MIGRATION}`,
    ).toBe(true);
  });

  it("creates the projection_events table", () => {
    expect(sql).toMatch(/create\s+table\b[^\n;]*projection_events/i);
  });

  it("enforces unique canonical event identity (run_id, source_system, source_event_id)", () => {
    const m = sql.match(/unique\s*\(([^)]*)\)/i);
    expect(m, "unique constraint present").toBeTruthy();
    const cols = (m?.[1] ?? "").replace(/\s+/g, " ");
    expect(cols).toContain("run_id");
    expect(cols).toContain("source_system");
    expect(cols).toContain("source_event_id");
  });

  it("has durable projection_ordinal ordering column", () => {
    expect(sql).toMatch(
      /\bprojection_ordinal\b\s+(bigint|integer|bigserial|numeric)/i,
    );
  });

  it("creates required indexes on projection_events", () => {
    expect(sql).toMatch(/\bcreate\s+index\b[^\n;]*on\s+projection_events/i);
  });

  it("defines notify_projection_event() function", () => {
    expect(sql).toMatch(
      /\bcreate\s+(or\s+replace\s+)?function\b[^\n;]*notify_projection_event\b/i,
    );
  });

  it("uses exact realtime.send broadcast semantics", () => {
    // realtime.send(payload, 'projection_event', 'observatory:' || run_id, false)
    expect(sql).toMatch(
      /realtime\s*\.\s*send\s*\([^)]*'projection_event'[^)]*'observatory:'\s*\|\|\s*run_id[^)]*false\s*\)/i,
    );
  });

  it("has AFTER INSERT trigger on projection_events calling the notifier", () => {
    expect(sql).toMatch(
      /\bcreate\s+trigger\b[^\n;]*after\s+insert\s+on\s+projection_events/i,
    );
    expect(sql).toMatch(
      /execute\s+(procedure|function)\s+notify_projection_event\s*\(\)/i,
    );
  });

  it("enables row level security on projection_events", () => {
    expect(sql).toMatch(
      /\balter\s+table\s+projection_events\b[^\n;]*enable\s+row\s+level\s+security/i,
    );
  });

  it("grants SELECT-only access for anon/authenticated (publishable read path)", () => {
    const m = sql.match(
      /\bcreate\s+policy\b[^\n;]*on\s+projection_events[^\n;]*for\s+select[^\n;]*/i,
    );
    expect(m, "SELECT policy on projection_events present").toBeTruthy();
    const block = (m?.[0] ?? "").toLowerCase();
    expect(block).toContain("select");
    expect(block).toMatch(/\bto\s+(anon|authenticated|public)/i);
    expect(block).toMatch(/anon/i);
    expect(block).toMatch(/authenticated/i);
  });

  it("does NOT create client INSERT/UPDATE/DELETE policies on projection_events", () => {
    const writePolicy = /\bcreate\s+policy\b[^\n;]*on\s+projection_events[^\n;]*for\s+(insert|update|delete)/i;
    expect(sql).not.toMatch(writePolicy);
  });

  it("does NOT backfill historical projection_events (no INSERT INTO projection_events)", () => {
    expect(sql).not.toMatch(/\binsert\s+into\s+projection_events\b/i);
  });
});

describe("Guard — existing migration bytes unchanged", () => {
  it("DDL 20260823T080000Z_observatory_history.sql sha256 unchanged", async () => {
    const s = await sha256File(DDL_FILE);
    expect(s).toBe(EXPECTED_DDL_SHA256);
  });

  it("DML 20260823T090000Z_observatory_backfill_dml.sql sha256 unchanged", async () => {
    const s = await sha256File(DML_FILE);
    expect(s).toBe(EXPECTED_DML_SHA256);
  });
});
