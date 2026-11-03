import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(__dirname, "..", "..", "..");
const migrationPath = path.join(root, "supabase", "migrations", "20261103150000_gwc_observation_v2_ingest.sql");
const edgePath = path.join(root, "supabase", "functions", "dwo-observation-ingest-v2", "index.ts");
const sql = fs.readFileSync(migrationPath, "utf8").toLowerCase();
const edge = fs.readFileSync(edgePath, "utf8");

describe("GWC v2 native observation ingest contract", () => {
  it("creates immutable raw ledger, cursor, source binding and hashed machine-key stores", () => {
    expect(sql).toContain("create table if not exists observation_events_raw");
    expect(sql).toContain("create table if not exists observation_ingest_cursors");
    expect(sql).toContain("create table if not exists observation_source_bindings");
    expect(sql).toContain("create table if not exists observation_machine_keys");
    expect(sql).toContain("unique (source_system, source_event_id)");
    expect(sql).toContain("unique (source_system, run_id, source_sequence)");
    expect(sql).toContain("secret_hash");
  });

  it("keeps browser roles away from ingest/raw state and grants RPC only to service_role", () => {
    for (const table of [
      "observation_source_bindings",
      "observation_machine_keys",
      "observation_events_raw",
      "observation_ingest_cursors",
    ]) {
      expect(sql).toContain(`alter table ${table} enable row level security`);
      expect(sql).toContain(`revoke all on ${table} from anon, authenticated`);
    }
    expect(sql).toMatch(/revoke all on function public\.ingest_observation_event_v2[\s\S]*from public, anon, authenticated/);
    expect(sql).toMatch(/grant execute on function public\.ingest_observation_event_v2[\s\S]*to service_role/);
    expect(sql).toContain("security invoker");
  });

  it("persists before broadcast and extends the canonical projection row", () => {
    expect(sql).toContain("insert into observation_events_raw");
    expect(sql).toContain("insert into projection_events");
    expect(sql).toContain("realtime.send(");
    expect(sql).toContain("'projection_event'");
    expect(sql).toContain("'observatory:' || new.run_id");
    expect(sql).toContain("add column if not exists raw_event_id");
    expect(sql).toContain("add column if not exists runtime_epoch");
    expect(sql).toContain("add column if not exists source_sha");
  });

  it("fails closed on source drift, id conflict and sequence gaps", () => {
    expect(sql).toContain("source_binding_mismatch");
    expect(sql).toContain("event_id_digest_conflict");
    expect(sql).toContain("source_sequence_gap");
  });

  it("Edge receiver authenticates with hashed machine key + HMAC and never expects a GWC Supabase credential", () => {
    expect(edge).toContain('x-dwo-machine-token');
    expect(edge).toContain('x-dwo-signature');
    expect(edge).toContain('x-dwo-request-digest');
    expect(edge).toContain('observation_machine_keys');
    expect(edge).toContain('secret_hash');
    expect(edge).toContain('crypto.subtle.verify("HMAC"');
    expect(edge).not.toContain("GWC_SUPABASE_SERVICE_ROLE_KEY");
    expect(edge).not.toContain("GWC_SUPABASE_SECRET_KEY");
  });

  it("Edge receiver produces a signed ACK bound to DB commit identity", () => {
    expect(edge).toContain("raw_event_id");
    expect(edge).toContain("projection_ordinal");
    expect(edge).toContain("signature_proof");
    expect(edge).toContain("dwo-observation-v2");
  });
});
