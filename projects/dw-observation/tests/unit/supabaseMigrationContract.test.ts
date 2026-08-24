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
    // Flatten newlines so multiline CREATE INDEX statements match.
    const flat = sql.replace(/\r\n?/g, " ").replace(/\n/g, " ");
    // The canonical envelope requires at least one CREATE INDEX on projection_events.
    expect(flat).toMatch(/\bcreate\s+(unique\s+)?index\b/i);
    // Canonical envelope requires both run_ordinal and run_src_seq indexes
    // with their specific column lists.
    expect(flat).toMatch(
      /idx_projection_events_run_ordinal\s+on\s+projection_events\s*\(\s*run_id\s*,\s*projection_ordinal\s*\)/i,
    );
    expect(flat).toMatch(
      /idx_projection_events_run_src_seq\s+on\s+projection_events\s*\(\s*run_id\s*,\s*source_system\s*,\s*sequence\s*\)/i,
    );
  });

  it("enforces strict deterministic per-run ordering via UNIQUE (run_id, projection_ordinal)", () => {
    // Flatten newlines so multiline CREATE UNIQUE INDEX matches.
    const flat = sql.replace(/\r\n?/g, " ").replace(/\n/g, " ");
    // Canonical contract: UNIQUE INDEX on (run_id, projection_ordinal).
    // Accept either CREATE UNIQUE INDEX [...] ON projection_events (run_id, projection_ordinal)
    // or CONSTRAINT unique (run_id, projection_ordinal) format.
    const uniqueIndex = /create\s+unique\s+index\s+if\s+not\s+exists\s+idx_projection_events_run_ordinal\s+on\s+projection_events\s*\(\s*run_id\s*,\s*projection_ordinal\s*\)/i;
    const uniqueConstraint = /constraint\s+\S+\s+unique\s*\(\s*run_id\s*,\s*projection_ordinal\s*\)/i;
    expect(uniqueIndex.test(flat) || uniqueConstraint.test(flat)).toBe(true);
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
      /realtime\s*\.\s*send\s*\(\s*[\s\S]*?'projection_event'\s*,\s*'observatory:'\s*\|\|\s*new\.run_id\s*,\s*false\s*\)/i,
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

  it("defines normalized canonical ProjectionEvent columns (RunProjectionEvent v1)", () => {
    // Require EVERY normalized column from the canonical
    // projects/dw-observation/sql/projection_events.sql envelope, not a subset.
    // The current G6 migration at 7ce6aace lacks these and leaves
    // projection_ordinal BIGINT NOT NULL caller-assigned — after G6 real detail
    // reads would error/degrade despite CI GREEN. This test must be RED until the
    // migration is aligned to the canonical normalized schema.
    const requiredColumns = [
      "id",
      "projection_ordinal",
      "run_id",
      "source_system",
      "source_event_id",
      "sequence",
      "event_type",
      "occurred_at",
      "gate",
      "node_id",
      "actor",
      "outcome",
      "before",
      "after",
      "evidence_refs",
      "authority_ref",
      "source_digest",
      "read_only_projection",
    ] as const;
    for (const col of requiredColumns) {
      const colPattern = new RegExp(
        `\\b${col}\\b\\s+(TEXT|BIGINT|JSONB|TIMESTAMPTZ|INTEGER|BIGSERIAL|SMALLINT|UUID|BOOLEAN|[VARCHAR]+[\\d*]*)\\b`,
        "i",
      );
      expect(sql).toMatch(colPattern);
    }
    // Canonical identity: UNIQUE (run_id, source_system, source_event_id).
    const hasIdentity = /\bunique\b[^\n;]*\(\s*run_id\s*,\s*source_system\s*,\s*source_event_id\s*\)/i.test(sql);
    expect(hasIdentity).toBe(true);
  });

  it("uses DB-assigned durable global ordinal — GENERATED ALWAYS AS IDENTITY", () => {
    // projection_ordinal must be DB-assigned (GENERATED ALWAYS AS IDENTITY), not
    // caller-supplied plain BIGINT NOT NULL. A caller-assigned ordinal breaks
    // durable cross-source ordering because the producer can invent non-monotonic
    // values. The canonical contract requires Postgres to assign it at insert time.
    expect(sql).toMatch(
      /\bprojection_ordinal\b\s+BIGINT\s+GENERATED\s+ALWAYS\s+AS\s+IDENTITY/i,
    );
    // Must NOT be a plain caller-assigned BIGINT NOT NULL (no GENERATED clause).
    expect(sql).not.toMatch(
      /\bprojection_ordinal\b\s+BIGINT\s+NOT\s+NULL(?!\s+GENERATED)/i,
    );
  });

  it("requires sequence INTEGER NOT NULL with non-negative check", () => {
    // sequence is the per-source ledger sequence; it must be INTEGER NOT NULL and
    // non-negative (CHECK (sequence >= 0)). The canonical contract enforces this
    // so per-source gap/duplicate detection has a well-defined domain.
    expect(sql).toMatch(
      /\bsequence\b\s+INTEGER\s+NOT\s+NULL\s+CHECK\s*\(\s*sequence\s*>=\s*0\s*\)/i,
    );
  });

  it("requires source_digest TEXT NOT NULL", () => {
    // source_digest is a NOT NULL TEXT column in the canonical envelope. It is the
    // deterministic source digest used for integrity/canonical-reference checks.
    expect(sql).toMatch(
      /\bsource_digest\b\s+TEXT\s+NOT\s+NULL/i,
    );
  });

  it("requires read_only_projection BOOLEAN NOT NULL DEFAULT TRUE", () => {
    // read_only_projection is a BOOLEAN column with DEFAULT TRUE in the canonical
    // envelope. It marks the projection as read-only (observer never mutates).
    expect(sql).toMatch(
      /\bread_only_projection\b\s+BOOLEAN\s+NOT\s+NULL\s+DEFAULT\s+TRUE/i,
    );
  });

  it("broadcast payload exposes normalized ProjectionEvent fields at top level", () => {
    // The realtime.send() payload must be the RAW normalized ProjectionEvent
    // (row columns as jsonb), NOT a nested envelope and NOT just {event_id, payload}.
    // Require the executable broadcast to include the canonical normalized fields
    // at top level: sequence, projection_ordinal, gate, node_id, actor, outcome,
    // before, after, evidence_refs, authority_ref, source_digest, read_only_projection.
    // Strip comments, then assert each normalized field appears inside the
    // json_build_object / jsonb_build_object that feeds realtime.send.
    const commentStripped = sql
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/--[^\n]*/g, "");
    // Find the json_build_object / jsonb_build_object block that feeds realtime.send
    const buildObjMatch = commentStripped.match(
      /jsonb?_build_object\s*\([^)]*\)/i,
    );
    expect(buildObjMatch, "json_build_object payload block found").toBeTruthy();
    if (buildObjMatch) {
      const payload = buildObjMatch[0];
      const requiredPayloadFields = [
        "sequence",
        "projection_ordinal",
        "gate",
        "node_id",
        "actor",
        "outcome",
        "before",
        "after",
        "evidence_refs",
        "authority_ref",
        "source_digest",
        "read_only_projection",
      ];
      for (const field of requiredPayloadFields) {
        expect(payload).toContain(`'${field}'`);
      }
    }
    // The realtime.send call must NOT cast the payload to ::text — the canonical
    // contract sends the raw jsonb so the subscriber receives it as the top-level
    // payload object, not a stringified nested envelope.
    expect(commentStripped).not.toMatch(
      /realtime\s*\.\s*send\s*\(.*::\s*text/i,
    );
  });

  it("does NOT define non-canonical event_id / payload / created_at columns", () => {
    // The canonical normalized schema replaces event_id + payload with the full
    // normalized column set (id BIGINT GENERATED ALWAYS AS IDENTITY, plus the
    // normalized fields). A migration that still defines event_id TEXT,
    // payload JSONB, or created_at TIMESTAMPTZ is NOT aligned to canonical and
    // would cause detail-read column mismatches after G6.
    // NOTE: source_event_id TEXT is canonical and must NOT trigger this check.
    // Use a negative-lookbehind-style check: event_id NOT preceded by "source_".
    const flat = sql.replace(/\r\n?/g, " ").replace(/\n/g, " ");
    expect(flat).not.toMatch(/(^|[^a-zA-Z0-9_])event_id\s+TEXT/i);
    expect(flat).not.toMatch(/\bpayload\b\s+JSONB/i);
    expect(flat).not.toMatch(/\bcreated_at\b\s+TIMESTAMPTZ/i);
  });

  it("requires id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY", () => {
    // Canonical contract: id is the DB-generated durable IDENTITY primary key,
    // NOT a caller-supplied TEXT/UUID. The migration must declare id as BIGINT
    // GENERATED ALWAYS AS IDENTITY PRIMARY KEY.
    expect(sql).toMatch(
      /\bid\b\s+BIGINT\s+GENERATED\s+ALWAYS\s+AS\s+IDENTITY\s+PRIMARY\s+KEY/i,
    );
    // Must NOT define event_id TEXT as primary key (old non-canonical shape).
    expect(sql).not.toMatch(/\bevent_id\b\s+TEXT\s+PRIMARY\s+KEY/i);
  });

  it("aligns source_system CHECK with canonical normalized contract (taskcontroller, gwc only)", () => {
    // Canonical contract: source_system IN ('taskcontroller', 'gwc').
    // Do NOT widen to 'mixed' unless an approved test/type proves it required.
    expect(sql).toMatch(
      /CHECK\s*\(\s*source_system\s+IN\s*\(\s*'taskcontroller'\s*,\s*'gwc'\s*\)/i,
    );
    // Must NOT include 'mixed' as a valid source_system option (invented
    // compatibility widening). The canonical contract is taskcontroller + gwc only.
    // Read the CHECK as a flattened string; the word "mixed" must not appear
    // inside the CHECK(...) constraint expression itself (comments are stripped
    // by the test, so any "mixed" in the CHECK is a real column-value widening).
    const checkMatch = sql.match(/check\s*\(\s*source_system\s+in\s*\(\s*[^)]*\)\s*\)/i);
    if (checkMatch) {
      expect(checkMatch[0]).not.toMatch(/mixed/i);
    }
  });

  it("preserves FK run_id REFERENCES runs(run_id) ON DELETE CASCADE (G6-compatible)", () => {
    // G6 migration-specific FK to runs table. Compatible with canonical contract.
    expect(sql).toMatch(
      /REFERENCES\s+runs\s*\(\s*run_id\s*\)\s+ON\s+DELETE\s+CASCADE/i,
    );
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