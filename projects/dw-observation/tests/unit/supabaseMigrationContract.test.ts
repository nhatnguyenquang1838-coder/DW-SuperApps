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

// Canonical immutable migration SHA-256 per .gwc/tasks/SCRUM-555/history-backfill/
// G6_PACKET.md. These are the git blob (LF) bytes at the approved base
// pre-prod@0ee1b41b (verified: `git show HEAD:<path> | shasum -a 256` reproduces
// them exactly). The working tree may be checked out with CRLF (core.autocrlf=true),
// so we LF-normalize content before hashing to reproduce the canonical repo bytes
// deterministically across environments.
const EXPECTED_DDL_SHA256 =
  "ef880051d8fb7caf40005206d1200c3824509f8084ec771324866ee29500e185";
const EXPECTED_DML_SHA256 =
  "5bcee0d6ea6a34b0b8cef91ff5a860ff2289a0f23ff9386a92105ee62aff23df";

// Hash the canonical (LF-normalized) file content. Reproduces the git blob
// SHA-256 the G6 packet binds, regardless of CRLF/LF checkout (cross-environment
// deterministic). Does NOT change repository EOL config.
function sha256File(p: string): Promise<string> {
  return fs.readFile(p, "utf8").then((text) => {
    const lf = text.replace(/\r\n?/g, "\n");
    return crypto.createHash("sha256").update(lf).digest("hex");
  });
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

  it("uses exact realtime.send broadcast semantics — NOT pg_notify, NOT comments", () => {
    // PeopleSoft-DB-style pitfalls: pg_notify or the string
    // "realtime.send(payload, 'projection_event', 'observatory:' || run_id, false)"
    // sitting inside a SQL comment must NOT satisfy this assertion. We require the
    // exact call to be a real executable statement, not a commented-out reference.
    //
    // Strategy: strip SQL single-line (--) and block (/* */) comments, then assert
    // the remaining executable SQL contains the exact realtime.send shape. If the
    // migration uses pg_notify (the current implementation), this test is GENUINELY RED
    // because the executable SQL does not contain realtime.send at all.
    const commentStripped = sql
      // Remove block comments
      .replace(/\/\*[\s\S]*?\*\//g, "")
      // Remove single-line comments (everything from -- to end of line)
      .replace(/--[^\n]*/g, "");
    expect(commentStripped).toMatch(
      /realtime\s*\.\s*send\s*\(\s*'[^']*'\s*,\s*'projection_event'\s*,\s*'observatory:'\s*\|\|\s*run_id\s*,\s*false\s*\)/i,
    );
  });

  it("does NOT use pg_notify as the broadcast mechanism", () => {
    // The intended contract is realtime.send(...), NOT pg_notify(...). A migration
    // that implements pg_notify('projection_event', ...) but does not also contain a
    // real realtime.send call does NOT satisfy the contract — it is RED. Comments
    // mentioning pg_notify are irrelevant; we check executable SQL after comment
    // stripping (same function as above, inline for independence).
    const commentStripped = sql
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/--[^\n]*/g, "");
    expect(commentStripped).not.toMatch(/pg_notify\s*\(/i);
  });

  it("defines full canonical ProjectionEvent columns (not a subset)", () => {
    // Require EVERY canonical column from the approved contract, not just a few.
    // Real pitfall: a migration that creates a table with only event_id + run_id and
    // calls it "projection_events" must still fail — missing source_system,
    // source_event_id, event_type, payload, projection_ordinal, occurred_at,
    // created_at is a real functional deficiency.
    const requiredColumns = [
      "event_id",
      "run_id",
      "source_system",
      "source_event_id",
      "event_type",
      "payload",
      "projection_ordinal",
      "occurred_at",
      "created_at",
    ] as const;
    for (const col of requiredColumns) {
      // Match column definitions like: "  event_id  TEXT ..."
      // Allow any whitespace; stop at next column/constraint/comma/paren boundary.
      const colPattern = new RegExp(
        `\\b${col}\\b\\s+(TEXT|BIGINT|JSONB|TIMESTAMPTZ|INTEGER|BIGSERIAL|SMALLINT|UUID|[VARCHAR]+[\\d*]*)\\b`,
        "i",
      );
      expect(sql).toMatch(colPattern);
    }
    // Durable global ordinal semantics: projection_ordinal must be BIGINT NOT NULL
    // (not INTEGER, not nullable, not omitted). This enforces durable ordered
    // replay — a SMALLINT or nullable ordinal breaks the global-ordinal contract.
    expect(sql).toMatch(
      /\bprojection_ordinal\b\s+BIGINT\s+NOT\s+NULL/i,
    );
    // event_id must be the explicit PRIMARY KEY (canonical single-event identity),
    // NOT merely UNIQUE. Accept both table-constraint style
    // (`PRIMARY KEY (event_id)`) and inline column style (`event_id TEXT PRIMARY KEY`),
    // since both make event_id the canonical single-event identity. What fails is a
    // table that has UNIQUE on (run_id, source_system, source_event_id) but no PRIMARY
    // KEY on event_id at all.
    const hasTableConstraintPK = /\bPRIMARY\s+KEY\b[^\n;]*\b(event_id)\b/i.test(sql);
    const hasInlineColumnPK = /\b(event_id)\b[^\n;]*\bPRIMARY\s+KEY\b/i.test(sql);
    expect(hasTableConstraintPK || hasInlineColumnPK).toBe(true);
  });

  it("regression: existing migration file hashes unchanged (canonical G6)", async () => {
    const s = await sha256File(DDL_FILE);
    expect(s).toBe(EXPECTED_DDL_SHA256);
    const s2 = await sha256File(DML_FILE);
    expect(s2).toBe(EXPECTED_DML_SHA256);
  });

  it("enables row level security on projection_events", () => {
    expect(sql).toMatch(
      /\balter\s+table\s+projection_events\b[\s\S]*?\benable\s+row\s+level\s+security\b/i,
    );
  });

  it("grants SELECT-only access for anon/authenticated (publishable read path)", () => {
    expect(sql).toMatch(
      /create\s+policy\s+projection_events_select_publishable\s+on\s+projection_events\s+for\s+select\s+to\s+anon,\s+authenticated\s+using\s*\(\s*true\s*\)/i,
    );
    expect(sql).toMatch(/create\s+policy\s+projection_events_select_publishable/i);
  });

  it("does NOT create client INSERT/UPDATE/DELETE policies on projection_events", () => {
    const writePolicy = /\bcreate\s+policy\b[^\n;]*on\s+projection_events[^\n;]*for\s+(insert|update|delete)/i;
    expect(sql).not.toMatch(writePolicy);
  });

  it("does NOT backfill historical projection_events (no INSERT INTO projection_events)", () => {
    expect(sql).not.toMatch(/\binsert\s+into\s+projection_events\b/i);
  });
});

describe("Guard — existing migration bytes unchanged (canonical G6 hashes)", () => {
  it("DDL 20260823T080000Z_observatory_history.sql sha256 == canonical ef880051…", async () => {
    const s = await sha256File(DDL_FILE);
    expect(s).toBe(EXPECTED_DDL_SHA256);
  });

  it("DML 20260823T090000Z_observatory_backfill_dml.sql sha256 == canonical 5bcee0d6…", async () => {
    const s = await sha256File(DML_FILE);
    expect(s).toBe(EXPECTED_DML_SHA256);
  });
});
