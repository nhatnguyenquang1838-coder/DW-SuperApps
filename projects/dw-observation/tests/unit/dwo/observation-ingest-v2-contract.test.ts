import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(__dirname, "..", "..", "..");
const baseMigrationPath = path.join(root, "supabase", "migrations", "20261103150000_gwc_observation_v2_ingest.sql");
const finalMigrationPath = path.join(root, "supabase", "migrations", "20261103160000_native_read_model_dynamic_source.sql");
const edgePath = path.join(root, "supabase", "functions", "dwo-observation-ingest-v2", "index.ts");
const profilePath = path.join(root, "project-profile.yaml");
const baseSql = fs.readFileSync(baseMigrationPath, "utf8").toLowerCase();
const finalSql = fs.readFileSync(finalMigrationPath, "utf8").toLowerCase();
const edge = fs.readFileSync(edgePath, "utf8");
const profile = fs.readFileSync(profilePath, "utf8");

describe("GWC v2 native observation ingest contract", () => {
  it("creates immutable raw ledger, cursor, source binding and hashed machine-key stores", () => {
    expect(baseSql).toContain("create table if not exists observation_events_raw");
    expect(baseSql).toContain("create table if not exists observation_ingest_cursors");
    expect(baseSql).toContain("create table if not exists observation_source_bindings");
    expect(baseSql).toContain("create table if not exists observation_machine_keys");
    expect(baseSql).toContain("unique (source_system, source_event_id)");
    expect(baseSql).toContain("unique (source_system, run_id, source_sequence)");
    expect(baseSql).toContain("secret_hash");
  });

  it("keeps browser roles away from ingest/raw state and grants final RPC only to service_role", () => {
    for (const table of [
      "observation_source_bindings",
      "observation_machine_keys",
      "observation_events_raw",
      "observation_ingest_cursors",
    ]) {
      expect(baseSql).toContain(`alter table ${table} enable row level security`);
      expect(baseSql).toContain(`revoke all on ${table} from anon, authenticated`);
    }
    expect(finalSql).toMatch(/revoke all on function public\.ingest_observation_event_v2\(text, jsonb, text\)[\s\S]*from public, anon, authenticated/);
    expect(finalSql).toMatch(/grant execute on function public\.ingest_observation_event_v2\(text, jsonb, text\)[\s\S]*to service_role/);
    expect(finalSql).toContain("security invoker");
  });

  it("binds authenticated machine source_id to repository/schema and supports head-independent signed provenance", () => {
    expect(finalSql).toContain("p_source_id text");
    expect(finalSql).toContain("and b.source_id = p_source_id");
    expect(finalSql).toContain("sha_policy");
    expect(finalSql).toContain("'any_signed'");
    expect(finalSql).toContain("b.source_sha = v_source_sha");
    expect(edge).toContain("p_source_id: sourceId");
    expect(profile).toContain("sha_policy: ANY_SIGNED");
    expect(profile).toContain("exact_sha_provenance: event.source.sha");
    expect(profile).not.toContain("target_sha:");
  });

  it("atomically materializes the functional runs/gates/nodes read model before projection commit", () => {
    expect(finalSql).toContain("insert into runs");
    expect(finalSql).toContain("insert into observation_events_raw");
    expect(finalSql).toContain("insert into run_gates");
    expect(finalSql).toContain("insert into run_nodes");
    expect(finalSql).toContain("insert into projection_events");
    expect(finalSql).toContain("update run_gates");
    expect(finalSql).toContain("state = 'passed'");
    expect(finalSql).toContain("gwc_universal_v2");
    expect(finalSql).toContain("observed_runtime");
  });

  it("fails closed on source drift, id conflict and sequence gaps", () => {
    expect(finalSql).toContain("source_binding_mismatch");
    expect(finalSql).toContain("event_id_digest_conflict");
    expect(finalSql).toContain("source_sequence_gap");
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

  it("broadcasts only after durable RPC commit and signs ACK DB identity", () => {
    const rpcPos = edge.indexOf('supabase.rpc("ingest_observation_event_v2"');
    const broadcastPos = edge.indexOf('type: "broadcast"');
    expect(rpcPos).toBeGreaterThan(-1);
    expect(broadcastPos).toBeGreaterThan(rpcPos);
    expect(edge).toContain("raw_event_id");
    expect(edge).toContain("projection_ordinal");
    expect(edge).toContain("signature_proof");
    expect(edge).toContain("dwo-observation-v2");
  });
});
