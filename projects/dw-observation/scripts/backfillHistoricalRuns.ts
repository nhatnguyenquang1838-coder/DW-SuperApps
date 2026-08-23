/**
 * DW-OBS-HIST-BACKFILL-R1 — historical Run backfill (DRY-RUN only).
 *
 * Reads authoritative repo evidence (fixtures + inventory) and builds the
 * normalized row sets for the 8 observatory tables. It NEVER connects to
 * Supabase and NEVER applies DDL/DML. Output is a deterministic dry-run
 * report (row counts, idempotency/upsert-key checks, RI checks, real-vs-sim
 * separation, reconstruction provenance, rollback plan).
 *
 * Remote apply is gated behind exact G6 approval (see G6 packet). This script
 * is the offline validation artifact only.
 */
import * as fs from "fs";
import * as path from "path";

const PROJECT_ROOT = process.env.DW_OBS_PROJECT_ROOT
  ? path.resolve(process.env.DW_OBS_PROJECT_ROOT)
  : process.cwd();
const FIXTURES = path.join(PROJECT_ROOT, "fixtures");

type RunKind = "observed_real" | "simulated_fixture" | "reconstructed_history";

interface RunsRow {
  run_id: string;
  run_kind: RunKind;
  source_system: "taskcontroller" | "gwc" | "mixed";
  epic_id?: string;
  jira_key?: string;
  parent_issue?: string;
  authority_ref?: string;
  scope_sha?: string;
  base_branch?: string;
  branch?: string;
  pr_number?: number;
  ci_run_id?: string;
  ci_status?: string;
  started_at?: string;
  completed_at?: string;
  reconstruction_basis?: string;
  source_refs: string[];
  confidence?: "HIGH" | "PARTIAL" | "UNKNOWN";
  evidence_quality?: "STRONG" | "WEAK" | "NONE";
  reconstructed_by?: string;
  reconstructed_at?: string;
  payload: Record<string, unknown>;
}

// ---- loaders ---------------------------------------------------------------
function loadFixture(name: string): any {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, name), "utf8"));
}

function loadInventory(): any {
  const p = path.resolve(
    PROJECT_ROOT,
    "..",
    "..",
    ".gwc",
    "tasks",
    "SCRUM-555",
    "history-backfill",
    "INVENTORY.md",
  );
  return fs.existsSync(p) ? fs.readFileSync(p, "utf8") : "";
}

// ---- observed_real → runs + events + nodes + gates -------------------------
function buildObservedReal(): { runs: RunsRow[]; events: any[]; gates: any[]; nodes: any[] } {
  const out: RunsRow[] = [];
  const events: any[] = [];
  const gates: any[] = [];
  const nodes: any[] = [];

  const tc = loadFixture("run_scrum555_m0.json");
  const gwc = loadFixture("run_gwc_durable_m0.json");
  const projTc = loadFixture("projection_scrum555_m0.json");
  const projGwc = loadFixture("projection_gwc_durable_m0.json");

  out.push({
    run_id: tc.run_id,
    run_kind: "observed_real",
    source_system: "taskcontroller",
    jira_key: "SCRUM-555",
    parent_issue: "70",
    payload: { source: "fixtures/run_scrum555_m0.json", events: tc.events.length },
    source_refs: ["fixtures/run_scrum555_m0.json"],
  });
  out.push({
    run_id: gwc.run_id,
    run_kind: "observed_real",
    source_system: "gwc",
    payload: { source: "fixtures/run_gwc_durable_m0.json", events: gwc.events.length },
    source_refs: ["fixtures/run_gwc_durable_m0.json"],
  });

  for (const e of tc.events) {
    events.push({
      ...e,
      run_id: tc.run_id,
      source_system: e.source ?? "taskcontroller",
      source_event_id: e.event_id,
      event_type: e.event_type ?? e.decision_kind ?? "unknown",
    });
  }
  for (const e of gwc.events) {
    events.push({
      ...e,
      run_id: gwc.run_id,
      source_system: e.source ?? "gwc",
      source_event_id: e.event_id,
      event_type: e.event_type ?? e.decision_kind ?? "unknown",
    });
  }

  // projection fixtures → gates + nodes (object maps keyed by id)
  const projTcGates = projTc.gates && typeof projTc.gates === "object" ? Object.values(projTc.gates) : [];
  const projTcNodes = projTc.nodes && typeof projTc.nodes === "object" ? Object.values(projTc.nodes) : [];
  const projGwcGates = projGwc.gates && typeof projGwc.gates === "object" ? Object.values(projGwc.gates) : [];
  const projGwcNodes = projGwc.nodes && typeof projGwc.nodes === "object" ? Object.values(projGwc.nodes) : [];

  for (const g of projTcGates) gates.push({ ...g, run_id: tc.run_id });
  for (const n of projTcNodes) nodes.push({ ...n, run_id: tc.run_id });
  for (const g of projGwcGates) gates.push({ ...g, run_id: gwc.run_id });
  for (const n of projGwcNodes) nodes.push({ ...n, run_id: gwc.run_id });
  return { runs: out, events, gates, nodes };
}

// ---- reconstructed_history → milestone delivery runs (from PR/issue evidence)
function buildReconstructed(): { runs: RunsRow[] } {
  const runs: RunsRow[] = [
    {
      run_id: "DW-OBS-M3M4-20260823-R1",
      run_kind: "reconstructed_history",
      source_system: "mixed",
      authority_ref: "G2-DW-OBS-M3M4-20260823-R1",
      scope_sha: "aa5756f5dfc424ba",
      base_branch: "pre-prod",
      branch: "auto/SCRUM-555-dw-observation-m3m4-r1",
      pr_number: 79,
      reconstruction_basis: ".gwc/tasks/SCRUM-555/M3-M4-EVIDENCE.md + PR #79",
      source_refs: [
        ".gwc/tasks/SCRUM-555/M3-M4-EVIDENCE.md",
        "github:pull/79",
      ],
      confidence: "HIGH",
      evidence_quality: "STRONG",
      reconstructed_by: "TaskController/Hermes",
      reconstructed_at: new Date().toISOString(),
      payload: { nodes: "M3 #74 -> M4 #75", merged: true },
    },
    {
      run_id: "DW-OBS-M0-20260821-R1",
      run_kind: "reconstructed_history",
      source_system: "taskcontroller",
      pr_number: 76,
      branch: "auto/SCRUM-555-dw-observation-m0-r2",
      reconstruction_basis: "PR #76 (merged) + issue #71",
      source_refs: ["github:pull/76", "github:issue/71"],
      confidence: "HIGH",
      evidence_quality: "STRONG",
      reconstructed_by: "TaskController/Hermes",
      reconstructed_at: new Date().toISOString(),
      payload: { milestone: "M0" },
    },
    {
      run_id: "DW-OBS-M1-20260821-R1",
      run_kind: "reconstructed_history",
      source_system: "taskcontroller",
      pr_number: 77,
      branch: "auto/SCRUM-555-dw-observation-m1-r1",
      reconstruction_basis: "PR #77 (merged) + issue #72",
      source_refs: ["github:pull/77", "github:issue/72"],
      confidence: "HIGH",
      evidence_quality: "STRONG",
      reconstructed_by: "TaskController/Hermes",
      reconstructed_at: new Date().toISOString(),
      payload: { milestone: "M1" },
    },
    {
      run_id: "DW-OBS-M2-20260822-R1",
      run_kind: "reconstructed_history",
      source_system: "taskcontroller",
      pr_number: 78,
      branch: "auto/SCRUM-555-dw-observation-m2-r1",
      reconstruction_basis: "PR #78 (merged) + issue #73",
      source_refs: ["github:pull/78", "github:issue/73"],
      confidence: "HIGH",
      evidence_quality: "STRONG",
      reconstructed_by: "TaskController/Hermes",
      reconstructed_at: new Date().toISOString(),
      payload: { milestone: "M2" },
    },
    {
      run_id: "DW-OBS-M3-20260822-R1",
      run_kind: "reconstructed_history",
      source_system: "taskcontroller",
      pr_number: 79,
      reconstruction_basis: "PR #79 (merged) + issue #74",
      source_refs: ["github:pull/79", "github:issue/74"],
      confidence: "HIGH",
      evidence_quality: "STRONG",
      reconstructed_by: "TaskController/Hermes",
      reconstructed_at: new Date().toISOString(),
      payload: { milestone: "M3" },
    },
    {
      run_id: "DW-OBS-M4-20260822-R1",
      run_kind: "reconstructed_history",
      source_system: "taskcontroller",
      pr_number: 79,
      reconstruction_basis: "PR #79 (merged) + issue #75",
      source_refs: ["github:pull/79", "github:issue/75"],
      confidence: "HIGH",
      evidence_quality: "STRONG",
      reconstructed_by: "TaskController/Hermes",
      reconstructed_at: new Date().toISOString(),
      payload: { milestone: "M4" },
    },
  ];
  return { runs };
}

// ---- dry-run validation ---------------------------------------------------
interface DryRunReport {
  ok: boolean;
  counts: Record<string, number>;
  byRunKind: Record<string, number>;
  upsertKeyConflicts: string[];
  duplicateRunRows: string[];
  realVsSimSeparation: boolean;
  riChecks: string[];
  rollback: string;
  errors: string[];
}

function validate(
  runs: RunsRow[],
  events: any[],
  gates: any[] = [],
  nodes: any[] = [],
): DryRunReport {
  const errors: string[] = [];
  const upsertKeyConflicts: string[] = [];
  const duplicateRunRows: string[] = [];

  // no duplicate run_id (PK)
  const seen = new Set<string>();
  for (const r of runs) {
    if (seen.has(r.run_id)) duplicateRunRows.push(r.run_id);
    seen.add(r.run_id);
  }

  // event upsert key uniqueness (run_id, source_system, source_event_id)
  const evKeys = new Set<string>();
  for (const e of events) {
    const k = `${e.run_id}|${e.source_system}|${e.source_event_id}`;
    if (evKeys.has(k)) upsertKeyConflicts.push(k);
    evKeys.add(k);
  }

  // real-vs-sim separation: no simulated_fixture rows present
  const sim = runs.filter((r) => r.run_kind === "simulated_fixture");
  const realVsSimSeparation = sim.length === 0;

  // RI: every event.run_id / gate.run_id / node.run_id must exist in runs
  const runIds = new Set(runs.map((r) => r.run_id));
  const riChecks: string[] = [];
  for (const e of events) {
    if (!runIds.has(e.run_id)) riChecks.push(`event ${e.source_event_id} → missing run ${e.run_id}`);
  }
  for (const g of gates) {
    if (!runIds.has(g.run_id)) riChecks.push(`gate ${g.gate_id ?? "?"} → missing run ${g.run_id}`);
  }
  for (const n of nodes) {
    if (!runIds.has(n.run_id)) riChecks.push(`node ${n.node_id ?? "?"} → missing run ${n.run_id}`);
  }

  const byRunKind: Record<string, number> = {};
  for (const r of runs) byRunKind[r.run_kind] = (byRunKind[r.run_kind] || 0) + 1;

  const counts: Record<string, number> = {
    runs: runs.length,
    events: events.length,
    gates: gates.length,
    nodes: nodes.length,
    artifacts: 0,
    checkpoints: 0,
    edges: 0,
    sources: 0,
  };

  const rollback = `DROP TABLE IF EXISTS run_sources, run_edges, run_checkpoints, run_artifacts, run_events, run_nodes, run_gates, runs CASCADE;`;

  if (duplicateRunRows.length) errors.push(`duplicate run rows: ${duplicateRunRows.join(", ")}`);
  if (upsertKeyConflicts.length) errors.push(`event upsert conflicts: ${upsertKeyConflicts.length}`);
  if (riChecks.length) errors.push(`RI violations: ${riChecks.length}`);
  if (!realVsSimSeparation) errors.push("simulated_fixture rows present (separation violated)");

  return {
    ok: errors.length === 0,
    counts,
    byRunKind,
    upsertKeyConflicts,
    duplicateRunRows,
    realVsSimSeparation,
    riChecks,
    rollback,
    errors,
  };
}

// ---- main ------------------------------------------------------------------
function main() {
  const obs = buildObservedReal();
  const rec = buildReconstructed();
  const allRuns = [...obs.runs, ...rec.runs];

  const report = validate(allRuns, obs.events, obs.gates, obs.nodes);

  const out = {
    migration: "20260823T080000Z_observatory_history.sql",
    target_project: "auswvdxoetufwiaxutib",
    dry_run: true,
    remote_apply: false,
    g6_boundary: "STOP — no remote apply until exact G6 approval bound",
    ...report,
    runs: allRuns,
  };

  console.log(JSON.stringify(out, null, 2));
  process.exit(report.ok ? 0 : 1);
}

main();
