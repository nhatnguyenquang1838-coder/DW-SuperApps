import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(__dirname, "..", "..", "..");
const baseMigrationPath = path.join(root, "supabase", "migrations", "20261103150000_gwc_observation_v2_ingest.sql");
const finalMigrationPath = path.join(root, "supabase", "migrations", "20261103161000_finalize_native_observation_contract.sql");
const postDeployPath = path.join(root, "scripts", "postdeploy-finalize-native-observation-rpc.sql");
const indexMigrationPath = path.join(root, "supabase", "migrations", "20261103163000_native_read_model_indexes.sql");
const hardeningMigrationPath = path.join(root, "supabase", "migrations", "20261103164000_native_observation_security_hardening.sql");
const verifyPath = path.join(root, "scripts", "verify-native-observation-db.sql");
const edgePath = path.join(root, "supabase", "functions", "dwo-observation-ingest-v2", "index.ts");
const profilePath = path.join(root, "project-profile.yaml");

const baseSql = fs.readFileSync(baseMigrationPath, "utf8").toLowerCase();
const finalSql = fs.readFileSync(finalMigrationPath, "utf8").toLowerCase();
const postDeploySql = fs.readFileSync(postDeployPath, "utf8").toLowerCase();
const indexSql = fs.readFileSync(indexMigrationPath, "utf8").toLowerCase();
const hardeningSql = fs.readFileSync(hardeningMigrationPath, "utf8").toLowerCase();
const verifySql = fs.readFileSync(verifyPath, "utf8").toLowerCase();
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

  it("final migration is restart-safe, source-bound and self-healing", () => {
    expect(finalSql).toContain("pg_advisory_xact_lock");
    expect(finalSql).toContain("accepted_source_id");
    expect(finalSql).toContain("p_source_id text");
    expect(finalSql).toContain("and b.source_id = p_source_id");
    expect(finalSql).toContain("event_source_id_conflict");
    expect(finalSql).toContain("source_sequence_gap");
    expect(finalSql).toContain("insert into public.run_gates");
    expect(finalSql).toContain("insert into public.run_nodes");
    expect(finalSql).toContain("insert into public.projection_events");
    expect(finalSql).toContain("_materialize_gwc_observation_read_model_v2");
    expect(finalSql).toContain("verify_raw_projection_gap");
    expect(finalSql).toContain("verify_gate_materialization_gap");
    expect(finalSql).toContain("verify_node_materialization_gap");
  });

  it("keeps browser roles away from ingest/raw state and final RPC is service_role-only", () => {
    for (const table of [
      "observation_source_bindings",
      "observation_machine_keys",
      "observation_events_raw",
      "observation_ingest_cursors",
    ]) {
      expect(baseSql).toContain(`alter table ${table} enable row level security`);
      expect(baseSql).toContain(`revoke all on ${table} from anon, authenticated`);
    }
    expect(finalSql).toMatch(/revoke all on function public\.ingest_observation_event_v2\(text,jsonb,text\)[\s\S]*from public, anon, authenticated/);
    expect(finalSql).toMatch(/grant execute on function public\.ingest_observation_event_v2\(text,jsonb,text\)[\s\S]*to service_role/);
    expect(finalSql).toContain("security invoker");
    expect(postDeploySql).toContain("drop function if exists public.ingest_observation_event_v2(jsonb,text)");
    expect(postDeploySql).toContain("postdeploy_source_bound_rpc_missing");
    expect(verifySql).toContain("verify_browser_rpc_execute_present");
    expect(verifySql).toMatch(/end\s+\$\$;/);
    expect(verifySql).not.toMatch(/end\s+\$;(?!\$)/);
    expect(hardeningSql).toContain("verify_server_only_table_exposure");
    expect(hardeningSql).toContain("observation_source_bindings_sha_policy_check");
    expect(hardeningSql).toContain("from public, anon, authenticated");
  });

  it("supports head-independent signed main provenance without dropping exact SHA audit", () => {
    expect(finalSql).toContain("sha_policy");
    expect(finalSql).toContain("'any_signed'");
    expect(finalSql).toContain("source_sha = null");
    expect(finalSql).toContain("b.source_sha = v_source_sha");
    expect(edge).toContain("p_source_id: sourceId");
    expect(profile).toContain("sha_policy: ANY_SIGNED");
    expect(profile).toContain("exact_sha_provenance: event.source.sha");
    expect(profile).not.toContain("target_sha:");
  });

  it("repairs and materializes the functional runs/gates/nodes read model", () => {
    expect(finalSql).toContain("insert into public.runs");
    expect(finalSql).toContain("insert into public.run_gates");
    expect(finalSql).toContain("insert into public.run_nodes");
    expect(finalSql).toContain("update public.run_gates");
    expect(finalSql).toContain("state = 'passed'");
    expect(finalSql).toContain("gwc_universal_v2");
    expect(finalSql).toContain("observed_runtime");
    expect(finalSql).toContain("order by run_id, source_sequence, id");
    expect(verifySql).toContain("verify_gate_gap");
    expect(verifySql).toContain("verify_node_gap");
  });

  it("covers native read-model query paths with FK indexes", () => {
    expect(indexSql).toContain("idx_run_gates_run_id");
    expect(indexSql).toContain("idx_run_nodes_run_id");
    expect(indexSql).toContain("idx_run_nodes_gate_id");
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
